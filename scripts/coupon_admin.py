#!/usr/bin/env python3
from __future__ import annotations

import argparse

from invite_admin import build_parser as build_invite_parser  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage local coupon csv")
    parser.add_argument(
        "rest",
        nargs=argparse.REMAINDER,
        help="Forward args, e.g. create --credits 20 --max-uses 100",
    )
    args = parser.parse_args()

    forward_parser = build_invite_parser()
    forward_args = forward_parser.parse_args(args.rest)
    handler = getattr(forward_args, "func", None)
    if not handler:
        forward_parser.print_help()
        return 2
    return int(handler(forward_args))


if __name__ == "__main__":
    raise SystemExit(main())
