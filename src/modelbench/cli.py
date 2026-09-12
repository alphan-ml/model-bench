"""Command-line entry point.

    modelbench pull-data          # W-A1: pull Banking77, write data/golden.jsonl
    modelbench run --model KEY    # W-A2: run one model against golden.jsonl
    modelbench report             # W-A2: build results.json from outputs/
    modelbench smoke              # W-A2: a fast local pipeline check, no network/secrets

`smoke` runs 20 rows of the real golden set through a FakeProvider (see
providers/fake.py) and writes to .smoke_outputs/, never to outputs/ — it
proves the pipeline works end to end, it does not test any real model.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from modelbench import pull_data, report, runner


def _cmd_pull_data(_args: argparse.Namespace) -> int:
    return pull_data.main()


def _cmd_run(args: argparse.Namespace) -> int:
    if args.limit is not None:
        print(
            f"WARNING: --limit={args.limit} is set. This is a local smoke-test "
            "run, not a real run — its output must never be used for reporting "
            "(SPEC-model-bench.md section 1).",
            file=sys.stderr,
        )
    summary = runner.run(args.model, limit=args.limit)
    print(json.dumps(asdict(summary), indent=2))
    if summary.error_rate > runner.ERROR_RATE_LIMIT:
        print(
            f"FAILED: error rate {summary.error_rate:.1%} exceeds "
            f"{runner.ERROR_RATE_LIMIT:.0%} ({summary.n_errors}/{summary.n_processed})",
            file=sys.stderr,
        )
        return 1
    return 0


def _cmd_report(_args: argparse.Namespace) -> int:
    return report.main()


def _cmd_smoke(_args: argparse.Namespace) -> int:
    from modelbench.providers.fake import FakeProvider

    smoke_out = runner.REPO_ROOT / ".smoke_outputs" / "smoke.jsonl"
    smoke_out.parent.mkdir(parents=True, exist_ok=True)
    if smoke_out.exists():
        smoke_out.unlink()  # each smoke run starts fresh, it is never resumed

    summary = runner.run(
        "smoke-fake",
        model_id="fake-model-v1",
        provider=FakeProvider(),
        limit=20,
        resume=False,
        out_path=smoke_out,
    )
    print(json.dumps(asdict(summary), indent=2))
    if summary.error_rate > runner.ERROR_RATE_LIMIT:
        print(f"SMOKE FAILED: error rate {summary.error_rate:.1%}", file=sys.stderr)
        return 1
    print("SMOKE OK: pipeline ran end-to-end against a fake provider (no network, no secrets).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="modelbench")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("pull-data", help="Pull the Banking77 test split.").set_defaults(
        func=_cmd_pull_data
    )

    run_parser = sub.add_parser("run", help="Run one model against golden.jsonl.")
    run_parser.add_argument("--model", required=True, help="Model key from prices.json")
    run_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Local smoke-test row limit only. Must never be set for a real run.",
    )
    run_parser.set_defaults(func=_cmd_run)

    sub.add_parser("report", help="Build results.json from outputs/*.jsonl.").set_defaults(
        func=_cmd_report
    )
    sub.add_parser(
        "smoke", help="Fast local pipeline check against a fake provider (no network)."
    ).set_defaults(func=_cmd_smoke)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
