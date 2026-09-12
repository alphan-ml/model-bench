"""Command-line entry point.

    modelbench pull-data          # W-A1: pull Banking77, write data/golden.jsonl
    modelbench run --model KEY    # W-A2: run one model against golden.jsonl
    modelbench report             # W-A2: build results.json from outputs/
    modelbench smoke              # W-A2: a fast local smoke test with --limit

Only `pull-data` is implemented as of W-A1. The others are registered here so
`modelbench --help` shows the full intended shape; they raise a clear
"not implemented yet" error until W-A2 lands them.
"""

from __future__ import annotations

import argparse
import sys

from modelbench import pull_data


def _cmd_pull_data(_args: argparse.Namespace) -> int:
    return pull_data.main()


def _not_yet(name: str, task: str):
    def _run(_args: argparse.Namespace) -> int:
        print(f"'{name}' is not implemented yet — it lands in {task}.", file=sys.stderr)
        return 2

    return _run


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
    run_parser.set_defaults(func=_not_yet("run", "W-A2"))

    sub.add_parser("report", help="Build results.json from outputs/*.jsonl.").set_defaults(
        func=_not_yet("report", "W-A2")
    )
    sub.add_parser("smoke", help="Fast local smoke test.").set_defaults(
        func=_not_yet("smoke", "W-A2")
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
