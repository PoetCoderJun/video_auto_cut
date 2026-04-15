from __future__ import annotations

import fcntl
import logging
from pathlib import Path
from contextlib import contextmanager
from typing import Any

from video_auto_cut.orchestration.pipeline_service import run_auto_edit, run_transcribe
from video_auto_cut.asr.oss_uploader import OSSAudioUploader
from video_auto_cut.editing.chapter_domain import (
    build_document_revision,
    canonicalize_step1_chapters,
    kept_step1_lines,
)

from ..config import ensure_job_dirs, get_settings
from ..constants import (
    DEFAULT_ENCODING,
    JOB_STATUS_STEP1_CONFIRMED,
    JOB_STATUS_STEP1_RUNNING,
    JOB_STATUS_STEP1_READY,
    PROGRESS_STEP1_CONFIRMED,
    PROGRESS_STEP1_READY,
)
from ..repository import (
    get_job_owner_user_id,
    list_step1_chapters,
    list_step1_lines,
    replace_step1_chapters,
    replace_step1_lines,
    update_job,
    upsert_job_files,
)
from ..utils.srt_utils import (
    build_step1_lines_from_srt,
    build_step1_lines_from_json,
    write_final_step1_srt,
    write_step1_json,
    write_topics_json,
)
from .billing import has_available_credits
from .pipeline_options import build_pipeline_options
from .step2 import generate_step1_chapters


def run_step1(job_id: str) -> None:
    dirs = ensure_job_dirs(job_id)
    files = _load_required_paths(job_id)
    asr_oss_key = files.get("asr_oss_key")
    if asr_oss_key:
        media_path = dirs["input"] / "audio.wav"
        logging.info(
            "[web_api] step1 inputs job=%s asr_oss_key=%s (direct OSS, skip upload)",
            job_id,
            asr_oss_key[:50] + "..." if len(asr_oss_key) > 50 else asr_oss_key,
        )
    else:
        media_path = Path(files["audio_path"])
        logging.info(
            "[web_api] step1 inputs job=%s audio_path=%s video_path=%s",
            job_id,
            files.get("audio_path"),
            files.get("video_path"),
        )
    logging.info("[web_api] step1 transcribe using: %s", media_path)
    options = build_pipeline_options()
    logging.info(
        "[web_api] step1 asr backend: %s (enable_words=%s sentence_rule_with_punc=%s)",
        options.asr_backend,
        getattr(options, "asr_dashscope_enable_words", None),
        getattr(options, "asr_dashscope_sentence_rule_with_punc", None),
    )
    owner_user_id = get_job_owner_user_id(job_id)
    if not owner_user_id:
        raise RuntimeError("job owner not found")
    if not has_available_credits(owner_user_id, required=1):
        raise RuntimeError("额度不足，请先兑换邀请码后重试")

    logging.info("[web_api] step1 transcribe start: %s", media_path)
    update_job(
        job_id,
        status=JOB_STATUS_STEP1_RUNNING,
        progress=31,
        stage_code="TRANSCRIBING_AUDIO",
        stage_message="正在识别语音并生成字幕...",
    )
    srt_path = run_transcribe(media_path, options, oss_object_key=asr_oss_key)

    raw_lines = build_step1_lines_from_srt(srt_path, DEFAULT_ENCODING)
    if raw_lines:
        replace_step1_lines(job_id, raw_lines)
        logging.info(
            "[web_api] step1 transcribe done job=%s raw_line_count=%s",
            job_id,
            len(raw_lines),
        )

    logging.info("[web_api] step1 auto-edit start: %s", srt_path)
    current_stage_code = "REMOVING_REDUNDANT_LINES"

    def push_auto_edit_stage(stage_code: str, stage_message: str) -> None:
        nonlocal current_stage_code
        current_stage_code = stage_code
        progress_by_stage = {
            "REMOVING_REDUNDANT_LINES": 32,
            "MERGING_SHORT_LINES": 33,
            "POLISHING_EXPRESSION": 34,
        }
        update_job(
            job_id,
            status=JOB_STATUS_STEP1_RUNNING,
            progress=progress_by_stage.get(stage_code, 34),
            stage_code=stage_code,
            stage_message=stage_message,
        )

    def push_auto_edit_preview(lines: list[dict[str, object]]) -> None:
        if not lines:
            return
        replace_step1_lines(job_id, lines)
        first_text = str(lines[0].get("optimized_text") or lines[0].get("original_text") or "").strip()
        logging.info(
            "[web_api] step1 preview sync job=%s stage=%s line_count=%s first_line=%s",
            job_id,
            current_stage_code,
            len(lines),
            first_text[:60],
        )

    push_auto_edit_stage("REMOVING_REDUNDANT_LINES", "正在判断哪些字幕需要删除...")
    optimized_srt_path = run_auto_edit(
        srt_path,
        options,
        stage_callback=push_auto_edit_stage,
        preview_callback=push_auto_edit_preview,
    )
    optimized_srt_upload = _upload_optimized_srt_to_oss(job_id, optimized_srt_path)
    step1_lines_path = optimized_srt_path.with_suffix(".step1.json")
    if not step1_lines_path.exists():
        raise RuntimeError(f"step1 sidecar missing: {step1_lines_path}")

    lines = build_step1_lines_from_json(step1_lines_path)
    if not lines:
        raise RuntimeError("step1 produced empty line list")

    replace_step1_lines(job_id, lines)
    update_job(
        job_id,
        status=JOB_STATUS_STEP1_RUNNING,
        progress=34,
        stage_code="GENERATING_CHAPTERS",
        stage_message="正在生成章节结构...",
    )

    kept_lines = kept_step1_lines(lines)
    chapters_draft_path = dirs["step1"] / "chapters_draft.json"
    chapters = generate_step1_chapters(
        source_srt=optimized_srt_path,
        output_path=chapters_draft_path,
        kept_lines=kept_lines,
    )
    replace_step1_chapters(job_id, chapters)

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
        status=JOB_STATUS_STEP1_READY,
        progress=PROGRESS_STEP1_READY,
        stage_code="STEP1_READY",
        stage_message="字幕和章节已生成，请确认内容。",
    )


