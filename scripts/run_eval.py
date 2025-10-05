#!/usr/bin/env python3
"""CLI entrypoint for running the conversational eval suite."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # pragma: no cover - import side effect
    sys.path.insert(0, str(ROOT))

from tests.eval.test_runner import run_cases_for_cli


def _normalise_pattern(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description="Run multi-turn conversational eval cases")
    parser.add_argument(
        "--pattern",
        default=None,
        help="Glob pattern relative to tests/eval/cases (default: all cases)",
    )
    args = parser.parse_args()

    results = run_cases_for_cli(_normalise_pattern(args.pattern))
    passed = results["passed"]
    failed = results["failed"]
    total = len(passed) + len(failed)

    print(f"PASS {len(passed)} / {total}")
    if failed:
        for failure in failed:
            case = failure.get("case", "<unknown>")
            reason = failure.get("reason")
            print(f"FAIL: {case}")
            if reason:
                print(f"  reason: {reason}")
        print("Artifacts written: .eval_artifacts/<case>/...")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
