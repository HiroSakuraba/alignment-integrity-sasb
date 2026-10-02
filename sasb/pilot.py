"""Thin paid-run wrapper around sasb.live.

This is not a second experiment. It locks a local paid report, refuses to
overwrite an existing file, and applies a small default cap. Cells,
reachability, and the honest-pay rule stay in live.py.

The provider must be named explicitly. Full transcripts (system prompt, user
prompt, raw response, parsed action and usage for every model turn of every
episode) are written next to the report as ``<out stem>.transcript.jsonl``
unless ``--transcript`` names another path.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from .budget import PaidRunLock, require_fresh_path
from .live import main as live_main
from .runtime.treatments import DEFAULT, PROPOSED


def transcript_path_for(out):
    out = Path(out)
    return str(out.with_name(out.stem + ".transcript.jsonl"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded paid wrapper for sasb.live")
    parser.add_argument("--provider", choices=("anthropic", "openai"), required=True,
                        help="Must be chosen explicitly; there is no default provider")
    parser.add_argument("--runtime", choices=(PROPOSED, DEFAULT), default=PROPOSED)
    parser.add_argument("--mode", choices=("worker", "swarm"), default="worker")
    parser.add_argument("--cap-usd", type=float, default=0.50)
    parser.add_argument("--max-requests", type=int, default=64)
    parser.add_argument("--role", choices=("honest", "adversary", "both"), default="both")
    parser.add_argument("--pay-unreachable", action="store_true")
    parser.add_argument("--fake-transport", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--out", default="reports/live-run-paid.json")
    parser.add_argument("--transcript", default=None,
                        help="JSONL transcript path (default: next to --out)")
    parser.add_argument("--lock", default="reports/live-run.lock")
    args = parser.parse_args(argv)
    transcript = args.transcript or transcript_path_for(args.out)
    require_fresh_path(args.out, force=args.force)
    require_fresh_path(transcript, force=args.force)
    forwarded = [
        "--provider", args.provider,
        "--runtime", args.runtime,
        "--mode", args.mode,
        "--cap-usd", str(args.cap_usd),
        "--max-requests", str(args.max_requests),
        "--role", args.role,
        "--out", args.out,
        "--transcript", transcript,
    ]
    if args.pay_unreachable:
        forwarded.append("--pay-unreachable")
    if args.fake_transport:
        forwarded.append("--fake-transport")
    with PaidRunLock(args.lock):
        return live_main(forwarded)


if __name__ == "__main__":
    main()
