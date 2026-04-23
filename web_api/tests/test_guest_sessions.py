from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from web_api.config import get_settings
from web_api.db import init_db
from web_api.db_repository import (
    claim_guest_session,
    consume_guest_session_free_use,
    get_guest_session,
    get_guest_session_by_token,
)


class GuestSessionsRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "TURSO_DATABASE_URL": os.environ.get("TURSO_DATABASE_URL"),
            "TURSO_AUTH_TOKEN": os.environ.get("TURSO_AUTH_TOKEN"),
            "TURSO_LOCAL_REPLICA_PATH": os.environ.get("TURSO_LOCAL_REPLICA_PATH"),
            "WORK_DIR": os.environ.get("WORK_DIR"),
        }
        os.environ.pop("TURSO_DATABASE_URL", None)
        os.environ.pop("TURSO_AUTH_TOKEN", None)
        os.environ["TURSO_LOCAL_REPLICA_PATH"] = str(Path(self.tmpdir.name) / "test.db")
        os.environ["WORK_DIR"] = self.tmpdir.name
        get_settings.cache_clear()
        init_db()

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

    def test_same_device_reuses_same_guest_identity_before_consumption(self) -> None:
        first = claim_guest_session(
            ip_address="203.0.113.10",
            user_agent="Mozilla/5.0 test-agent",
            device_fingerprint="device-fingerprint-1",
        )
        second = claim_guest_session(
            ip_address="203.0.113.10",
            user_agent="Mozilla/5.0 test-agent",
            device_fingerprint="device-fingerprint-1",
        )

        self.assertEqual(first["guest_id"], second["guest_id"])
        self.assertNotEqual(first["token"], second["token"])
        self.assertFalse(first["reused_existing"])
        self.assertTrue(second["reused_existing"])

        session = get_guest_session_by_token(second["token"])
        self.assertIsNotNone(session)
        self.assertEqual(session["guest_id"], first["guest_id"])
        self.assertEqual(session["free_uses_remaining"], 1)
        self.assertEqual(session["status"], "ACTIVE")

    def test_consumed_device_cannot_claim_second_free_use(self) -> None:
        claimed = claim_guest_session(
            ip_address="203.0.113.10",
            user_agent="Mozilla/5.0 test-agent",
            device_fingerprint="device-fingerprint-2",
        )
        consume_guest_session_free_use(claimed["guest_id"], "job_guest_once")

        session = get_guest_session(claimed["guest_id"])
        self.assertIsNotNone(session)
        self.assertEqual(session["free_uses_remaining"], 0)
        self.assertEqual(session["status"], "CONSUMED")

        with self.assertRaises(LookupError) as ctx:
            claim_guest_session(
                ip_address="203.0.113.10",
                user_agent="Mozilla/5.0 test-agent",
                device_fingerprint="device-fingerprint-2",
            )

        self.assertEqual(str(ctx.exception), "GUEST_SESSION_INELIGIBLE")


if __name__ == "__main__":
    unittest.main()
