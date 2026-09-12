"""Thin paid-run wrapper around sasb.live.

This is not a second experiment. It locks a local paid report, refuses to
overwrite an existing file, and applies a small default cap. The cells,
reachability join, and honest-pay rule stay in live.py.
"""
from __future__ import annotations

import argparse

from .budget import PaidRunLock, require_fresh_path
from .live import main as live_main
from .runtime.treatments import DEFAULT, PROPOSED


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded paid wrapper for sasb.live")
    parser.add_argument("--provider", choices=("anthropic", "openai"), default="anthropic")
    parser.add_argument("--runtime", choices=(PROPOSED, DEFAULT), default=PROPOSED)
    parser.add_argument("--mode", choices=("worker", "swarm"), default="worker")
    parser.add_argument("--cap-usd", type=float, default=0.50)
    parser.add_argument("--role", choices=("honest", "adversary", "both"), default="both")
    parser.add_argument("--pay-unreachable", action="store_true")
    parser.add_argument("--fake-transport", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--out", default="reports/live-run-paid.json")
    parser.add_argument("--lock", default="reports/live-run.lock")
    args = parser.parse_args(argv)
    require_fresh_path(args.out, force=args.force)
    forwarded = [
        "--provider", args.provider,
        "--runtime", args.runtime,
        "--mode", args.mode,
        "--cap-usd", str(args.cap_usd),
        "--role", args.role,
        "--out", args.out,
    ]
    if args.pay_unreachable:
        forwarded.append("--pay-unreachable")
    if args.fake_transport:
        forwarded.append("--fake-transport")
    with PaidRunLock(args.lock):
        return live_main(forwarded)


if __name__ == "__main__":
    main()
