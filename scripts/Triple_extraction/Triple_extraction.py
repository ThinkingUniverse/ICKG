"""Batch triple extraction with Baichuan-M3-Plus API.

This script reads PubMed records, uses a markdown prompt template,
extracts triples from title+abstract text, and appends results to JSONL.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import requests


API_URL = "https://api.baichuan-ai.com/v1/chat/completions"


@dataclass
class RunStats:
	total: int = 0
	skipped: int = 0
	success_records: int = 0
	failed_records: int = 0
	total_triples: int = 0
	truncated_records: int = 0


def utc_now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


def load_json_file(path: Path) -> Any:
	with path.open("r", encoding="utf-8-sig") as handle:
		return json.load(handle)


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


def build_system_prompt(template_without_input: str) -> str:
	return (
		f"{template_without_input}\n\n"
		"Hard constraints:\n"
		"1. Only use predefined entity types and predefined relation types from this prompt.\n"
		"2. Output must be a JSON array only; do not add any explanatory text.\n"
	)


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
) -> tuple[str, Dict[str, Any], Dict[str, Any]]:
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

	response = session.post(API_URL, headers=headers, json=payload, timeout=timeout_sec)
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
	thinking = body.get("thinking", {})
	if not isinstance(thinking, dict):
		thinking = {}

	return content, usage, thinking


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
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
	last_thinking: Dict[str, Any] = {}
	last_error = "Unknown error"

	for attempt in range(1, max_retries + 1):
		try:
			model_text, usage, thinking = call_baichuan(
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
			)
			triples = parse_triples_json(model_text)
			last_thinking = thinking
			return triples, {"usage": usage, "thinking": thinking}
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
		description="Use Baichuan-M3-Plus API to generate triple extraction fine-tuning data."
	)
	parser.add_argument(
		"--input_file",
		type=Path,
		default=root / "data/pubmed_output/random_sampling/PubMed_abstract_sampled_5000_1.json",
		help="Input PubMed sampled JSON file.",
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
		help="API config JSON containing api_key.",
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
		default="Baichuan-M3-Plus",
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
		default=2.0,
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
		default=0.2,
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
		default=4096,
		help="Maximum output tokens from API.",
	)
	parser.add_argument(
		"--thinking_budget_tokens",
		type=int,
		default=2000,
		help="Thinking budget tokens; set 0 to disable.",
	)
	parser.add_argument(
		"--timeout_sec",
		type=int,
		default=90,
		help="HTTP request timeout in seconds.",
	)

	return parser.parse_args()


def validate_paths(args: argparse.Namespace) -> None:
	required_files = [args.input_file, args.prompt_file, args.api_config]
	for path in required_files:
		if not path.exists():
			raise FileNotFoundError(f"Required file does not exist: {path}")


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

	api_key = load_api_key(args.api_config)
	raw_prompt = args.prompt_file.read_text(encoding="utf-8")
	prompt_template = sanitize_prompt_template(raw_prompt)
	system_prompt = build_system_prompt(prompt_template)

	records = list(iter_records(load_json_file(args.input_file)))
	stats = RunStats(total=len(records))

	processed_pmids = load_state_pmids(args.state_file)

	print("=" * 72)
	print("Baichuan Triple Extraction")
	print("=" * 72)
	print(f"Input records: {stats.total}")
	print(f"Already processed PMIDs in state: {len(processed_pmids)}")
	print(f"Output JSONL: {args.output_jsonl}")
	print(f"Usage JSONL: {args.usage_jsonl}")
	print(f"Failed JSONL: {args.failed_jsonl}")
	print(f"temperature={args.temperature}, top_p={args.top_p}, top_k={args.top_k}, thinking_budget_tokens={args.thinking_budget_tokens}")
	print("=" * 72)

	session = requests.Session()

	for index, record in enumerate(records, start=1):
		pmid = str(record.get("PMID", "")).strip()
		if not pmid:
			pmid = f"missing_pmid_{index}"

		if pmid in processed_pmids:
			stats.skipped += 1
			continue

		title = str(record.get("Title", ""))
		abstract = str(record.get("Abstract", ""))
		input_text = normalize_record_text(title, abstract)

		if len(input_text) > args.max_chars:
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
			stats.truncated_records += 1

		user_prompt = build_user_prompt(input_text)

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
			)

			written_for_record = 0
			for triple in triples:
				output_item = {"PMID": pmid, **triple}
				append_jsonl(args.output_jsonl, output_item)
				written_for_record += 1

			append_jsonl(
				args.usage_jsonl,
				{
					"PMID": pmid,
					"completion_tokens": int(usage.get("usage", {}).get("completion_tokens", 0) or 0),
					"prompt_tokens": int(usage.get("usage", {}).get("prompt_tokens", 0) or 0),
					"total_tokens": int(usage.get("usage", {}).get("total_tokens", 0) or 0),
					"thinking_budget_tokens": int(args.thinking_budget_tokens or 0),
					"thinking_status": str(usage.get("thinking", {}).get("status", "") or ""),
					"thinking_summary": str(usage.get("thinking", {}).get("summary", "") or ""),
					"timestamp": utc_now_iso(),
				},
			)

			stats.success_records += 1
			stats.total_triples += written_for_record
		except Exception as exc:  # pylint: disable=broad-except
			stats.failed_records += 1
			append_jsonl(
				args.failed_jsonl,
				{
					"PMID": pmid,
					"error_reason": str(exc),
					"timestamp": utc_now_iso(),
				},
			)

		append_state_pmid(args.state_file, pmid)
		processed_pmids.add(pmid)

		if args.sleep_sec > 0:
			time.sleep(args.sleep_sec)

		if index % 20 == 0 or index == stats.total:
			print(
				f"Progress {index}/{stats.total} | "
				f"success={stats.success_records}, "
				f"failed={stats.failed_records}, "
				f"skipped={stats.skipped}, "
				f"triples={stats.total_triples}"
			)

	session.close()
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
