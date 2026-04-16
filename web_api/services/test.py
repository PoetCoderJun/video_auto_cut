from __future__ import annotations

import fcntl
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Any

from video_auto_cut.asr.oss_uploader import create_oss_uploader_from_config
from video_auto_cut.asr.transcribe_stage import run_asr_transcription_stage
from video_auto_cut.orchestration.pipeline_service import run_auto_edit
from video_auto_cut.editing.chapter_domain import (
    build_document_revision,
    canonicalize_test_chapters,
    kept_test_lines,
)

from ..config import ensure_job_dirs, get_settings
from ..constants import (
    DEFAULT_ENCODING,
    JOB_STATUS_TEST_CONFIRMED,
    JOB_STATUS_TEST_RUNNING,
    JOB_STATUS_TEST_READY,
    PROGRESS_TEST_CONFIRMED,
    PROGRESS_TEST_READY,
)
from ..repository import (
    get_job_owner_user_id,
    list_test_chapters,
    list_test_lines,
    replace_test_chapters,
    replace_test_lines,
    update_job,
    upsert_job_files,
)
from ..utils.srt_utils import build_test_lines_from_text, write_chapters_text, write_final_test_srt, write_test_text
from .billing import has_available_credits
from .pipeline_options import build_pipeline_options
from .step2 import generate_test_chapters


def run_test(job_id: str) -> None:
    dirs = ensure_job_dirs(job_id)
    files = _load_required_paths(job_id)
    asr_oss_key = files.get("asr_oss_key")
    replace_test_lines(job_id, [])
    if asr_oss_key:
        media_path = dirs["input"] / "audio.wav"
        logging.info(
            "[web_api] test inputs job=%s asr_oss_key=%s (direct OSS, skip upload)",
            job_id,
            asr_oss_key[:50] + "..." if len(asr_oss_key) > 50 else asr_oss_key,
        )
    else:
        media_path = Path(files["audio_path"])
        logging.info(
            "[web_api] test inputs job=%s audio_path=%s video_path=%s",
            job_id,
            files.get("audio_path"),
            files.get("video_path"),
        )
    logging.info("[web_api] test flow transcribe using: %s", media_path)
    options = build_pipeline_options()
    logging.info(
        "[web_api] test flow asr backend: %s (enable_words=%s sentence_rule_with_punc=%s)",
        options.asr_backend,
        getattr(options, "asr_dashscope_enable_words", None),
        getattr(options, "asr_dashscope_sentence_rule_with_punc", None),
    )
    owner_user_id = get_job_owner_user_id(job_id)
    if not owner_user_id:
        raise RuntimeError("job owner not found")
    if not has_available_credits(owner_user_id, required=1):
        raise RuntimeError("额度不足，请先兑换邀请码后重试")

    logging.info("[web_api] test flow transcribe start: %s", media_path)
    update_job(
        job_id,
        status=JOB_STATUS_TEST_RUNNING,
        progress=31,
        stage_code="TRANSCRIBING_MEDIA",
        stage_message="正在识别语音并生成字幕...",
    )
    asr_artifacts = run_asr_transcription_stage(
        media_path,
        options,
        oss_object_key=asr_oss_key,
    )
    srt_path = asr_artifacts.srt_path
    raw_lines = getattr(asr_artifacts, "test_lines", None) or getattr(asr_artifacts, "test_lines", None)
    if raw_lines:
        replace_test_lines(job_id, raw_lines)
        logging.info(
            "[web_api] test flow transcribe done job=%s raw_line_count=%s",
            job_id,
            len(raw_lines),
        )

    logging.info("[web_api] test flow editor start: %s", srt_path)
    current_stage_code = "REMOVING_REDUNDANT_LINES"

    def push_auto_edit_stage(stage_code: str, stage_message: str) -> None:
        nonlocal current_stage_code
        current_stage_code = stage_code
        progress_by_stage = {
            "REMOVING_REDUNDANT_LINES": 32,
            "POLISHING_EXPRESSION": 34,
        }
        update_job(
            job_id,
            status=JOB_STATUS_TEST_RUNNING,
            progress=progress_by_stage.get(stage_code, 34),
            stage_code=stage_code,
            stage_message=stage_message,
        )

    def push_auto_edit_preview(lines: list[dict[str, object]]) -> None:
        if not lines:
            return
        replace_test_lines(job_id, lines)
        first_text = str(lines[0].get("optimized_text") or lines[0].get("original_text") or "").strip()
        logging.info(
            "[web_api] test preview sync job=%s stage=%s line_count=%s first_line=%s",
            job_id,
            current_stage_code,
            len(lines),
            first_text[:60],
        )

    push_auto_edit_stage("REMOVING_REDUNDANT_LINES", "正在判断哪些字幕需要删除...")
    auto_edit_artifacts = run_auto_edit(
        srt_path,
        options,
        stage_callback=push_auto_edit_stage,
        preview_callback=push_auto_edit_preview,
    )
    optimized_srt_path = auto_edit_artifacts.optimized_srt_path
    optimized_srt_upload = _upload_optimized_srt_to_oss(job_id, optimized_srt_path)
    test_lines_path = auto_edit_artifacts.test_text_path
    if not test_lines_path.exists():
        raise RuntimeError(f"test sidecar missing: {test_lines_path}")

    lines = list(auto_edit_artifacts.test_lines)
    if not lines:
        raise RuntimeError("test flow produced empty line list")

    replace_test_lines(job_id, lines)
    update_job(
        job_id,
        status=JOB_STATUS_TEST_RUNNING,
        progress=34,
        stage_code="GENERATING_CHAPTERS",
        stage_message="正在生成章节结构...",
    )

    kept_lines = kept_test_lines(lines)
    test_dir = dirs["base"] / "test"
    test_dir.mkdir(parents=True, exist_ok=True)
    chapters_draft_path = test_dir / "chapters_draft.txt"
    chapters = generate_test_chapters(
        source_srt=optimized_srt_path,
        output_path=chapters_draft_path,
        kept_lines=kept_lines,
    )
    replace_test_chapters(job_id, chapters)

    upsert_job_files(
        job_id,
        srt_path=str(srt_path),
        optimized_srt_path=str(optimized_srt_path),
        chapters_draft_path=str(chapters_draft_path),
        optimized_srt_oss_key=(
            optimized_srt_upload.get("object_key") if optimized_srt_upload else None
        ),
        optimized_srt_oss_signed_url=(
            optimized_srt_upload.get("signed_url") if optimized_srt_upload else None
        ),
    )

    update_job(
        job_id,
        status=JOB_STATUS_TEST_READY,
        progress=PROGRESS_TEST_READY,
        stage_code="TEST_READY",
        stage_message="字幕和章节已生成，请确认内容。",
    )


