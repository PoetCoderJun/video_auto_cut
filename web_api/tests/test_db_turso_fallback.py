from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from web_api.config import get_settings
from web_api.db import (
    _create_conn,
    _is_invalid_local_replica_state_error,
    init_db,
    is_retryable_turso_connect_error,
    is_retryable_turso_error,
)


class DbTursoFallbackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self._original_env = {
            "TURSO_DATABASE_URL": os.environ.get("TURSO_DATABASE_URL"),
            "TURSO_AUTH_TOKEN": os.environ.get("TURSO_AUTH_TOKEN"),
            "TURSO_LOCAL_REPLICA_PATH": os.environ.get("TURSO_LOCAL_REPLICA_PATH"),
        }
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

    def test_retryable_turso_error_requires_turso_marker_for_generic_transient_signals(self) -> None:
        self.assertTrue(is_retryable_turso_error(ValueError("libsql remote returned 503 service unavailable")))
        self.assertFalse(is_retryable_turso_error(ValueError("503 service unavailable")))

    def test_create_conn_keeps_local_replica_when_open_sync_temporarily_fails(self) -> None:
        fake_conn = unittest.mock.Mock()
        fake_conn.sync.side_effect = ValueError(
            "sync error: http dispatch error: error trying to connect: tls handshake eof"
        )

        with patch("web_api.db._connect_turso", return_value=fake_conn):
            conn = _create_conn()

        self.assertIs(conn, fake_conn)
        fake_conn.close.assert_not_called()

    def test_invalid_local_replica_state_is_detected(self) -> None:
        self.assertTrue(
            _is_invalid_local_replica_state_error(
                ValueError("sync error: invalid local state: db file exists but metadata file does not")
            )
        )

    def test_create_conn_resets_invalid_local_replica_state_and_retries(self) -> None:
        fake_conn = unittest.mock.Mock()
        first_exc = ValueError("sync error: invalid local state: db file exists but metadata file does not")

        with patch("web_api.db._connect_turso", side_effect=[first_exc, fake_conn]) as connect_mock, patch(
            "web_api.db._reset_local_replica"
        ) as reset_mock, patch("web_api.db._sync_best_effort") as sync_mock:
            conn = _create_conn()

        self.assertIs(conn, fake_conn)
        self.assertEqual(connect_mock.call_count, 2)
        reset_mock.assert_called_once()
        sync_mock.assert_called_once_with(fake_conn, stage="open", raise_on_error=True)

    def test_init_db_skips_schema_ddl_in_turso_mode(self) -> None:
        fake_conn = unittest.mock.Mock()

        @contextmanager
        def fake_get_conn():
            yield fake_conn

        with patch("web_api.db.get_conn", fake_get_conn), patch(
            "web_api.db.is_turso_enabled", return_value=True
        ), patch("web_api.db.ensure_runtime_schema_ready") as ready_mock, patch(
            "web_api.user_identity.ensure_user_identity_schema"
        ) as identity_mock, patch("web_api.db.ensure_current_schema") as current_schema_mock:
            init_db()

        ready_mock.assert_called_once_with(fake_conn)
        current_schema_mock.assert_not_called()
        identity_mock.assert_not_called()
        fake_conn.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
