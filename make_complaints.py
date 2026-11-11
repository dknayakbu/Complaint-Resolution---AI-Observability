"""Send a burst of invented complaints and measure their input distribution."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

COMPLAINTS = (
    "I was debited twice for the same purchase, and now I cannot use my "
    "remaining money to pay rent.",
    "A scammer persuaded me to transfer money to a supposedly safe account "
    "and the payment has not been recovered.",
    "My card was charged for an unrecognised purchase and the disputed transaction "
    "is still pending.",
    "A fraud alert blocked my account after I reported a payment that I did not "
    "authorise.",
    "My online transfer went to the wrong recipient and the bank has not explained "
    "how it can be recovered.",
    "I was charged an unexpected overdraft fee after an incoming payment arrived "
    "later than expected.",
    "The mobile app repeatedly rejects my password reset and I cannot view my "
    "statements.",
    "A promised refund for a cancelled card payment has not arrived after several "
    "weeks.",
    "A direct debit was collected twice and I am worried about paying my utility "
    "bills.",
    "I reported a suspicious text message but have received no explanation about "
    "protecting my account.",
)


def request_json(
    api: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 420,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        api + path,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            **(headers or {}),
        },
        method="GET" if payload is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path}: HTTP {error.code}: {detail}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f"{path}: {error}") from error


def submit(api: str, text: str, number: int) -> dict[str, Any]:
    started = time.monotonic()
    result = request_json(
        api,
        "/api/cases",
        payload={"complaint_text": text, "synthetic": True},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    if not isinstance(result, dict) or not isinstance(result.get("case_id"), str):
        raise RuntimeError(f"Complaint {number}: API returned an invalid case")
    print(
        f"Complaint {number}: {result['state']} in {time.monotonic() - started:.1f}s"
        f" (case {result['case_id']})",
        flush=True,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api", default=os.getenv("COPILOT_API_URL", "http://localhost:8000")
    )
    parser.add_argument(
        "--parallel", type=int, default=10, help="Concurrent requests (default: 10)"
    )
    args = parser.parse_args()
    if args.parallel < 1:
        parser.error("--parallel must be at least 1")
    api = args.api.rstrip("/")
    try:
        mode = request_json(api, "/api/mode")
        token = os.getenv("INTERNAL_TOKEN")
        if not token:
            if mode.get("mode") == "fixture":
                token = "fixture-internal-token"
            else:
                token = getpass.getpass("Internal token (for batch drift): ")
        try:
            request_json(
                api,
                "/internal/demo/replay/_check",
                payload={},
                headers={
                    "X-Internal-Token": token,
                    "Idempotency-Key": str(uuid.uuid4()),
                },
            )
        except RuntimeError as error:
            if "HTTP 404" not in str(error):
                raise
        print(
            f"Sending 10 invented complaints, up to {args.parallel} at a time; "
            f"mode: {mode['mode']}. Live calls may incur provider charges.",
            flush=True,
        )
        successes: list[dict[str, Any]] = []
        failures: list[str] = []
        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(submit, api, text, index): index
                for index, text in enumerate(COMPLAINTS, 1)
            }
            for future in as_completed(futures):
                try:
                    successes.append(future.result())
                except (RuntimeError, KeyError) as error:
                    failures.append(f"Complaint {futures[future]}: {error}")
        if failures:
            for failure in failures:
                print(failure, file=sys.stderr)
            raise RuntimeError(
                f"Only {len(successes)}/10 submissions returned a case; "
                "batch drift requires 10 distinct cases."
            )
        drift = request_json(
            api,
            "/internal/demo/batch-drift",
            payload={"case_ids": [case["case_id"] for case in successes]},
            headers={"X-Internal-Token": token, "Idempotency-Key": str(uuid.uuid4())},
        )
        print(
            f"Batch shift: {drift['score_base2_jsd']:.3f} "
            f"(threshold {drift['threshold']:.2f}; "
            f"{drift['reference_count']} reference complaints). "
            "One batch is not a consecutive-window warning.",
            flush=True,
        )
        print("Refresh Grafana after telemetry export and the next Prometheus scrape.")
        return 0
    except (RuntimeError, KeyError, EOFError, KeyboardInterrupt) as error:
        print(f"Batch failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