def _load_required_paths(job_id: str) -> dict[str, str]:
    from ..repository import get_job_files

    files = get_job_files(job_id)
    if not files:
        raise RuntimeError(f"job files not found: {job_id}")
    if not files.get("audio_path") and not files.get("asr_oss_key"):
        raise RuntimeError("upload audio missing for test flow (need audio_path or asr_oss_key)")
    return files


def _upload_optimized_srt_to_oss(job_id: str, optimized_srt_path: Path) -> dict[str, str] | None:
    settings = get_settings()
    if not (
        settings.asr_oss_endpoint
        and settings.asr_oss_bucket
        and settings.asr_oss_access_key_id
        and settings.asr_oss_access_key_secret
    ):
        return None

    prefix_base = (settings.asr_oss_prefix or "video-auto-cut/asr").strip().strip("/")
    debug_prefix = f"{prefix_base}/debug/optimized-srt" if prefix_base else "video-auto-cut/asr/debug/optimized-srt"
    try:
        uploader = create_oss_uploader_from_config(settings, prefix=debug_prefix)
    except Exception as exc:
        logging.warning(
            "[web_api] test skip optimized.srt OSS upload job=%s (uploader init failed): %s",
            job_id,
            exc,
        )
        return None

    try:
        uploaded = uploader.upload_audio(optimized_srt_path)
    except Exception as exc:
        logging.warning(
            "[web_api] test optimized.srt OSS upload failed job=%s path=%s: %s",
            job_id,
            optimized_srt_path,
            exc,
        )
        return None

    logging.info(
        "[web_api] test optimized.srt OSS upload done job=%s key=%s size=%s",
        job_id,
        uploaded.object_key,
        uploaded.size_bytes,
    )
    return {
        "object_key": uploaded.object_key,
        "signed_url": uploaded.signed_url,
    }


def get_test_document(job_id: str) -> dict[str, Any]:
    lines = list_test_lines(job_id)
    chapters = list_test_chapters(job_id)
    return {
        "lines": lines,
        "chapters": chapters,
        "document_revision": build_document_revision(lines, chapters),
    }


def confirm_test(
    job_id: str,
    updates: list[dict[str, object]],
    chapters: list[dict[str, object]],
    *,
    expected_revision: str,
) -> dict[str, Any]:
    dirs = ensure_job_dirs(job_id)
    test_dir = dirs["base"] / "test"
    test_dir.mkdir(parents=True, exist_ok=True)
    with _test_confirm_lock(test_dir / ".confirm.lock"):
        existing = list_test_lines(job_id)
        if not existing:
            raise RuntimeError("test lines not found")
        existing_chapters = list_test_chapters(job_id)
        actual_revision = build_document_revision(existing, existing_chapters)
        if str(expected_revision or "").strip() != actual_revision:
            raise RuntimeError("test document revision conflict")

        by_id = {int(item["line_id"]): dict(item) for item in existing}
        for item in updates:
            line_id = int(item["line_id"])
            if line_id not in by_id:
                raise RuntimeError(f"invalid line_id: {line_id}")
            by_id[line_id]["optimized_text"] = str(item.get("optimized_text", "")).strip()
            by_id[line_id]["user_final_remove"] = bool(item.get("user_final_remove", False))

        lines = [by_id[key] for key in sorted(by_id)]
        kept_lines = kept_test_lines(lines)
        normalized_chapters = canonicalize_test_chapters(chapters, kept_lines)

        final_test_srt = test_dir / "final_test.srt"
        final_test_text = test_dir / "final_test.txt"
        final_chapters = test_dir / "final_chapters.txt"
        write_final_test_srt(lines, final_test_srt, DEFAULT_ENCODING)
        write_test_text(lines, final_test_text)
        write_chapters_text(normalized_chapters, final_chapters)

        upsert_job_files(
            job_id,
            final_test_text_path=str(final_test_text),
            final_test_srt_path=str(final_test_srt),
            final_chapters_path=str(final_chapters),
        )
        update_job(
            job_id,
            status=JOB_STATUS_TEST_CONFIRMED,
            progress=PROGRESS_TEST_CONFIRMED,
            stage_code="EXPORT_READY",
            stage_message="字幕和章节已确认，正在准备导出...",
        )
        return {
            "lines": lines,
            "chapters": normalized_chapters,
            "document_revision": build_document_revision(lines, normalized_chapters),
        }


@contextmanager
def _test_confirm_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
