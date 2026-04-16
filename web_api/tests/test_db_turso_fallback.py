from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_api.config import get_settings
from web_api.db import _create_conn, is_retryable_turso_connect_error


class DbTursoFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "WEB_DB_LOCAL_ONLY": os.environ.get("WEB_DB_LOCAL_ONLY"),
            "TURSO_DATABASE_URL": os.environ.get("TURSO_DATABASE_URL"),
            "TURSO_AUTH_TOKEN": os.environ.get("TURSO_AUTH_TOKEN"),
            "TURSO_LOCAL_REPLICA_PATH": os.environ.get("TURSO_LOCAL_REPLICA_PATH"),
        }
        os.environ.pop("WEB_DB_LOCAL_ONLY", None)
        os.environ["TURSO_DATABASE_URL"] = "libsql://example.turso.io"
        os.environ["TURSO_AUTH_TOKEN"] = "token"
        os.environ["TURSO_LOCAL_REPLICA_PATH"] = str(Path(self.tmpdir.name) / "replica.db")
        get_settings.cache_clear()

    def tearDown(self) -> None:
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()

    def test_retryable_connect_error_detects_tls_handshake_eof(self) -> None:
        self.assertTrue(
            is_retryable_turso_connect_error(
                ValueError("sync error: http dispatch error: error trying to connect: tls handshake eof")
            )
        )

    def test_create_conn_keeps_local_replica_when_open_sync_temporarily_fails(self) -> None:
        fake_conn = unittest.mock.Mock()
        fake_conn.sync.side_effect = ValueError(
            "sync error: http dispatch error: error trying to connect: tls handshake eof"
        )

        with patch("web_api.db._connect_turso", return_value=fake_conn):
            conn = _create_conn()

        self.assertIs(conn, fake_conn)
        fake_conn.close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