def _load_required_paths(job_id: str) -> dict[str, str]:
    from ..repository import get_job_files

    files = get_job_files(job_id)
    if not files:
        raise RuntimeError(f"job files not found: {job_id}")
    if not files.get("audio_path") and not files.get("asr_oss_key"):
        raise RuntimeError("upload audio missing for step1 (need audio_path or asr_oss_key)")
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
        uploader = OSSAudioUploader(
            endpoint=settings.asr_oss_endpoint,
            bucket_name=settings.asr_oss_bucket,
            access_key_id=settings.asr_oss_access_key_id,
            access_key_secret=settings.asr_oss_access_key_secret,
            prefix=debug_prefix,
            signed_url_ttl_seconds=int(settings.asr_oss_signed_url_ttl_seconds),
        )
    except Exception as exc:
        logging.warning(
            "[web_api] step1 skip optimized.srt OSS upload job=%s (uploader init failed): %s",
            job_id,
            exc,
        )
        return None

    try:
        uploaded = uploader.upload_audio(optimized_srt_path)
    except Exception as exc:
        logging.warning(
            "[web_api] step1 optimized.srt OSS upload failed job=%s path=%s: %s",
            job_id,
            optimized_srt_path,
            exc,
        )
        return None

    logging.info(
        "[web_api] step1 optimized.srt OSS upload done job=%s key=%s size=%s",
        job_id,
        uploaded.object_key,
        uploaded.size_bytes,
    )
    return {
        "object_key": uploaded.object_key,
        "signed_url": uploaded.signed_url,
    }


def get_step1_document(job_id: str) -> dict[str, Any]:
    lines = list_step1_lines(job_id)
    chapters = list_step1_chapters(job_id)
    return {
        "lines": lines,
        "chapters": chapters,
        "document_revision": build_document_revision(lines, chapters),
    }


def confirm_step1(
    job_id: str,
    updates: list[dict[str, object]],
    chapters: list[dict[str, object]],
    *,
    expected_revision: str,
) -> dict[str, Any]:
    dirs = ensure_job_dirs(job_id)
    with _step1_confirm_lock(dirs["step1"] / ".confirm.lock"):
        existing = list_step1_lines(job_id)
        if not existing:
            raise RuntimeError("step1 lines not found")
        existing_chapters = list_step1_chapters(job_id)
        actual_revision = build_document_revision(existing, existing_chapters)
        if str(expected_revision or "").strip() != actual_revision:
            raise RuntimeError("step1 document revision conflict")

        by_id = {int(item["line_id"]): dict(item) for item in existing}
        for item in updates:
            line_id = int(item["line_id"])
            if line_id not in by_id:
                raise RuntimeError(f"invalid line_id: {line_id}")
            by_id[line_id]["optimized_text"] = str(item.get("optimized_text", "")).strip()
            by_id[line_id]["user_final_remove"] = bool(item.get("user_final_remove", False))

        lines = [by_id[key] for key in sorted(by_id)]
        kept_lines = kept_step1_lines(lines)
        normalized_chapters = canonicalize_step1_chapters(chapters, kept_lines)

        final_step1_srt = dirs["step1"] / "final_step1.srt"
        final_step1_json = dirs["step1"] / "final_step1.json"
        final_chapters = dirs["step1"] / "final_chapters.json"
        write_final_step1_srt(lines, final_step1_srt, DEFAULT_ENCODING)
        write_step1_json(lines, final_step1_json)
        write_topics_json(normalized_chapters, final_chapters)

        upsert_job_files(
            job_id,
            final_step1_json_path=str(final_step1_json),
            final_step1_srt_path=str(final_step1_srt),
            final_chapters_path=str(final_chapters),
        )
        update_job(
            job_id,
            status=JOB_STATUS_STEP1_CONFIRMED,
            progress=PROGRESS_STEP1_CONFIRMED,
            stage_code="EXPORT_READY",
            stage_message="字幕和章节已确认，正在准备导出...",
        )
        return {
            "lines": lines,
            "chapters": normalized_chapters,
            "document_revision": build_document_revision(lines, normalized_chapters),
        }


@contextmanager
def _step1_confirm_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
