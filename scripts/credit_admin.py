#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from coupon_admin import load_env_file
from web_api.db_repository import ensure_user
from web_api.db import get_conn
from web_api.utils.persistence_helpers import now_iso


def normalize_email(raw: str) -> str:
    email = raw.strip().lower()
    if not email:
        raise ValueError("email cannot be empty")
    return email


def current_balance(conn: Any, user_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(SUM(delta), 0) AS balance FROM credit_ledger WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return int(row["balance"] or 0)


def resolve_user(conn: Any, *, email: str | None, user_id: str | None) -> dict[str, Any]:
    if user_id:
        row = conn.execute(
            """
            SELECT user_id, email, status, activated_at
            FROM users
            WHERE user_id = ?
            LIMIT 1
            """,
            (user_id.strip(),),
        ).fetchone()
        if not row:
            raise LookupError("user not found")
        return {
            "user_id": str(row["user_id"]),
            "email": row["email"],
            "status": row["status"],
            "activated_at": row["activated_at"],
        }

    normalized_email = normalize_email(email or "")
    auth_row = None
    try:
        auth_row = conn.execute(
            """
            SELECT id, email
            FROM "user"
            WHERE lower(email) = ?
            LIMIT 1
            """,
            (normalized_email,),
        ).fetchone()
    except Exception:
        auth_row = None

    if auth_row:
        auth_user_id = str(auth_row["id"] or "").strip()
        if auth_user_id:
            ensure_user(auth_user_id, normalized_email)
            row = conn.execute(
                """
                SELECT user_id, email, status, activated_at
                FROM users
                WHERE user_id = ?
                LIMIT 1
                """,
                (auth_user_id,),
            ).fetchone()
            if row:
                return {
                    "user_id": str(row["user_id"]),
                    "email": row["email"],
                    "status": row["status"],
                    "activated_at": row["activated_at"],
                }

    rows = conn.execute(
        """
        SELECT user_id, email, status, activated_at
        FROM users
        WHERE lower(email) = ?
        ORDER BY updated_at DESC, created_at DESC
        """,
        (normalized_email,),
    ).fetchall()
    if not rows:
        raise LookupError("user not found")
    if len(rows) > 1:
        raise LookupError(
            "multiple users found for this email: "
            + ", ".join(str(row["user_id"]) for row in rows)
        )

    row = rows[0]
    return {
        "user_id": str(row["user_id"]),
        "email": row["email"],
        "status": row["status"],
        "activated_at": row["activated_at"],
    }


def print_user_summary(conn: Any, user: dict[str, Any]) -> None:
    balance = current_balance(conn, str(user["user_id"]))
    print(f"user_id: {user['user_id']}")
    print(f"email: {user.get('email') or 'NULL'}")
    print(f"status: {user.get('status') or 'NULL'}")
    print(f"activated_at: {user.get('activated_at') or 'NULL'}")
    print(f"balance: {balance}")


def cmd_show(args: argparse.Namespace) -> int:
    with get_conn() as conn:
        try:
            user = resolve_user(conn, email=args.email, user_id=args.user_id)
        except LookupError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        print_user_summary(conn, user)
        rows = conn.execute(
            """
            SELECT entry_id, delta, reason, job_id, idempotency_key, created_at
            FROM credit_ledger
            WHERE user_id = ?
            ORDER BY entry_id DESC
            LIMIT ?
            """,
            (str(user["user_id"]), int(args.limit)),
        ).fetchall()

    print("recent_ledger:")
    print("entry_id\tdelta\treason\tjob_id\tidempotency_key\tcreated_at")
    for row in rows:
        print(
            "\t".join(
                [
                    str(row["entry_id"]),
                    str(row["delta"]),
                    str(row["reason"] or ""),
                    str(row["job_id"] or ""),
                    str(row["idempotency_key"] or ""),
                    str(row["created_at"] or ""),
                ]
            )
        )
    if not rows:
        print("(empty)")
    return 0


def cmd_grant(args: argparse.Namespace) -> int:
    credits = int(args.credits)
    if credits <= 0:
        print("error: --credits must be > 0", file=sys.stderr)
        return 2

    reason = (args.reason or "").strip() or "ADMIN_MANUAL_CREDIT"
    idempotency_key = (args.idempotency_key or "").strip()
    if not idempotency_key:
        print("error: --idempotency-key is required", file=sys.stderr)
        return 2

    with get_conn() as conn:
        try:
            user = resolve_user(conn, email=args.email, user_id=args.user_id)
        except LookupError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        before_balance = current_balance(conn, str(user["user_id"]))
        existing = conn.execute(
            """
            SELECT entry_id, user_id, delta, reason, created_at
            FROM credit_ledger
            WHERE idempotency_key = ?
            LIMIT 1
            """,
            (idempotency_key,),
        ).fetchone()
        if existing:
            after_balance = current_balance(conn, str(user["user_id"]))
            print("grant skipped: idempotency key already exists")
            print(f"entry_id: {existing['entry_id']}")
            print(f"user_id: {existing['user_id']}")
            print(f"delta: {existing['delta']}")
            print(f"reason: {existing['reason']}")
            print(f"created_at: {existing['created_at']}")
            print(f"balance_before: {before_balance}")
            print(f"balance_after: {after_balance}")
            return 0

        created_at = now_iso()
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """
            INSERT INTO credit_ledger(user_id, delta, reason, job_id, idempotency_key, created_at)
            VALUES(?, ?, ?, NULL, ?, ?)
            """,
            (
                str(user["user_id"]),
                credits,
                reason,
                idempotency_key,
                created_at,
            ),
        )
        conn.commit()
        after_balance = current_balance(conn, str(user["user_id"]))

    print("grant applied")
    print(f"entry_id: {int(cursor.lastrowid)}")
    print(f"user_id: {user['user_id']}")
    print(f"email: {user.get('email') or 'NULL'}")
    print(f"delta: {credits}")
    print(f"reason: {reason}")
    print(f"idempotency_key: {idempotency_key}")
    print(f"created_at: {created_at}")
    print(f"balance_before: {before_balance}")
    print(f"balance_after: {after_balance}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Credit admin tool (Turso)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    show_parser = subparsers.add_parser("show", help="Show user credit balance and recent ledger")
    show_target = show_parser.add_mutually_exclusive_group(required=True)
    show_target.add_argument("--email", type=str, help="User email")
    show_target.add_argument("--user-id", type=str, help="User ID")
    show_parser.add_argument("--limit", type=int, default=10, help="How many ledger rows to show")

    grant_parser = subparsers.add_parser("grant", help="Grant credits to a user")
    grant_target = grant_parser.add_mutually_exclusive_group(required=True)
    grant_target.add_argument("--email", type=str, help="User email")
    grant_target.add_argument("--user-id", type=str, help="User ID")
    grant_parser.add_argument("--credits", type=int, required=True, help="Credits to add")
    grant_parser.add_argument(
        "--reason",
        type=str,
        default="ADMIN_MANUAL_CREDIT",
        help="Ledger reason",
    )
    grant_parser.add_argument(
        "--idempotency-key",
        type=str,
        required=True,
        help="Unique operation key to avoid duplicate grants",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    load_env_file(REPO_ROOT / ".env")

    try:
        if args.command == "show":
            return cmd_show(args)
        if args.command == "grant":
            return cmd_grant(args)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("hint: 请在 .env 配置 TURSO_DATABASE_URL 和 TURSO_AUTH_TOKEN", file=sys.stderr)
        return 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
