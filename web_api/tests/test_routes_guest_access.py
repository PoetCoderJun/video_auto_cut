from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from web_api.app import create_app
from web_api.config import get_settings
from web_api.db import init_db
from web_api.db_repository import get_guest_session, set_guest_session_job
from web_api.job_file_repository import create_job


class GuestRoutesAccessTest(unittest.TestCase):
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
        os.environ["WEB_AUTH_ENABLED"] = "1"
        get_settings.cache_clear()
        init_db()

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

    def test_guest_token_can_create_upload_and_start_job_without_login(self) -> None:
        with (
            patch("web_api.api.routes.run_test_job_background", return_value=None),
            TestClient(create_app()) as client,
        ):
            guest_resp = client.post(
                "/api/v1/public/guest/session",
                json={"device_fingerprint": "guest-route-fingerprint"},
                headers={"user-agent": "Mozilla/5.0 guest-route"},
            )
            self.assertEqual(guest_resp.status_code, 200)
            guest = guest_resp.json()["data"]["guest"]
            headers = {"X-Guest-Token": guest["token"]}

            create_resp = client.post("/api/v1/jobs", json={}, headers=headers)
            self.assertEqual(create_resp.status_code, 200)
            job_id = create_resp.json()["data"]["job"]["job_id"]

            load_resp = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
            self.assertEqual(load_resp.status_code, 200)
            self.assertEqual(load_resp.json()["data"]["job"]["job_id"], job_id)

            upload_resp = client.post(
                f"/api/v1/jobs/{job_id}/audio-upload-local",
                headers=headers,
                files={"audio_file": ("audio.mp3", b"guest audio bytes", "audio/mpeg")},
            )
            self.assertEqual(upload_resp.status_code, 200)
            self.assertEqual(upload_resp.json()["data"]["job"]["status"], "UPLOAD_READY")

            run_resp = client.post(f"/api/v1/jobs/{job_id}/test/run", headers=headers)
            self.assertEqual(run_resp.status_code, 200)
            self.assertTrue(run_resp.json()["data"]["accepted"])
            self.assertEqual(run_resp.json()["data"]["job"]["status"], "TEST_RUNNING")

    def test_guest_render_complete_consumes_free_use_idempotently(self) -> None:
        with TestClient(create_app()) as client:
            guest_resp = client.post(
                "/api/v1/public/guest/session",
                json={"device_fingerprint": "guest-render-fingerprint"},
                headers={"user-agent": "Mozilla/5.0 guest-render"},
            )
            self.assertEqual(guest_resp.status_code, 200)
            guest = guest_resp.json()["data"]["guest"]
            headers = {"X-Guest-Token": guest["token"]}
            owner_user_id = f"guest:{guest['guest_id']}"
            job_id = "job_guest_render_done"

            create_job(job_id, "SUCCEEDED", owner_user_id)
            set_guest_session_job(guest["guest_id"], job_id)

            first = client.post(f"/api/v1/jobs/{job_id}/render/complete", headers=headers)
            second = client.post(f"/api/v1/jobs/{job_id}/render/complete", headers=headers)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["data"]["billing"], {"consumed": True, "balance": 0})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["data"]["billing"], {"consumed": False, "balance": 0})

        session = get_guest_session(guest["guest_id"])
        self.assertIsNotNone(session)
        self.assertEqual(session["status"], "CONSUMED")
        self.assertEqual(session["free_uses_remaining"], 0)


if __name__ == "__main__":
    unittest.main()
