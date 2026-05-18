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
            "TURSO_DATABASE_URL": os.environ.get("TURSO_DATABASE_URL"),
            "TURSO_AUTH_TOKEN": os.environ.get("TURSO_AUTH_TOKEN"),
            "TURSO_LOCAL_REPLICA_PATH": os.environ.get("TURSO_LOCAL_REPLICA_PATH"),
            "WORK_DIR": os.environ.get("WORK_DIR"),
            "WEB_AUTH_ENABLED": os.environ.get("WEB_AUTH_ENABLED"),
        }
        os.environ.pop("TURSO_DATABASE_URL", None)
        os.environ.pop("TURSO_AUTH_TOKEN", None)
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

    def test_me_endpoint_grants_one_welcome_credit_for_local_dev_user(self) -> None:
        with TestClient(create_app()) as client:
            response = client.get("/api/v1/me")

        self.assertEqual(response.status_code, 200)
        user = response.json()["data"]["user"]
        self.assertEqual(user["user_id"], "dev_local_user")
        self.assertEqual(user["status"], "ACTIVE")
        self.assertEqual(user["credits"]["balance"], 1)
        self.assertEqual(len(user["credits"]["recent_ledger"]), 1)
        self.assertEqual(user["credits"]["recent_ledger"][0]["delta"], 1)
        self.assertEqual(user["credits"]["recent_ledger"][0]["reason"], "WELCOME_CREDIT")

        with TestClient(create_app()) as client:
            repeat = client.get("/api/v1/me")

        self.assertEqual(repeat.status_code, 200)
        repeat_user = repeat.json()["data"]["user"]
        self.assertEqual(repeat_user["credits"]["balance"], 1)
        self.assertEqual(len(repeat_user["credits"]["recent_ledger"]), 1)

    def test_public_coupon_verify_endpoint_is_removed(self) -> None:
        with TestClient(create_app()) as client:
            response = client.post("/api/v1/public/coupons/verify", json={"code": "CPN-NOT-FOUND"})

        self.assertEqual(response.status_code, 404)

    def test_coupon_redeem_returns_translated_invalid_error(self) -> None:
        with TestClient(create_app()) as client:
            response = client.post("/api/v1/auth/coupon/redeem", json={"code": "CPN-NOT-FOUND"})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "COUPON_CODE_INVALID")
        self.assertEqual(response.json()["error"]["message"], "兑换码无效，请检查后重试")


if __name__ == "__main__":
    unittest.main()
