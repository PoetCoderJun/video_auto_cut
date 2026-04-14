from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_api.config import get_settings
from web_api.constants import TASK_STATUS_RUNNING, TASK_TYPE_STEP1
from web_api.db import get_conn
from web_api.task_queue import (
    claim_next_task,
    enqueue_task,
    get_queue_db_path,
    heartbeat_task,
    init_task_queue_db,
    reclaim_stale_running_tasks,
)


class TaskQueueTest(unittest.TestCase):
    def test_queue_uses_shared_db_connection_storage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            replica_path = str(Path(tmpdir) / "queue.db")
            with patch.dict(
                os.environ,
                {
                    "WEB_DB_LOCAL_ONLY": "1",
                    "TURSO_LOCAL_REPLICA_PATH": replica_path,
                },
                clear=False,
            ):
                get_settings.cache_clear()
                try:
                    init_task_queue_db()
                    task_id = enqueue_task("job_queue_test", TASK_TYPE_STEP1, payload={"hello": "world"})
                    claimed = claim_next_task()

                    self.assertEqual(get_queue_db_path(), str(Path(replica_path).resolve()))
                    self.assertGreater(task_id, 0)
                    self.assertIsNotNone(claimed)
                    self.assertEqual(claimed["task_id"], task_id)
                    self.assertEqual(claimed["job_id"], "job_queue_test")
                    self.assertEqual(claimed["task_type"], TASK_TYPE_STEP1)
                    self.assertEqual(claimed["status"], TASK_STATUS_RUNNING)
                    self.assertEqual(claimed["payload"], {"hello": "world"})
                finally:
                    get_settings.cache_clear()

    def test_stale_task_is_reclaimed_before_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            replica_path = str(Path(tmpdir) / "queue.db")
            with patch.dict(
                os.environ,
                {
                    "WEB_DB_LOCAL_ONLY": "1",
                    "TURSO_LOCAL_REPLICA_PATH": replica_path,
                    "TASK_QUEUE_LEASE_SECONDS": "10",
                },
                clear=False,
            ):
                get_settings.cache_clear()
                try:
                    init_task_queue_db()
                    task_id = enqueue_task("job_stale_queue", TASK_TYPE_STEP1)
                    claimed = claim_next_task()
                    self.assertIsNotNone(claimed)
                    self.assertEqual(claimed["task_id"], task_id)

                    with get_conn() as conn:
                        conn.execute(
                            """
                            UPDATE queue_tasks
                            SET updated_at = ?, worker_id = ?
                            WHERE task_id = ?
                            """,
                            ("2000-01-01T00:00:00Z", str(claimed["worker_id"]), task_id),
                        )
                        conn.commit()

                    reclaimed = reclaim_stale_running_tasks(
                        now=datetime(2020, 1, 1, tzinfo=timezone.utc),
                    )
                    self.assertEqual(reclaimed, 1)

                    reclaimed_claim = claim_next_task()
                    self.assertIsNotNone(reclaimed_claim)
                    self.assertEqual(reclaimed_claim["task_id"], task_id)
                    self.assertEqual(reclaimed_claim["status"], TASK_STATUS_RUNNING)
                finally:
                    get_settings.cache_clear()

    def test_heartbeat_updates_running_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            replica_path = str(Path(tmpdir) / "queue.db")
            with patch.dict(
                os.environ,
                {
                    "WEB_DB_LOCAL_ONLY": "1",
                    "TURSO_LOCAL_REPLICA_PATH": replica_path,
                },
                clear=False,
            ):
                get_settings.cache_clear()
                try:
                    init_task_queue_db()
                    task_id = enqueue_task("job_heartbeat", TASK_TYPE_STEP1)
                    claimed = claim_next_task()
                    self.assertIsNotNone(claimed)

                    with get_conn() as conn:
                        conn.execute(
                            "UPDATE queue_tasks SET updated_at = ? WHERE task_id = ?",
                            ("2000-01-01T00:00:00Z", task_id),
                        )
                        conn.commit()

                    stale_worker_id = "pid-" + str(os.getpid())
                    self.assertFalse(heartbeat_task(task_id, worker_id="other-worker"))
                    self.assertTrue(heartbeat_task(task_id, worker_id=stale_worker_id))

                    with get_conn() as conn:
                        row = conn.execute(
                            "SELECT updated_at FROM queue_tasks WHERE task_id = ? LIMIT 1",
                            (task_id,),
                        ).fetchone()
                    self.assertIsNotNone(row)
                    self.assertNotEqual(str(row[0]), "2000-01-01T00:00:00Z")
                finally:
                    get_settings.cache_clear()

    def test_claim_next_task_does_not_retry_transient_turso_stream_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            replica_path = str(Path(tmpdir) / "queue.db")
            with patch.dict(
                os.environ,
                {
                    "WEB_DB_LOCAL_ONLY": "1",
                    "TURSO_LOCAL_REPLICA_PATH": replica_path,
                },
                clear=False,
            ):
                get_settings.cache_clear()
                try:
                    init_task_queue_db()
                    call_count = {"value": 0}

                    def flaky_get_conn():
                        call_count["value"] += 1

                        @contextmanager
                        def broken_conn():
                            raise ValueError(
                                'Hrana: `api error: `status=404 Not Found, body={"error":"stream not found: retry-test"}``'
                            )
                            yield

                        return broken_conn()

                    with patch("web_api.task_queue.reclaim_stale_running_tasks", return_value=0):
                        with patch("web_api.task_queue.get_conn", side_effect=flaky_get_conn):
                            with patch("web_api.db._is_turso_enabled", return_value=True):
                                with self.assertRaisesRegex(ValueError, "stream not found"):
                                    claim_next_task()

                    self.assertEqual(call_count["value"], 1)
                finally:
                    get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
