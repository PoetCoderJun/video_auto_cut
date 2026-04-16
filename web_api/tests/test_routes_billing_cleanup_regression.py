from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from web_api.app import create_app
from web_api.config import get_settings
from web_api.db import init_db


class BillingRoutesCleanupRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "WEB_DB_LOCAL_ONLY": os.environ.get("WEB_DB_LOCAL_ONLY"),
            "TURSO_LOCAL_REPLICA_PATH": os.environ.get("TURSO_LOCAL_REPLICA_PATH"),
            "WORK_DIR": os.environ.get("WORK_DIR"),
            "WEB_AUTH_ENABLED": os.environ.get("WEB_AUTH_ENABLED"),
        }
        os.environ["WEB_DB_LOCAL_ONLY"] = "1"
        os.environ["TURSO_LOCAL_REPLICA_PATH"] = str(Path(self.tmpdir.name) / "test.db")
        os.environ["WORK_DIR"] = self.tmpdir.name
        os.environ["WEB_AUTH_ENABLED"] = "0"
        get_settings.cache_clear()
        init_db()

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

    def test_me_endpoint_returns_pending_profile_for_local_dev_user(self) -> None:
        with TestClient(create_app()) as client:
            response = client.get("/api/v1/me")

        self.assertEqual(response.status_code, 200)
        user = response.json()["data"]["user"]
        self.assertEqual(user["user_id"], "dev_local_user")
        self.assertEqual(user["status"], "PENDING_COUPON")
        self.assertEqual(user["credits"]["balance"], 0)
        self.assertEqual(user["credits"]["recent_ledger"], [])

    def test_public_coupon_verify_returns_translated_invalid_error(self) -> None:
        with TestClient(create_app()) as client:
            response = client.post("/api/v1/public/coupons/verify", json={"code": "CPN-NOT-FOUND"})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "COUPON_CODE_INVALID")
        self.assertEqual(response.json()["error"]["message"], "邀请码无效，请检查后重试")

    def test_coupon_redeem_returns_translated_invalid_error(self) -> None:
        with TestClient(create_app()) as client:
            response = client.post("/api/v1/auth/coupon/redeem", json={"code": "CPN-NOT-FOUND"})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "COUPON_CODE_INVALID")
        self.assertEqual(response.json()["error"]["message"], "兑换码无效，请检查后重试")


if __name__ == "__main__":
    unittest.main()
