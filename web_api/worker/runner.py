from __future__ import annotations

import argparse
import logging
import time

from video_auto_cut.asr import qwen3_asr

from ..config import ensure_work_dirs, get_settings
from ..db import init_db
from ..services.cleanup import cleanup_expired_jobs, cleanup_on_startup
from ..services.tasks import execute_task
from ..task_queue import claim_next_task, init_task_queue_db


def _prewarm_qwen3_models() -> None:
    settings = get_settings()
    if not settings.qwen3_prewarm_on_startup:
        logging.info("[web-worker] skip qwen3 prewarm (disabled by config)")
        return

    model_id = qwen3_asr.default_model_id(
        settings.qwen3_model,
        "Qwen3-ASR-0.6B",
        qwen3_asr.DEFAULT_ASR_ID,
    )
    aligner_id = qwen3_asr.default_model_id(
        settings.qwen3_aligner,
        "Qwen3-ForcedAligner-0.6B",
        qwen3_asr.DEFAULT_ALIGNER_ID,
    )

    tic = time.time()
    cache_hit = qwen3_asr.prewarm_models(
        model_id=model_id,
        aligner_id=aligner_id,
        device=settings.device,
        offline=True,
        use_modelscope=False,
    )
    elapsed = time.time() - tic
    if cache_hit:
        logging.info("[web-worker] qwen3 model cache already warm (%.1f sec)", elapsed)
    else:
        logging.info("[web-worker] qwen3 model prewarmed at startup (%.1f sec)", elapsed)


def run_worker_loop(*, once: bool = False) -> None:
    settings = get_settings()
    last_cleanup_at = 0.0
    try:
        _prewarm_qwen3_models()
    except Exception:
        logging.exception("[web-worker] startup prewarm failed")

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
