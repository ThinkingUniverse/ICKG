"""Batch triple extraction with Baichuan-M3 API.

This script reads PubMed records, uses a markdown prompt template,
extracts triples from title+abstract text, and appends results to JSONL.
Supports concurrent extraction with multiple API keys.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import requests


API_URL = "https://api.baichuan-ai.com/v1/chat/completions"

# How many 429 responses to tolerate before marking a key as exhausted
_QUOTA_MAX_ATTEMPTS = 3
# Seconds to wait between each 429 retry for the same key
_QUOTA_WAIT_SEC = 2.0


class APIFatal429Error(Exception):
	"""Raised when all keys in the pool are exhausted (all returned 429)."""


class KeyAcquireTimeoutError(Exception):
	"""Raised when waiting for an available key times out temporarily."""


class KeyScheduler:
	"""Thread-safe API key scheduler with per-key concurrency and daily limits.

	The key file is re-read on every ``acquire_key()`` call so that keys
	added while the program is running are automatically picked up.
	"""

	def __init__(
		self,
		path: Path,
		max_concurrency_per_key: int = 2,
		daily_limit: int = 300,
	) -> None:
		self._path = path
		self._max_concurrency = max_concurrency_per_key
		self._daily_limit = daily_limit
		self._lock = threading.Lock()
		self._condition = threading.Condition(self._lock)
		self._exhausted: Set[str] = set()
		self._in_flight: Dict[str, int] = {}
		self._daily_count: Dict[str, int] = {}
		self._keys: List[str] = []
		self._refresh_keys_unlocked()
		if not self._keys:
			raise ValueError(f"No API keys found in {path}")
		print(
			f"[KeyScheduler] Loaded {len(self._keys)} API keys | "
			f"concurrency/key={self._max_concurrency}, "
			f"daily_limit/key={self._daily_limit}"
		)

	def _read_fresh_keys(self) -> List[str]:
		if not self._path.exists():
			return []
		keys: List[str] = []
		with self._path.open("r", encoding="utf-8") as fh:
			for line in fh:
				value = line.strip()
				if value:
					keys.append(value)
		return keys

	def _refresh_keys_unlocked(self) -> None:
		"""Re-read key file; must be called while holding ``_lock``."""
		fresh = self._read_fresh_keys()
		existing = set(self._keys)
		for key in fresh:
			if key not in existing and key not in self._in_flight:
				self._in_flight[key] = 0
				self._daily_count[key] = 0
				print(f"[KeyScheduler] Discovered new key: {key}")
			elif key not in self._in_flight:
				self._in_flight.setdefault(key, 0)
				self._daily_count.setdefault(key, 0)
		self._keys = fresh

	def acquire_key(self, timeout: float = 60.0) -> Optional[str]:
		"""Block until a usable key is available.

		Returns a key with an available concurrency slot and remaining
		daily quota, raises ``KeyAcquireTimeoutError`` on temporary wait
		timeout, or returns ``None`` only when all keys are exhausted or
		daily-capped.
		"""
		deadline = time.monotonic() + timeout
		with self._condition:
			while True:
				self._refresh_keys_unlocked()
				any_alive = False
				for key in self._keys:
					if key in self._exhausted:
						continue
					if self._daily_count.get(key, 0) >= self._daily_limit:
						continue
					any_alive = True
					if self._in_flight.get(key, 0) < self._max_concurrency:
						self._in_flight[key] = self._in_flight.get(key, 0) + 1
						self._daily_count[key] = self._daily_count.get(key, 0) + 1
						print(f"[KeyScheduler] Acquired key: {key}")
						return key
				if not any_alive:
					return None
				remaining = deadline - time.monotonic()
				if remaining <= 0:
					raise KeyAcquireTimeoutError("Timed out waiting for an available API key")
				self._condition.wait(timeout=min(remaining, 2.0))

	def release_key(self, key: str) -> None:
		"""Free one concurrency slot for *key*."""
		with self._condition:
			self._in_flight[key] = max(0, self._in_flight.get(key, 0) - 1)
			self._condition.notify_all()

	def mark_exhausted(self, key: str) -> None:
		"""Mark *key* as exhausted (429 quota hit)."""
		with self._condition:
			self._exhausted.add(key)
			print(f"[KeyScheduler] Key exhausted (429): {key}")
			self._condition.notify_all()

	def status_summary(self) -> str:
		with self._lock:
			self._refresh_keys_unlocked()
			unique_keys = list(dict.fromkeys(self._keys))
			total = len(unique_keys)
			exhausted = sum(1 for k in unique_keys if k in self._exhausted)
			daily_capped = sum(
				1 for k in unique_keys
				if k not in self._exhausted
				and self._daily_count.get(k, 0) >= self._daily_limit
			)
			active = total - exhausted - daily_capped
			return (
				f"keys: {total} total, {active} active, "
				f"{exhausted} exhausted, {daily_capped} daily-capped"
			)


@dataclass
class RunStats:
	total: int = 0
	skipped: int = 0
	success_records: int = 0
	failed_records: int = 0
	total_triples: int = 0
	truncated_records: int = 0
	_lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

	def inc_success(self, triples: int) -> None:
		with self._lock:
			self.success_records += 1
			self.total_triples += triples

	def inc_failed(self) -> None:
		with self._lock:
			self.failed_records += 1

	def inc_truncated(self) -> None:
		with self._lock:
			self.truncated_records += 1

	def inc_skipped(self) -> None:
		with self._lock:
			self.skipped += 1

	def snapshot(self) -> Dict[str, int]:
		with self._lock:
			return {
				"total": self.total,
				"skipped": self.skipped,
				"success": self.success_records,
				"failed": self.failed_records,
				"triples": self.total_triples,
				"truncated": self.truncated_records,
			}


def utc_now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


def load_json_file(path: Path) -> Any:
	with path.open("r", encoding="utf-8-sig") as handle:
		return json.load(handle)


def iter_input_json_files(input_path: Path) -> List[Path]:
	if input_path.is_file():
		if input_path.suffix.lower() != ".json":
			raise ValueError(f"Input file must be a JSON file: {input_path}")
		return [input_path]

	if input_path.is_dir():
		json_files = sorted(path for path in input_path.glob("*.json") if path.is_file())
		if not json_files:
			raise ValueError(f"No JSON files found in input directory: {input_path}")
		return json_files

	raise FileNotFoundError(f"Input path does not exist: {input_path}")


def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open("a", encoding="utf-8") as handle:
		handle.write(json.dumps(obj, ensure_ascii=False) + "\n")
		handle.flush()


def load_state_pmids(state_path: Path) -> Set[str]:
	if not state_path.exists():
		return set()

	pmids: Set[str] = set()
	with state_path.open("r", encoding="utf-8") as handle:
		for line in handle:
			value = line.strip()
			if value:
				pmids.add(value)
	return pmids


def append_state_pmid(state_path: Path, pmid: str) -> None:
	state_path.parent.mkdir(parents=True, exist_ok=True)
	with state_path.open("a", encoding="utf-8") as handle:
		handle.write(f"{pmid}\n")
		handle.flush()


def sanitize_prompt_template(raw_prompt: str) -> str:
	"""Drop the draft Input section so runtime can inject real input text."""
	marker_pattern = re.compile(r"\n##\s*Input\b", flags=re.IGNORECASE)
	match = marker_pattern.search(raw_prompt)
	if match:
		return raw_prompt[: match.start()].rstrip()
	return raw_prompt.strip()


def build_system_prompt(template_without_input: str, use_hard_constraints: bool) -> str:
	prompt = f"{template_without_input}\n"
	if use_hard_constraints:
		prompt += (
			"\nHard constraints:\n"
			"1. Only use predefined entity types and predefined relation types from this prompt.\n"
			"2. Output must be a JSON array only; do not add any explanatory text.\n"
		)
	return prompt


def build_user_prompt(input_text: str) -> str:
	return (
		"## Input\n"
		"```\n"
		f"{{{input_text}}}\n"
		"```\n"
	)


def normalize_record_text(title: str, abstract: str) -> str:
	title_clean = (title or "").strip()
	abstract_clean = (abstract or "").strip()
	merged = f"{title_clean} {abstract_clean}".strip()
	return re.sub(r"\s+", " ", merged)


def strip_code_fence(text: str) -> str:
	cleaned = text.strip()
	fence_pattern = re.compile(r"^```(?:json)?\s*([\s\S]*?)\s*```$", re.IGNORECASE)
	match = fence_pattern.match(cleaned)
	if match:
		return match.group(1).strip()
	return cleaned


def find_first_json_array_block(text: str) -> Optional[str]:
	"""Find the first balanced JSON array substring in text."""
	start = text.find("[")
	if start == -1:
		return None

	depth = 0
	in_string = False
	escaped = False
	for idx in range(start, len(text)):
		ch = text[idx]

		if in_string:
			if escaped:
				escaped = False
			elif ch == "\\":
				escaped = True
			elif ch == '"':
				in_string = False
			continue

		if ch == '"':
			in_string = True
		elif ch == "[":
			depth += 1
		elif ch == "]":
			depth -= 1
			if depth == 0:
				return text[start : idx + 1]

	return None


def parse_triples_json(model_text: str) -> List[Dict[str, Any]]:
	content = strip_code_fence(model_text)

	try:
		parsed = json.loads(content)
	except json.JSONDecodeError:
		array_block = find_first_json_array_block(content)
		if not array_block:
			raise
		parsed = json.loads(array_block)

	if not isinstance(parsed, list):
		raise ValueError("Model output is not a JSON array.")

	triples: List[Dict[str, Any]] = []
	for item in parsed:
		if isinstance(item, dict):
			triples.append(item)
	return triples


def call_baichuan(
	session: requests.Session,
	api_key: str,
	model: str,
	system_prompt: str,
	user_prompt: str,
	temperature: float,
	top_p: float,
	top_k: int,
	max_tokens: int,
	timeout_sec: int,
	thinking_budget_tokens: int,
	enable_timing: bool = False,
) -> tuple[str, Dict[str, Any]]:
	func_start = time.perf_counter() if enable_timing else 0
	headers = {
		"Content-Type": "application/json",
		"Authorization": f"Bearer {api_key}",
	}
	payload = {
		"model": model,
		"messages": [
			{"role": "system", "content": system_prompt},
			{"role": "user", "content": user_prompt},
		],
		"stream": False,
		"temperature": temperature,
		"top_p": top_p,
		"top_k": top_k,
		"max_tokens": max_tokens,
	}
	if thinking_budget_tokens > 0:
		payload["thinking"] = {"budget_tokens": thinking_budget_tokens}

	try:
		if enable_timing:
			post_start = time.perf_counter()
		response = session.post(API_URL, headers=headers, json=payload, timeout=timeout_sec)
		if enable_timing:
			post_elapsed_sec = time.perf_counter() - post_start
			print(f"[Timing] session.post cost: {post_elapsed_sec:.4f}s")

		if response.status_code == 429:
			raise APIFatal429Error("429 Client Error: API quota exhausted")
		response.raise_for_status()

		body = response.json()
		choices = body.get("choices", [])
		if not choices:
			raise ValueError("No choices returned from API.")

		message = choices[0].get("message", {})
		content = message.get("content")
		if not isinstance(content, str) or not content.strip():
			raise ValueError("Empty or invalid content in API response.")

		usage = body.get("usage", {})
		if not isinstance(usage, dict):
			usage = {}

		return content, usage
	finally:
		if enable_timing:
			func_elapsed_sec = time.perf_counter() - func_start
			print(f"[Timing] call_baichuan total cost: {func_elapsed_sec:.4f}s")


def call_baichuan_with_quota_retry(
	session: requests.Session,
	api_key: str,
	model: str,
	system_prompt: str,
	user_prompt: str,
	temperature: float,
	top_p: float,
	top_k: int,
	max_tokens: int,
	timeout_sec: int,
	thinking_budget_tokens: int,
	enable_timing: bool = False,
) -> tuple[str, Dict[str, Any]]:
	"""Call ``call_baichuan`` up to ``_QUOTA_MAX_ATTEMPTS`` times for 429s.

	Waits ``_QUOTA_WAIT_SEC`` between each attempt.  After all attempts are
	exhausted, re-raises ``APIFatal429Error`` so the caller can rotate keys.
	"""
	for attempt in range(1, _QUOTA_MAX_ATTEMPTS + 1):
		try:
			return call_baichuan(
				session=session,
				api_key=api_key,
				model=model,
				system_prompt=system_prompt,
				user_prompt=user_prompt,
				temperature=temperature,
				top_p=top_p,
				top_k=top_k,
				max_tokens=max_tokens,
				timeout_sec=timeout_sec,
				thinking_budget_tokens=thinking_budget_tokens,
				enable_timing=enable_timing,
			)
		except APIFatal429Error:
			print(
				f"[KeyScheduler] 429 for key {api_key} "
				f"(attempt {attempt}/{_QUOTA_MAX_ATTEMPTS})"
			)
			if attempt < _QUOTA_MAX_ATTEMPTS:
				time.sleep(_QUOTA_WAIT_SEC)
	raise APIFatal429Error(f"Key {api_key} returned 429 on all {_QUOTA_MAX_ATTEMPTS} attempts")


def extract_with_retry(
	session: requests.Session,
	api_key: str,
	model: str,
	system_prompt: str,
	user_prompt: str,
	max_retries: int,
	sleep_sec: float,
	temperature: float,
	top_p: float,
	top_k: int,
	max_tokens: int,
	timeout_sec: int,
	thinking_budget_tokens: int,
	enable_timing: bool = False,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
	last_error = "Unknown error"

	for attempt in range(1, max_retries + 1):
		try:
			model_text, usage = call_baichuan_with_quota_retry(
				session=session,
				api_key=api_key,
				model=model,
				system_prompt=system_prompt,
				user_prompt=user_prompt,
				temperature=temperature,
				top_p=top_p,
				top_k=top_k,
				max_tokens=max_tokens,
				timeout_sec=timeout_sec,
				thinking_budget_tokens=thinking_budget_tokens,
				enable_timing=enable_timing,
			)
			triples = parse_triples_json(model_text)
			return triples, usage
		except APIFatal429Error:
			raise
		except Exception as exc:  # pylint: disable=broad-except
			last_error = f"attempt {attempt}/{max_retries}: {exc}"
			if attempt < max_retries:
				time.sleep(max(1.0, sleep_sec) * (2 ** (attempt - 1)))

	raise ValueError(last_error)


def iter_records(data: Any) -> Iterable[Dict[str, Any]]:
	if not isinstance(data, list):
		raise ValueError("Input JSON must be a list of PubMed record objects.")
	for row in data:
		if isinstance(row, dict):
			yield row


def parse_args() -> argparse.Namespace:
	root = Path(__file__).resolve().parents[2]

	parser = argparse.ArgumentParser(
		description="Use Baichuan-M3 API to generate triple extraction fine-tuning data."
	)
	parser.add_argument(
		"--input_file",
		type=Path,
		default=root / "data/pubmed_output/random_sampling",
		help="Input PubMed JSON file or directory containing JSON files.",
	)
	parser.add_argument(
		"--prompt_file",
		type=Path,
		default=root / "prompts/Triple_prompt.md",
		help="Prompt markdown file.",
	)
	parser.add_argument(
		"--api_config",
		type=Path,
		default=root / "scripts/Triple_extraction/API_config.json",
		help="(Unused) Legacy API config JSON. Keys are now loaded from --api_keys_file.",
	)
	parser.add_argument(
		"--api_keys_file",
		type=Path,
		default=root / "scripts/Triple_extraction/API.txt",
		help="Text file with one API key per line (supports runtime additions).",
	)
	parser.add_argument(
		"--output_jsonl",
		type=Path,
		default=root / "data/Fine_tuning_dataset/triples_baichuan_m3_plus.jsonl",
		help="Output JSONL file for extracted triples.",
	)
	parser.add_argument(
		"--usage_jsonl",
		type=Path,
		default=root / "data/Fine_tuning_dataset/triples_usage.jsonl",
		help="Output JSONL file for per-PMID token usage.",
	)
	parser.add_argument(
		"--failed_jsonl",
		type=Path,
		default=root / "data/Fine_tuning_dataset/triples_failed_pmids.jsonl",
		help="Output JSONL file for failed PMIDs.",
	)
	parser.add_argument(
		"--truncation_jsonl",
		type=Path,
		default=root / "data/Fine_tuning_dataset/triples_truncated_pmids.jsonl",
		help="Output JSONL file for truncated records.",
	)
	parser.add_argument(
		"--state_file",
		type=Path,
		default=root / "data/Fine_tuning_dataset/triples_processed_pmids.txt",
		help="State file for processed PMIDs, used for resume.",
	)
	parser.add_argument(
		"--model",
		type=str,
		default="Baichuan-M3",
		help="Baichuan model name.",
	)
	parser.add_argument(
		"--max_retries",
		type=int,
		default=3,
		help="Maximum retries when output is not valid JSON.",
	)
	parser.add_argument(
		"--sleep_sec",
		type=float,
		default=1.0,
		help="Sleep seconds between records to avoid rate limits.",
	)
	parser.add_argument(
		"--max_chars",
		type=int,
		default=8000,
		help="Maximum title+abstract characters before truncation.",
	)
	parser.add_argument(
		"--temperature",
		type=float,
		default=0.8,
		help="Sampling temperature.",
	)
	parser.add_argument(
		"--top_p",
		type=float,
		default=0.85,
		help="Nucleus sampling top_p.",
	)
	parser.add_argument(
		"--top_k",
		type=int,
		default=5,
		help="Top-k sampling size.",
	)
	parser.add_argument(
		"--max_tokens",
		type=int,
		default=15000,
		help="Maximum output tokens from API.",
	)
	parser.add_argument(
		"--thinking_budget_tokens",
		type=int,
		default=5188,
		help="Thinking budget tokens; set 0 to disable.",
	)
	parser.add_argument(
		"--timeout_sec",
		type=int,
		default=90,
		help="HTTP request timeout in seconds.",
	)
	parser.add_argument(
		"--use_hard_constraints",
		type=str,
		choices=["Yes", "No"],
		default="No",
		help="Yes to include the hard-constraint block in the system prompt; No to omit it.",
	)
	parser.add_argument(
		"--enable_timing",
		type=str,
		choices=["Yes", "No"],
		default="No",
		help="Yes to enable timing logs for API calls; No to disable.",
	)
	parser.add_argument(
		"--worker_count",
		type=int,
		default=12,
		help="Number of concurrent worker threads (default: 12).",
	)
	parser.add_argument(
		"--per_key_max_concurrency",
		type=int,
		default=4,
		help="Maximum concurrent requests per API key (default: 4).",
	)
	parser.add_argument(
		"--per_key_daily_limit",
		type=int,
		default=300,
		help="Maximum daily requests per API key (default: 300).",
	)
	parser.add_argument(
		"--progress_interval",
		type=int,
		default=10,
		help="Print progress every N completed records (default: 10).",
	)

	return parser.parse_args()


def validate_paths(args: argparse.Namespace) -> None:
	if not args.input_file.exists():
		raise FileNotFoundError(f"Required input path does not exist: {args.input_file}")
	if not args.prompt_file.exists():
		raise FileNotFoundError(f"Required file does not exist: {args.prompt_file}")
	if not args.api_keys_file.exists():
		raise FileNotFoundError(f"Required file does not exist: {args.api_keys_file}")


def load_api_key(api_config_path: Path) -> str:
	config = load_json_file(api_config_path)
	if not isinstance(config, dict):
		raise ValueError("API config must be a JSON object.")

	api_key = str(config.get("api_key", "")).strip()
	if not api_key:
		raise ValueError("api_key is missing in API config.")
	return api_key




def run(args: argparse.Namespace) -> RunStats:
	validate_paths(args)

	scheduler = KeyScheduler(
		args.api_keys_file,
		max_concurrency_per_key=args.per_key_max_concurrency,
		daily_limit=args.per_key_daily_limit,
	)

	raw_prompt = args.prompt_file.read_text(encoding="utf-8")
	prompt_template = sanitize_prompt_template(raw_prompt)
	use_hard_constraints = args.use_hard_constraints == "Yes"
	system_prompt = build_system_prompt(prompt_template, use_hard_constraints)
	enable_timing = args.enable_timing == "Yes"

	input_json_files = iter_input_json_files(args.input_file)
	records: List[Dict[str, Any]] = []
	for input_json_file in input_json_files:
		records.extend(iter_records(load_json_file(input_json_file)))
	stats = RunStats(total=len(records))

	processed_pmids = load_state_pmids(args.state_file)

	# Build task list (filter already processed)
	tasks: List[tuple] = []
	for index, record in enumerate(records, start=1):
		pmid = str(record.get("PMID", "")).strip()
		if not pmid:
			pmid = f"missing_pmid_{index}"
		if pmid in processed_pmids:
			stats.skipped += 1  # single-threaded here, safe
			continue
		tasks.append((index, record, pmid))

	print("=" * 72)
	print("Baichuan Triple Extraction (Concurrent)")
	print("=" * 72)
	print(f"Input source: {args.input_file}")
	print(f"Input JSON files: {len(input_json_files)}")
	print(f"Input records: {stats.total}")
	print(f"Already processed: {stats.snapshot()['skipped']}")
	print(f"To process: {len(tasks)}")
	print(f"Workers: {args.worker_count}")
	print(f"{scheduler.status_summary()}")
	print(f"Output JSONL: {args.output_jsonl}")
	print(f"Usage JSONL: {args.usage_jsonl}")
	print(f"Failed JSONL: {args.failed_jsonl}")
	print(
		f"temperature={args.temperature}, top_p={args.top_p}, top_k={args.top_k}, "
		f"thinking_budget_tokens={args.thinking_budget_tokens}, "
		f"use_hard_constraints={args.use_hard_constraints}"
	)
	print("=" * 72)

	file_lock = threading.Lock()
	stop_event = threading.Event()
	completed_count = [0]
	count_lock = threading.Lock()

	def process_record(index: int, record: Dict[str, Any], pmid: str) -> None:
		"""Process a single record: acquire key, call API, write results."""
		if stop_event.is_set():
			return

		title = str(record.get("Title", ""))
		abstract = str(record.get("Abstract", ""))
		input_text = normalize_record_text(title, abstract)

		if len(input_text) > args.max_chars:
			with file_lock:
				append_jsonl(
					args.truncation_jsonl,
					{
						"PMID": pmid,
						"original_len": len(input_text),
						"truncated_len": args.max_chars,
						"timestamp": utc_now_iso(),
					},
				)
			input_text = input_text[: args.max_chars]
			stats.inc_truncated()

		user_prompt = build_user_prompt(input_text)

		while not stop_event.is_set():
			try:
				api_key = scheduler.acquire_key(timeout=60.0)
			except KeyAcquireTimeoutError:
				continue
			if api_key is None:
				stats.inc_failed()
				with file_lock:
					append_jsonl(
						args.failed_jsonl,
						{
							"PMID": pmid,
							"error_reason": "All API keys exhausted or daily-capped",
							"timestamp": utc_now_iso(),
						},
					)
				print(
					f"[KeyScheduler] No available keys. "
					f"Failing PMID {pmid}. Stopping."
				)
				stop_event.set()
				return

			session = requests.Session()
			try:
				triples, usage = extract_with_retry(
					session=session,
					api_key=api_key,
					model=args.model,
					system_prompt=system_prompt,
					user_prompt=user_prompt,
					max_retries=args.max_retries,
					sleep_sec=args.sleep_sec,
					temperature=args.temperature,
					top_p=args.top_p,
					top_k=args.top_k,
					max_tokens=args.max_tokens,
					timeout_sec=args.timeout_sec,
					thinking_budget_tokens=args.thinking_budget_tokens,
					enable_timing=enable_timing,
				)

				written = 0
				with file_lock:
					for triple in triples:
						append_jsonl(args.output_jsonl, {"PMID": pmid, **triple})
						written += 1
					append_jsonl(
						args.usage_jsonl,
						{
							"PMID": pmid,
							"completion_tokens": int(
								usage.get("completion_tokens", 0) or 0
							),
							"prompt_tokens": int(
								usage.get("prompt_tokens", 0) or 0
							),
							"total_tokens": int(
								usage.get("total_tokens", 0) or 0
							),
							"timestamp": utc_now_iso(),
						},
					)
					append_state_pmid(args.state_file, pmid)

				stats.inc_success(written)

				with count_lock:
					completed_count[0] += 1
					cc = completed_count[0]
				if cc % args.progress_interval == 0 or cc == len(tasks):
					snap = stats.snapshot()
					current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
					print(
						f"Progress {cc}/{len(tasks)} | "
						f"success={snap['success']}, "
						f"failed={snap['failed']}, "
						f"triples={snap['triples']} | "
						f"{scheduler.status_summary()} | "
						f"time={current_time}"
					)

				return  # Done with this record

			except APIFatal429Error:
				scheduler.mark_exhausted(api_key)
				continue  # Try with another key
			except Exception as exc:  # pylint: disable=broad-except
				stats.inc_failed()
				with file_lock:
					append_jsonl(
						args.failed_jsonl,
						{
							"PMID": pmid,
							"error_reason": str(exc),
							"timestamp": utc_now_iso(),
						},
					)
				with count_lock:
					completed_count[0] += 1
				return
			finally:
				scheduler.release_key(api_key)
				session.close()

	# ---- Execute with thread pool ----
	with ThreadPoolExecutor(max_workers=args.worker_count) as executor:
		futures: Dict[Any, str] = {}
		for idx, rec, pid in tasks:
			if stop_event.is_set():
				break
			future = executor.submit(process_record, idx, rec, pid)
			futures[future] = pid

		for future in as_completed(futures):
			try:
				future.result()
			except Exception as exc:
				print(
					f"[Error] Unexpected worker error for "
					f"PMID {futures[future]}: {exc}"
				)
			if stop_event.is_set():
				for f in futures:
					f.cancel()
				break

	return stats


def main() -> None:
	args = parse_args()
	stats = run(args)

	print("\n" + "=" * 72)
	print("Run Finished")
	print("=" * 72)
	print(f"Total records: {stats.total}")
	print(f"Skipped records: {stats.skipped}")
	print(f"Successful records: {stats.success_records}")
	print(f"Failed records: {stats.failed_records}")
	print(f"Truncated records: {stats.truncated_records}")
	print(f"Total triples written: {stats.total_triples}")
	print("=" * 72)


if __name__ == "__main__":
	main()
