#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import secrets
import string
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from web_api.db import get_conn, init_db


STATUS_ACTIVE = "ACTIVE"
STATUS_DISABLED = "DISABLED"


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        os.environ[key] = value


def _row_get(row: Any, key: str, index: int) -> Any:
    if isinstance(row, (tuple, list)):
        if 0 <= index < len(row):
            return row[index]
        return None
    try:
        return row[key]
    except Exception:
        return None


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_code(raw: str) -> str:
    code = raw.strip().upper()
    if not code:
        raise ValueError("coupon code cannot be empty")
    return code


def generate_code(length: int) -> str:
    alphabet = string.ascii_uppercase + string.digits
    token = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"CPN-{token}"


def _create_one_coupon_in_tx(
    conn: Any,
    *,
    credits: int,
    expires_at: str | None,
    status: str,
    source: str | None,
    code: str,
    now: str,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO coupon_codes(
            code,
            credits,
            used_count,
            expires_at,
            status,
            source,
            created_at,
            updated_at
        )
        VALUES(?, ?, 0, ?, ?, ?, ?, ?)
        """,
        (
            code,
            int(credits),
            expires_at,
            status,
            source,
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def cmd_create(args: argparse.Namespace) -> int:
    if args.credits <= 0:
        print("error: --credits must be > 0", file=sys.stderr)
        return 2
    if args.code is None and args.code_length < 4:
        print("error: --code-length must be >= 4 when auto-generating", file=sys.stderr)
        return 2
    if args.count <= 0:
        print("error: --count must be > 0", file=sys.stderr)
        return 2
    if args.code is not None and args.count > 1:
        print("error: --code cannot be used together with --count > 1", file=sys.stderr)
        return 2

    source = (args.source or "").strip() or None
    created: list[tuple[int, str]] = []

    try:
        with get_conn() as conn:
            for _ in range(int(args.count)):
                now = now_iso()
                if args.code is not None:
                    code = normalize_code(args.code)
                    coupon_id = _create_one_coupon_in_tx(
                        conn,
                        credits=int(args.credits),
                        expires_at=args.expires_at,
                        status=args.status,
                        source=source,
                        code=code,
                        now=now,
                    )
                    created.append((coupon_id, code))
                    continue

                last_error: Exception | None = None
                for _attempt in range(20):
                    try:
                        code = generate_code(args.code_length)
                        coupon_id = _create_one_coupon_in_tx(
                            conn,
                            credits=int(args.credits),
                            expires_at=args.expires_at,
                            status=args.status,
                            source=source,
                            code=code,
                            now=now,
                        )
                        created.append((coupon_id, code))
                        last_error = None
                        break
                    except Exception as exc:
                        last_error = exc
                if last_error is not None:
                    raise last_error
            conn.commit()
    except Exception as exc:
        print(f"error: failed to create coupon ({exc})", file=sys.stderr)
        return 1

    print(f"coupons created: {len(created)}")
    print(f"credits: {int(args.credits)}")
    print(f"status: {args.status}")
    print(f"expires_at: {args.expires_at if args.expires_at else 'NULL'}")
    print(f"source: {source if source else 'NULL'}")
    print("items:")
    print("coupon_id\tcode")
    for coupon_id, code in created:
        print(f"{coupon_id}\t{code}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    if args.limit <= 0:
        print("error: --limit must be > 0", file=sys.stderr)
        return 2

    clauses: list[str] = []
    values: list[Any] = []
    if args.status:
        clauses.append("status = ?")
        values.append(args.status)
    if args.source:
        clauses.append("source = ?")
        values.append(args.source.strip())
    where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    values.append(int(args.limit))

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT coupon_id, code, credits, used_count, expires_at, status, source, created_at
            FROM coupon_codes
            {where_clause}
            ORDER BY coupon_id DESC
            LIMIT ?
            """,
            tuple(values),
        ).fetchall()

    if not rows:
        print("no coupons found")
        return 0

    header = [
        "coupon_id",
        "code",
        "credits",
        "used_count",
        "status",
        "source",
        "expires_at",
        "created_at",
    ]
    print("\t".join(header))
    for row in rows:
        coupon_id = _row_get(row, "coupon_id", 0)
        code = _row_get(row, "code", 1)
        credits = _row_get(row, "credits", 2)
        used_count = _row_get(row, "used_count", 3)
        expires_at = _row_get(row, "expires_at", 4)
        status = _row_get(row, "status", 5)
        source = _row_get(row, "source", 6)
        created_at = _row_get(row, "created_at", 7)
        print(
            "\t".join(
                [
                    str(coupon_id),
                    str(code),
                    str(credits),
                    str(used_count),
                    str(status),
                    str(source if source is not None else ""),
                    str(expires_at if expires_at is not None else ""),
                    str(created_at),
                ]
            )
        )
    return 0


def cmd_disable(args: argparse.Namespace) -> int:
    now = now_iso()
    with get_conn() as conn:
        if args.coupon_id is not None:
            cursor = conn.execute(
                """
                UPDATE coupon_codes
                SET status = ?, updated_at = ?
                WHERE coupon_id = ?
                """,
                (STATUS_DISABLED, now, int(args.coupon_id)),
            )
        else:
            code = normalize_code(args.code)
            cursor = conn.execute(
                """
                UPDATE coupon_codes
                SET status = ?, updated_at = ?
                WHERE code = ?
                """,
                (STATUS_DISABLED, now, code),
            )
        conn.commit()
        affected = int(cursor.rowcount)

    if affected <= 0:
        print("error: coupon not found", file=sys.stderr)
        return 1
    print(f"coupon disabled ({affected} row updated)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Coupon admin tool (Turso)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="Create a coupon")
    create_parser.add_argument("--credits", type=int, required=True, help="Coupon credits")
    create_parser.add_argument("--code", type=str, help="Custom coupon code; auto-generated when omitted")
    create_parser.add_argument("--code-length", type=int, default=10, help="Auto-generated coupon token length")
    create_parser.add_argument("--count", type=int, default=1, help="How many coupons to create")
    create_parser.add_argument("--expires-at", type=str, help="ISO datetime, e.g. 2026-12-31T23:59:59Z")
    create_parser.add_argument("--source", type=str, help="Channel/source tag")
    create_parser.add_argument("--status", choices=[STATUS_ACTIVE, STATUS_DISABLED], default=STATUS_ACTIVE)

    list_parser = subparsers.add_parser("list", help="List coupons")
    list_parser.add_argument("--limit", type=int, default=50, help="Max rows to return")
    list_parser.add_argument("--status", choices=[STATUS_ACTIVE, STATUS_DISABLED], help="Filter by status")
    list_parser.add_argument("--source", type=str, help="Filter by source")

    disable_parser = subparsers.add_parser("disable", help="Disable coupon")
    group = disable_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--coupon-id", type=int)
    group.add_argument("--code", type=str)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    load_env_file(REPO_ROOT / ".env")
    try:
        init_db()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("hint: 请在 .env 配置 TURSO_DATABASE_URL 和 TURSO_AUTH_TOKEN", file=sys.stderr)
        return 1

    if args.command == "create":
        return cmd_create(args)
    if args.command == "list":
        return cmd_list(args)
    if args.command == "disable":
        return cmd_disable(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
