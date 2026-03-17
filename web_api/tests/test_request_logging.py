from __future__ import annotations

import logging
import unittest

from web_api.app import _SuppressPollingAccessFilter, _should_suppress_request_log


class RequestLoggingTest(unittest.TestCase):
    def test_should_suppress_polling_requests(self) -> None:
        self.assertTrue(_should_suppress_request_log("OPTIONS", "/api/v1/jobs/job_123"))
        self.assertTrue(_should_suppress_request_log("GET", "/api/v1/jobs/job_123"))
        self.assertTrue(_should_suppress_request_log("GET", "/api/v1/jobs/job_123/step1"))
        self.assertFalse(_should_suppress_request_log("GET", "/api/v1/jobs/job_123/step2"))
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


if __name__ == "__main__":
    unittest.main()
