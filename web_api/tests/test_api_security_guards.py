from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from web_api.app import _RequestGuardMiddleware, _SlidingWindowRateLimiter, create_app
from web_api.config import get_settings
from web_api.repository import get_job_files


class ApiSecurityGuardsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "WEB_DB_LOCAL_ONLY": os.environ.get("WEB_DB_LOCAL_ONLY"),
            "TURSO_LOCAL_REPLICA_PATH": os.environ.get("TURSO_LOCAL_REPLICA_PATH"),
            "WORK_DIR": os.environ.get("WORK_DIR"),
            "WEB_AUTH_ENABLED": os.environ.get("WEB_AUTH_ENABLED"),
            "OSS_ENDPOINT": os.environ.get("OSS_ENDPOINT"),
            "OSS_BUCKET": os.environ.get("OSS_BUCKET"),
            "OSS_ACCESS_KEY_ID": os.environ.get("OSS_ACCESS_KEY_ID"),
            "OSS_ACCESS_KEY_SECRET": os.environ.get("OSS_ACCESS_KEY_SECRET"),
            "WEB_PUBLIC_RATE_LIMIT_WINDOW_SECONDS": os.environ.get("WEB_PUBLIC_RATE_LIMIT_WINDOW_SECONDS"),
            "WEB_PUBLIC_INVITE_RATE_LIMIT": os.environ.get("WEB_PUBLIC_INVITE_RATE_LIMIT"),
            "WEB_PUBLIC_COUPON_VERIFY_RATE_LIMIT": os.environ.get("WEB_PUBLIC_COUPON_VERIFY_RATE_LIMIT"),
            "WEB_MAX_JSON_BODY_BYTES": os.environ.get("WEB_MAX_JSON_BODY_BYTES"),
        }
        os.environ["WEB_DB_LOCAL_ONLY"] = "1"
        os.environ["TURSO_LOCAL_REPLICA_PATH"] = str(Path(self.tmpdir.name) / "test.db")
        os.environ["WORK_DIR"] = self.tmpdir.name
        os.environ["WEB_AUTH_ENABLED"] = "0"
        os.environ["OSS_ENDPOINT"] = "https://oss-cn-test.aliyuncs.com"
        os.environ["OSS_BUCKET"] = "bucket-test"
        os.environ["OSS_ACCESS_KEY_ID"] = "key-id"
        os.environ["OSS_ACCESS_KEY_SECRET"] = "key-secret"
        get_settings.cache_clear()

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

    def test_audio_oss_ready_rejects_unexpected_object_key(self) -> None:
        expected_key = "video-auto-cut/asr/job_test/audio_expected.wav"
        wrong_key = "video-auto-cut/asr/job_test/audio_wrong.wav"

        with (
            patch("web_api.api.routes.require_active_user", return_value=None),
            patch(
                "web_api.api.routes.get_presigned_put_url_for_job",
                return_value=("https://example.com/upload", expected_key),
            ),
            TestClient(create_app()) as client,
        ):
            create_resp = client.post("/api/v1/jobs")
            self.assertEqual(create_resp.status_code, 200)
            job_id = create_resp.json()["data"]["job"]["job_id"]

            upload_url_resp = client.post(f"/api/v1/jobs/{job_id}/oss-upload-url")
            self.assertEqual(upload_url_resp.status_code, 200)
            self.assertEqual(upload_url_resp.json()["data"]["object_key"], expected_key)

            files = get_job_files(job_id) or {}
            self.assertEqual(files.get("pending_asr_oss_key"), expected_key)

            ready_resp = client.post(
                f"/api/v1/jobs/{job_id}/audio-oss-ready",
                json={"object_key": wrong_key},
            )
            self.assertEqual(ready_resp.status_code, 409)
            self.assertIn("校验失败", ready_resp.json()["error"]["message"])

            files = get_job_files(job_id) or {}
            self.assertIsNone(files.get("asr_oss_key"))
            self.assertEqual(files.get("pending_asr_oss_key"), expected_key)

    def test_audio_oss_ready_accepts_expected_object_key(self) -> None:
        expected_key = "video-auto-cut/asr/job_test/audio_expected.wav"

        with (
            patch("web_api.api.routes.require_active_user", return_value=None),
            patch(
                "web_api.api.routes.get_presigned_put_url_for_job",
                return_value=("https://example.com/upload", expected_key),
            ),
            TestClient(create_app()) as client,
        ):
            create_resp = client.post("/api/v1/jobs")
            job_id = create_resp.json()["data"]["job"]["job_id"]

            upload_url_resp = client.post(f"/api/v1/jobs/{job_id}/oss-upload-url")
            self.assertEqual(upload_url_resp.status_code, 200)

            ready_resp = client.post(
                f"/api/v1/jobs/{job_id}/audio-oss-ready",
                json={"object_key": expected_key},
            )
            self.assertEqual(ready_resp.status_code, 200)

            files = get_job_files(job_id) or {}
            self.assertEqual(files.get("asr_oss_key"), expected_key)
            self.assertIsNone(files.get("pending_asr_oss_key"))

    def test_public_invite_endpoint_is_rate_limited(self) -> None:
        os.environ["WEB_PUBLIC_RATE_LIMIT_WINDOW_SECONDS"] = "60"
        os.environ["WEB_PUBLIC_INVITE_RATE_LIMIT"] = "2"
        get_settings.cache_clear()

        with (
            patch(
                "web_api.api.routes.claim_public_invite_for_ip",
                return_value={"code": "CPN-TEST", "credits": 1, "already_claimed": False},
            ),
            TestClient(create_app()) as client,
        ):
            first = client.post("/api/v1/public/invites/claim")
            second = client.post("/api/v1/public/invites/claim")
            third = client.post("/api/v1/public/invites/claim")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(third.status_code, 429)
        self.assertEqual(third.json()["error"]["code"], "RATE_LIMITED")

    def test_json_request_body_is_rejected_when_too_large(self) -> None:
        async def run_case() -> tuple[bool, int]:
            called = False
            sent_messages: list[dict[str, object]] = []

            async def app(scope, receive, send):
                nonlocal called
                called = True
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"{}", "more_body": False})

            middleware = _RequestGuardMiddleware(
                app,
                rate_limiter=_SlidingWindowRateLimiter(),
                settings=SimpleNamespace(
                    public_invite_rate_limit=5,
                    public_coupon_verify_rate_limit=30,
                    public_rate_limit_window_seconds=60,
                    max_json_body_bytes=16,
                ),
            )
            scope = {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/public/coupons/verify",
                "raw_path": b"/api/v1/public/coupons/verify",
                "query_string": b"",
                "headers": [(b"content-type", b"application/json")],
                "client": ("127.0.0.1", 1234),
                "scheme": "http",
                "server": ("testserver", 80),
            }
            messages = iter(
                [
                    {"type": "http.request", "body": b'{"code":"CPN-TEST","pad":"1234567890"}', "more_body": False},
                ]
            )

            async def receive():
                return next(messages, {"type": "http.disconnect"})

            async def send(message):
                sent_messages.append(message)

            await middleware(scope, receive, send)
            status = int(sent_messages[0]["status"]) if sent_messages else 0
            return called, status

        called, status = asyncio.run(run_case())
        self.assertFalse(called)
        self.assertEqual(status, 413)
