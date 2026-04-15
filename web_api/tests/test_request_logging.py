from __future__ import annotations

import logging
import unittest

from starlette.requests import Request

from web_api.api.routes import _resolve_client_ip
from web_api.app import _SuppressPollingAccessFilter, _should_suppress_request_log


class RequestLoggingTest(unittest.TestCase):
    def _make_request(self, headers: list[tuple[bytes, bytes]], client: tuple[str, int]) -> Request:
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/v1/public/invites/claim",
                "headers": headers,
                "client": client,
            }
        )

    def test_should_suppress_polling_requests(self) -> None:
        self.assertTrue(_should_suppress_request_log("OPTIONS", "/api/v1/jobs/job_123"))
        self.assertTrue(_should_suppress_request_log("GET", "/api/v1/jobs/job_123"))
        self.assertTrue(_should_suppress_request_log("GET", "/api/v1/jobs/job_123/step1"))
        self.assertFalse(_should_suppress_request_log("GET", "/api/v1/jobs/job_123/render/config"))
        self.assertFalse(_should_suppress_request_log("POST", "/api/v1/jobs/job_123/step1/run"))

    def test_access_log_filter_drops_polling_access_logs(self) -> None:
        log_filter = _SuppressPollingAccessFilter()
        polling_record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='%s - "%s %s HTTP/%s" %s',
            args=("127.0.0.1:12345", "GET", "/api/v1/jobs/job_123", "1.1", 200),
            exc_info=None,
        )
        regular_record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='%s - "%s %s HTTP/%s" %s',
            args=("127.0.0.1:12345", "POST", "/api/v1/jobs/job_123/step1/run", "1.1", 200),
            exc_info=None,
        )

        self.assertFalse(log_filter.filter(polling_record))
        self.assertTrue(log_filter.filter(regular_record))

    def test_resolve_client_ip_prefers_cf_connecting_ip(self) -> None:
        request = self._make_request(
            [
                (b"cf-connecting-ip", b"198.51.100.77"),
                (b"x-forwarded-for", b"203.0.113.9, 10.0.0.1"),
            ],
            ("10.0.0.1", 4321),
        )

        self.assertEqual(_resolve_client_ip(request), "198.51.100.77")

    def test_resolve_client_ip_parses_forwarded_header(self) -> None:
        request = self._make_request(
            [(b"forwarded", b'for="198.51.100.91:443";proto=https;by=203.0.113.43')],
            ("10.0.0.1", 4321),
        )

        self.assertEqual(_resolve_client_ip(request), "198.51.100.91")


if __name__ == "__main__":
    unittest.main()
