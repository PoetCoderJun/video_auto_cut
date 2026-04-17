from __future__ import annotations

import unittest
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

from web_api.db_repository import get_credit_balance, get_recent_credit_ledger, get_user


class _FakeCursor:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[Any]:
        return list(self._rows)


class _FakeConn:
    def __init__(self, rows_by_sql: dict[str, list[Any]]) -> None:
        self._rows_by_sql = rows_by_sql

    def execute(self, sql: str, _params: Any = ()) -> _FakeCursor:
        normalized = " ".join(sql.split())
        return _FakeCursor(self._rows_by_sql.get(normalized, []))


class DbRepositoryTupleRowsTests(unittest.TestCase):
    def test_get_user_accepts_tuple_row(self) -> None:
        conn = _FakeConn(
            {
                "SELECT user_id, email, status, activated_at FROM users WHERE user_id = ?": [
                    ("user-1", "user@example.com", "ACTIVE", "2026-04-17T00:00:00Z")
                ]
            }
        )

        @contextmanager
        def fake_get_conn():
            yield conn

        with patch("web_api.db_repository.get_conn", fake_get_conn):
            user = get_user("user-1")

        self.assertEqual(
            user,
            {
                "user_id": "user-1",
                "email": "user@example.com",
                "status": "ACTIVE",
                "activated_at": "2026-04-17T00:00:00Z",
            },
        )

    def test_get_credit_balance_accepts_tuple_row(self) -> None:
        conn = _FakeConn(
            {
                "SELECT COALESCE(SUM(delta), 0) AS balance FROM credit_ledger WHERE user_id = ?": [
                    (42,)
                ]
            }
        )

        @contextmanager
        def fake_get_conn():
            yield conn

        with patch("web_api.db_repository.get_conn", fake_get_conn):
            balance = get_credit_balance("user-1")

        self.assertEqual(balance, 42)

    def test_get_recent_credit_ledger_accepts_tuple_rows(self) -> None:
        conn = _FakeConn(
            {
                "SELECT entry_id, delta, reason, job_id, idempotency_key, created_at FROM credit_ledger WHERE user_id = ? ORDER BY entry_id DESC LIMIT ?": [
                    (9, -1, "JOB_EXPORT_SUCCESS", "job-1", "job:job-1:export_success", "2026-04-17T00:00:00Z")
                ]
            }
        )

        @contextmanager
        def fake_get_conn():
            yield conn

        with patch("web_api.db_repository.get_conn", fake_get_conn):
            ledger = get_recent_credit_ledger("user-1", limit=1)

        self.assertEqual(
            ledger,
            [
                {
                    "entry_id": 9,
                    "delta": -1,
                    "reason": "JOB_EXPORT_SUCCESS",
                    "job_id": "job-1",
                    "idempotency_key": "job:job-1:export_success",
                    "created_at": "2026-04-17T00:00:00Z",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
