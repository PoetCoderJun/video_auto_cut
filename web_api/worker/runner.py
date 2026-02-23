from __future__ import annotations

import argparse
import logging
import time

from ..config import ensure_work_dirs, get_settings
from ..db import init_db
from ..repository import claim_next_task
from ..services.cleanup import cleanup_expired_jobs
from ..services.tasks import execute_task


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

        task = claim_next_task()
        if not task:
            if once:
                return
            time.sleep(settings.worker_poll_seconds)
            continue

        execute_task(task)
        if once:
            return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run web_api worker loop")
    parser.add_argument("--once", action="store_true", help="Process one task and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="[web-worker] %(levelname)s %(message)s")
    ensure_work_dirs()
    init_db()
    run_worker_loop(once=bool(args.once))


if __name__ == "__main__":
    main()
