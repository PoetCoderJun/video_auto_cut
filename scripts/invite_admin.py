#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import secrets
import string
import sys
from pathlib import Path


STATUS_ACTIVE = "ACTIVE"
STATUS_DISABLED = "DISABLED"
FIELDNAMES = ["code", "credits", "max_uses", "expires_at", "status", "source"]


def generate_code(length: int) -> str:
    alphabet = string.ascii_uppercase + string.digits
    token = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"INV-{token}"


def normalize_code(raw: str) -> str:
    return raw.strip().upper()


def resolve_output_path(args: argparse.Namespace) -> Path:
    raw = (
        str(args.output or "").strip()
        or os.getenv("COUPON_CODE_SHEET_LOCAL_CSV")
        or "./workdir/activation_codes.csv"
    )
    return Path(raw).expanduser().resolve()


def load_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, str]] = []
        for row in reader:
            if not isinstance(row, dict):
                continue
            rows.append({key: str(row.get(key) or "").strip() for key in FIELDNAMES})
        return rows


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: str(row.get(key) or "") for key in FIELDNAMES})


def cmd_template(args: argparse.Namespace) -> int:
    path = resolve_output_path(args)
    if path.exists():
        print(f"csv already exists: {path}")
        return 0
    write_rows(path, [])
    print(f"created csv: {path}")
    print("header: code,credits,max_uses,expires_at,status,source")
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    if args.code is None and args.code_length < 4:
        print("error: --code-length must be >= 4 when auto-generating", file=sys.stderr)
        return 2
    if args.credits <= 0:
        print("error: --credits must be > 0", file=sys.stderr)
        return 2
    if args.max_uses is not None and args.max_uses <= 0:
        print("error: --max-uses must be > 0 when provided", file=sys.stderr)
        return 2

    raw_code = args.code if args.code else generate_code(args.code_length)
    code = normalize_code(raw_code)
    path = resolve_output_path(args)
    rows = load_rows(path)
    new_row = {
        "code": code,
        "credits": str(int(args.credits)),
        "max_uses": "" if args.max_uses is None else str(int(args.max_uses)),
        "expires_at": args.expires_at or "",
        "status": args.status,
        "source": args.source or "",
    }

    existing_idx = -1
    for idx, row in enumerate(rows):
        if normalize_code(str(row.get("code") or "")) == code:
            existing_idx = idx
            break
    if existing_idx >= 0:
        if not args.update:
            print(f"error: code already exists in csv ({code}), use --update to overwrite", file=sys.stderr)
            return 1
        rows[existing_idx] = new_row
    else:
        rows.append(new_row)

    write_rows(path, rows)
    print(f"saved code to csv: {path}")
    print(",".join([new_row[k] for k in FIELDNAMES]))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    path = resolve_output_path(args)
    rows = load_rows(path)
    if not rows:
        print(f"no rows in csv: {path}")
        return 0
    print("\t".join(FIELDNAMES))
    limit = int(args.limit)
    for row in rows[: max(1, limit)]:
        print("\t".join([row.get(k, "") for k in FIELDNAMES]))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage local activation code csv")
    parser.add_argument(
        "--output",
        type=str,
        help="CSV path (default: COUPON_CODE_SHEET_LOCAL_CSV or ./workdir/activation_codes.csv)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    template_parser = subparsers.add_parser("template", help="Create csv with header if missing")
    template_parser.set_defaults(func=cmd_template)

    create_parser = subparsers.add_parser("create", help="Create one activation code into local csv")
    create_parser.add_argument("--code", type=str, help="Custom code; auto-generated when omitted")
    create_parser.add_argument("--code-length", type=int, default=8, help="Auto-generated token length")
    create_parser.add_argument("--credits", type=int, default=20, help="Credits granted by this code")
    create_parser.add_argument("--max-uses", type=int, help="Max successful activations")
    create_parser.add_argument("--expires-at", type=str, help="ISO datetime, e.g. 2026-12-31T23:59:59Z")
    create_parser.add_argument("--source", type=str, help="Channel/source tag, e.g. xhs")
    create_parser.add_argument("--status", choices=[STATUS_ACTIVE, STATUS_DISABLED], default=STATUS_ACTIVE)
    create_parser.add_argument("--update", action="store_true", help="Update existing code row if present")
    create_parser.set_defaults(func=cmd_create)

    list_parser = subparsers.add_parser("list", help="List codes in local csv")
    list_parser.add_argument("--limit", type=int, default=100)
    list_parser.set_defaults(func=cmd_list)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    handler = getattr(args, "func", None)
    if not handler:
        parser.print_help()
        return 2
    return int(handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
