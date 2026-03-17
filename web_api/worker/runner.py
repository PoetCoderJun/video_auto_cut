from __future__ import annotations

import argparse
import logging
import threading
import time

from ..config import ensure_work_dirs, get_settings
from ..db import init_db
from ..services.cleanup import cleanup_expired_jobs, cleanup_on_startup
from ..services.tasks import execute_task
from ..task_queue import claim_next_task, get_queue_db_path, heartbeat_task, init_task_queue_db


def _start_heartbeat(task_id: int, worker_id: str, *, interval_seconds: float) -> tuple[threading.Event, threading.Thread]:
    stop_event = threading.Event()

    def run() -> None:
        while not stop_event.wait(max(1.0, interval_seconds)):
            if not heartbeat_task(task_id, worker_id=worker_id):
                logging.debug(
                    "[web-worker] heartbeat skipped or task=%s no longer running",
                    task_id,
                )

    thread = threading.Thread(
        target=run,
        daemon=True,
        name=f"web-worker-heartbeat-{task_id}",
    )
    thread.start()
    return stop_event, thread


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
        worker_id = str(task.get("worker_id") or "")
        task_id = int(task.get("task_id", 0) or 0)
        stop_event = None
        heartbeat_thread: threading.Thread | None = None
        if task_id > 0 and worker_id:
            heartbeat_stop_interval = max(1.0, settings.task_heartbeat_seconds)
            stop_event, heartbeat_thread = _start_heartbeat(task_id, worker_id, interval_seconds=heartbeat_stop_interval)

        try:
            execute_task(task)
        except Exception:
            logging.exception("[web-worker] execute task failed")
            if once:
                raise
        finally:
            if heartbeat_thread is not None and stop_event is not None:
                stop_event.set()
                heartbeat_thread.join(timeout=max(1.0, settings.task_heartbeat_seconds))

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
