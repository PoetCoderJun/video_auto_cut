from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_api.config import get_settings
from web_api.constants import TASK_STATUS_RUNNING, TASK_TYPE_STEP1
from web_api.task_queue import (
    claim_next_task,
    enqueue_task,
    get_queue_db_path,
    init_task_queue_db,
    set_task_succeeded,
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

                    set_task_succeeded(task_id)
                finally:
                    get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
