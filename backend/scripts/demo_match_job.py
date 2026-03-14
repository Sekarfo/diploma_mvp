from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib import error, request


def load_payload(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Payload file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def call_match_job_api(base_url: str, payload: dict) -> dict:
    url = f"{base_url.rstrip('/')}/match-job"
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"API returned HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not connect to API: {exc}") from exc


def rank_change_label(model_rank: int, baseline_rank: int) -> str:
    delta = baseline_rank - model_rank
    if delta > 0:
        return f"up {delta}"
    if delta < 0:
        return f"down {abs(delta)}"
    return "same"


def print_result(result: dict) -> None:
    ranked = result.get("ranked_candidates", [])
    print(f"\nJob: {result.get('job_id', '<unknown>')}")
    print(f"Returned: {len(ranked)} / {result.get('total_candidates', len(ranked))}")
    print("-" * 100)
    print(f"{'M#':>3} {'B#':>3} {'Change':>8} {'Resume':<18} {'Model':>8} {'Base':>8}  {'Headline'}")
    print("-" * 100)
    for item in ranked:
        model_rank = int(item.get("model_rank", 0))
        baseline_rank = int(item.get("baseline_rank", 0))
        change = rank_change_label(model_rank=model_rank, baseline_rank=baseline_rank)
        resume_id = str(item.get("resume_id", ""))
        headline = str(item.get("headline", ""))
        model_score = float(item.get("model_score", 0.0))
        baseline_score = float(item.get("baseline_score", 0.0))
        print(
            f"{model_rank:>3} {baseline_rank:>3} {change:>8} {resume_id:<18} "
            f"{model_score:>8.4f} {baseline_score:>8.4f}  {headline}"
        )
        print(f"      explanation: {item.get('explanation', '')}")
    print("-" * 100)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a local /match-job MVP demo request.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL.")
    parser.add_argument(
        "--request-file",
        default="backend/examples/match_job_request.json",
        help="Path to JSON request payload.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = load_payload(Path(args.request_file))
    result = call_match_job_api(args.base_url, payload)
    print_result(result)


if __name__ == "__main__":
    main()

