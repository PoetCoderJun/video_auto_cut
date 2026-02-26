from __future__ import annotations

import argparse
import logging
import time

from ..config import ensure_work_dirs, get_settings
from ..db import init_db
from ..services.cleanup import cleanup_expired_jobs, cleanup_on_startup
from ..services.tasks import execute_task
from ..task_queue import claim_next_task, get_queue_db_path, init_task_queue_db

def run_worker_loop(*, once: bool = False) -> None:
    settings = get_settings()
    last_cleanup_at = 0.0

    while True:
        now = time.time()
        if settings.cleanup_enabled and now - last_cleanup_at >= settings.cleanup_interval_seconds:
            try:
                cleanup_expired_jobs()
            except Exception:
                logging.exception("[web-worker] periodic cleanup failed")
            last_cleanup_at = now

        try:
            task = claim_next_task()
        except Exception:
            logging.exception("[web-worker] claim next task failed")
            if once:
                raise
            time.sleep(max(1.0, settings.worker_poll_seconds))
            continue
        if not task:
            if once:
                return
            time.sleep(settings.worker_poll_seconds)
            continue

        logging.info("[web-worker] claiming task_id=%s job_id=%s type=%s", task.get("task_id"), task.get("job_id"), task.get("task_type"))
        try:
            execute_task(task)
        except Exception:
            logging.exception("[web-worker] execute task failed")
            if once:
                raise
        if once:
            return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run web_api worker loop")
    parser.add_argument("--once", action="store_true", help="Process one task and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[web-worker] %(levelname)s %(message)s")
    logging.info("[web-worker] starting worker loop queue_path=%s", get_queue_db_path())
    ensure_work_dirs()
    init_db()
    init_task_queue_db()
    try:
        cleanup_on_startup()
    except Exception:
        logging.exception("[web-worker] startup cleanup failed")
    run_worker_loop(once=bool(args.once))


if __name__ == "__main__":
    main()
