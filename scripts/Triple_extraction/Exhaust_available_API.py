"""Classify API keys into exhausted and available groups.

Reads API keys from ``API.txt`` in the current directory, sends a small test
request to Baichuan chat completions API, and writes:

- ``Exhaust.txt``: keys whose response status is 429
- ``Available.txt``: keys whose response status is not 429
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Tuple

import requests


API_URL = "https://api.baichuan-ai.com/v1/chat/completions"
MODEL_NAME = "Baichuan-M3"
TIMEOUT_SEC = 30


def read_api_keys(path: Path) -> List[str]:
    """Load non-empty API keys from file."""
    with path.open("r", encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


def write_api_keys(path: Path, keys: Iterable[str]) -> None:
    """Write one API key per line."""
    path.write_text("\n".join(keys), encoding="utf-8")


def test_api_key(session: requests.Session, api_key: str) -> Tuple[bool, int, str]:
    """Return classification result for a single API key.

    Returns:
        (is_exhausted, status_code, detail)
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Reply with OK."},
        ],
        "stream": False,
        "temperature": 0.1,
        "max_tokens": 8,
    }

    try:
        response = session.post(API_URL, headers=headers, json=payload, timeout=TIMEOUT_SEC)
        detail = response.text[:200].replace("\n", " ").strip()
        return response.status_code == 429, response.status_code, detail
    except requests.RequestException as exc:
        # Network/request errors are treated as unavailable for exhaustion check,
        # so they will not be written into Exhaust.txt unless the server returns 429.
        return False, -1, str(exc)


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    api_file = base_dir / "API.txt"
    exhaust_file = base_dir / "Exhaust.txt"
    available_file = base_dir / "Available.txt"

    if not api_file.exists():
        raise FileNotFoundError(f"API file not found: {api_file}")

    api_keys = read_api_keys(api_file)
    if not api_keys:
        raise ValueError(f"No API keys found in {api_file}")

    exhausted_keys: List[str] = []
    available_keys: List[str] = []

    with requests.Session() as session:
        for index, api_key in enumerate(api_keys, start=1):
            is_exhausted, status_code, detail = test_api_key(session, api_key)
            if is_exhausted:
                exhausted_keys.append(api_key)
                print(f"[{index}/{len(api_keys)}] Exhausted | status={status_code} | key={api_key}")
            else:
                available_keys.append(api_key)
                print(
                    f"[{index}/{len(api_keys)}] Available | status={status_code} | "
                    f"key={api_key} | detail={detail}"
                )

    write_api_keys(exhaust_file, exhausted_keys)
    write_api_keys(available_file, available_keys)

    print("-" * 60)
    print(f"Total keys: {len(api_keys)}")
    print(f"Exhausted keys: {len(exhausted_keys)} -> {exhaust_file}")
    print(f"Available keys: {len(available_keys)} -> {available_file}")


if __name__ == "__main__":
    main()
