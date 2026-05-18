from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from web_api.config import get_settings
from web_api.db import init_db


class CurrentSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "TURSO_DATABASE_URL": os.environ.get("TURSO_DATABASE_URL"),
            "TURSO_AUTH_TOKEN": os.environ.get("TURSO_AUTH_TOKEN"),
            "WORK_DIR": os.environ.get("WORK_DIR"),
            "TURSO_LOCAL_REPLICA_PATH": os.environ.get("TURSO_LOCAL_REPLICA_PATH"),
        }
        os.environ.pop("TURSO_DATABASE_URL", None)
        os.environ.pop("TURSO_AUTH_TOKEN", None)
        os.environ["WORK_DIR"] = self.tmpdir.name
        os.environ.pop("TURSO_LOCAL_REPLICA_PATH", None)
        get_settings.cache_clear()

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

    def test_init_db_creates_current_schema_and_seed(self) -> None:
        init_db()

        db_path = get_settings().turso_local_replica_path
        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            settings_row = conn.execute(
                "SELECT settings_id, max_claims FROM public_invite_settings"
            ).fetchone()
            email_indexes = {
                row[1]
                for row in conn.execute("PRAGMA index_list(users)").fetchall()
            }

        self.assertTrue(
            {
                "users",
                "coupon_codes",
                "credit_ledger",
                "public_invite_claims",
                "public_invite_settings",
            }.issubset(tables)
        )
        self.assertEqual(settings_row, (1, 50))
        self.assertIn("idx_users_email_ci_unique", email_indexes)


if __name__ == "__main__":
    unittest.main()
