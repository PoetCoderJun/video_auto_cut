from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from web_api.config import get_settings
from web_api.db import get_conn, init_db
from web_api.db_repository import claim_public_coupon_code


class PublicInviteClaimTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "WEB_DB_LOCAL_ONLY": os.environ.get("WEB_DB_LOCAL_ONLY"),
            "TURSO_LOCAL_REPLICA_PATH": os.environ.get("TURSO_LOCAL_REPLICA_PATH"),
            "WORK_DIR": os.environ.get("WORK_DIR"),
        }
        os.environ["WEB_DB_LOCAL_ONLY"] = "1"
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

    def test_same_ip_reuses_existing_code(self) -> None:
        first = claim_public_coupon_code("203.0.113.10", credits=2, source="TEST")
        second = claim_public_coupon_code("203.0.113.10", credits=2, source="TEST")

        self.assertFalse(first["already_claimed"])
        self.assertTrue(second["already_claimed"])
        self.assertEqual(first["code"], second["code"])
        self.assertEqual(first["credits"], 2)
        self.assertEqual(second["credits"], 2)

        with get_conn() as conn:
            claim_count = conn.execute("SELECT COUNT(*) AS total FROM public_invite_claims").fetchone()["total"]
            coupon_count = conn.execute("SELECT COUNT(*) AS total FROM coupon_codes").fetchone()["total"]

        self.assertEqual(claim_count, 1)
        self.assertEqual(coupon_count, 1)

    def test_different_ips_receive_different_codes(self) -> None:
        first = claim_public_coupon_code("203.0.113.10", credits=1, source="TEST")
        second = claim_public_coupon_code("203.0.113.11", credits=1, source="TEST")

        self.assertNotEqual(first["code"], second["code"])

        with get_conn() as conn:
            rows = conn.execute(
                "SELECT code FROM coupon_codes ORDER BY coupon_id ASC"
            ).fetchall()

        self.assertEqual([row["code"] for row in rows], [first["code"], second["code"]])

    def test_same_ip_rotates_claim_when_existing_coupon_is_no_longer_usable(self) -> None:
        first = claim_public_coupon_code("203.0.113.10", credits=2, source="TEST")

        with get_conn() as conn:
            conn.execute(
                """
                UPDATE coupon_codes
                SET used_count = 1, status = 'DISABLED', updated_at = created_at
                WHERE code = ?
                """,
                (first["code"],),
            )
            conn.commit()

        second = claim_public_coupon_code("203.0.113.10", credits=2, source="TEST")

        self.assertTrue(second["already_claimed"])
        self.assertNotEqual(first["code"], second["code"])

        with get_conn() as conn:
            claim_count = conn.execute("SELECT COUNT(*) AS total FROM public_invite_claims").fetchone()["total"]
            coupon_count = conn.execute("SELECT COUNT(*) AS total FROM coupon_codes").fetchone()["total"]
            current_claim = conn.execute(
                "SELECT code FROM public_invite_claims WHERE ip_hash IS NOT NULL LIMIT 1"
            ).fetchone()

        self.assertEqual(claim_count, 1)
        self.assertEqual(coupon_count, 2)
        self.assertEqual(current_claim["code"], second["code"])

    def test_new_claim_stops_after_max_claims(self) -> None:
        with get_conn() as conn:
            conn.execute(
                "UPDATE public_invite_settings SET max_claims = 1, updated_at = created_at WHERE settings_id = 1"
            )
            conn.commit()

        first = claim_public_coupon_code("203.0.113.10", credits=1, source="TEST")
        self.assertFalse(first["already_claimed"])

        with self.assertRaises(LookupError) as ctx:
            claim_public_coupon_code("203.0.113.11", credits=1, source="TEST")
        self.assertEqual(str(ctx.exception), "PUBLIC_INVITE_EXHAUSTED")

        repeat = claim_public_coupon_code("203.0.113.10", credits=1, source="TEST")
        self.assertTrue(repeat["already_claimed"])
        self.assertEqual(repeat["code"], first["code"])

    def test_default_max_claims_row_is_seeded(self) -> None:
        with get_conn() as conn:
            row = conn.execute(
                "SELECT max_claims FROM public_invite_settings WHERE settings_id = 1"
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(int(row["max_claims"]), 50)


if __name__ == "__main__":
    unittest.main()
