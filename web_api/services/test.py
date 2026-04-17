from __future__ import annotations

import json
import fcntl
import logging
import math
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from video_auto_cut.editing.chapter_domain import (
    build_document_revision,
    canonicalize_test_chapters,
    ensure_full_block_coverage,
    format_block_range,
    kept_test_lines,
    parse_block_range,
)
from video_auto_cut.editing.llm_client import build_llm_config
from video_auto_cut.asr.oss_uploader import create_oss_uploader_from_config
from video_auto_cut.asr.transcribe_stage import run_asr_transcription_stage
from video_auto_cut.orchestration.pipeline_options_builder import build_pipeline_options_from_settings
from video_auto_cut.orchestration.pipeline_service import run_auto_edit
from video_auto_cut.pi_agent_runner import TestPiRequest, run_test_pi
from video_auto_cut.shared.test_text_io import (
    write_final_test_srt,
    write_chapters_text,
    write_test_text,
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
from ..db_repository import get_credit_balance
from ..job_file_repository import (
    get_job_owner_user_id,
    list_test_chapters,
    list_test_lines,
    replace_test_chapters,
    replace_test_lines,
    update_job,
    upsert_job_files,
)


@dataclass(frozen=True)
class TestRunContext:
    dirs: dict[str, Path]
    media_path: Path
    video_path: Path | None
    asr_oss_key: str | None
    options: Any


def generate_test_chapters(
    *,
    output_path: Path,
    kept_lines: list[dict[str, Any]],
    video_path: Path | None = None,
) -> list[dict[str, Any]]:
    options = build_pipeline_options_from_settings(get_settings())
    llm_config = build_llm_config(
        base_url=options.llm_base_url,
        model=options.llm_model,
        api_key=options.llm_api_key,
        timeout=options.llm_timeout,
        temperature=0.0,
        max_tokens=options.llm_max_tokens,
        enable_thinking=False,
    )
    max_chapters, chapter_policy_hint = _resolve_test_chapter_policy(
        kept_lines=kept_lines,
        video_path=video_path,
    )
    artifacts = run_test_pi(
        TestPiRequest(
            task="chapter",
            llm_config=llm_config,
            lines=kept_lines,
            title_max_chars=int(options.topic_title_max_chars),
            max_chapters=max_chapters,
            chapter_policy_hint=chapter_policy_hint,
        )
    )
    chapters = _coerce_test_chapters_to_policy(
        artifacts.chapters,
        kept_lines=kept_lines,
        max_chapters=max_chapters,
    )
    if not chapters:
        raise RuntimeError("test flow generated empty chapter list")
    ensure_full_block_coverage(chapters, total_blocks=len(kept_lines))
    write_chapters_text(chapters, output_path)
    return chapters


def _probe_video_orientation(video_path: Path | None) -> str | None:
    if video_path is None:
        return None
    candidate = Path(video_path)
    if not candidate.exists():
        return None

    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(candidate),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout or "{}")
        streams = payload.get("streams")
        if not isinstance(streams, list) or not streams:
            return None
        stream = streams[0] if isinstance(streams[0], dict) else {}
        width = int(stream.get("width") or 0)
        height = int(stream.get("height") or 0)
        if width <= 0 or height <= 0:
            return None
        if height > width:
            return "portrait"
        if width > height:
            return "landscape"
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, json.JSONDecodeError) as exc:
        logging.info("[web_api] chapter orientation probe skipped for %s: %s", candidate, exc)
    return None


def _resolve_test_chapter_policy(
    *,
    kept_lines: list[dict[str, Any]],
    video_path: Path | None,
) -> tuple[int, str]:
    if not kept_lines:
        raise RuntimeError("kept test lines missing")

    orientation = _probe_video_orientation(video_path)
    layout_cap = 4 if orientation == "portrait" else 6
    density_cap = max(1, math.ceil(len(kept_lines) / 3))
    max_chapters = max(1, min(layout_cap, density_cap))
    if orientation == "portrait":
        return max_chapters, "竖屏视频章节约束"
    if orientation == "landscape":
        return max_chapters, "横屏视频章节约束"
    return max_chapters, "当前视频章节约束"


def _chapter_text_length(lines: list[dict[str, Any]]) -> int:
    total = 0
    for line in lines:
        text = str(line.get("optimized_text") or line.get("original_text") or "").strip()
        total += len(text)
    return total


def _chapter_metrics(
    chapter: dict[str, Any],
    kept_lines: list[dict[str, Any]],
) -> dict[str, float | int | bool]:
    parsed = parse_block_range(chapter.get("block_range"))
    if parsed is None:
        raise RuntimeError("chapter block_range invalid")
    start_idx, end_idx = parsed
    chapter_lines = kept_lines[start_idx - 1 : end_idx]
    if not chapter_lines:
        raise RuntimeError("chapter block_range empty")
    block_count = len(chapter_lines)
    duration = max(0.0, float(chapter_lines[-1]["end"]) - float(chapter_lines[0]["start"]))
    text_length = _chapter_text_length(chapter_lines)
    score = block_count * 100 + text_length * 2 + int(round(duration * 10))
    substantial = block_count >= 2 or duration >= 12.0 or text_length >= 28
    return {
        "block_count": block_count,
        "duration": duration,
        "text_length": text_length,
        "score": score,
        "substantial": substantial,
    }


def _merge_adjacent_chapter_pair(
    chapters: list[dict[str, Any]],
    *,
    left_index: int,
    kept_lines: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    left = chapters[left_index]
    right = chapters[left_index + 1]
    left_metrics = _chapter_metrics(left, kept_lines)
    right_metrics = _chapter_metrics(right, kept_lines)
    keep_right_title = int(right_metrics["score"]) > int(left_metrics["score"])
    merged_title = str((right if keep_right_title else left).get("title") or "").strip() or f"章节{left_index + 1}"
    left_range = parse_block_range(left.get("block_range"))
    right_range = parse_block_range(right.get("block_range"))
    if left_range is None or right_range is None:
        raise RuntimeError("chapter block_range invalid")
    start_value = left_range[0]
    end_value = right_range[1]
    merged = {
        "chapter_id": left_index + 1,
        "title": merged_title,
        "block_range": format_block_range(start_value, end_value),
    }
    next_payload = [dict(item) for item in chapters[:left_index]] + [merged] + [dict(item) for item in chapters[left_index + 2 :]]
    for index, chapter in enumerate(next_payload, start=1):
        chapter["chapter_id"] = index
    return canonicalize_test_chapters(next_payload, kept_lines)


def _coerce_test_chapters_to_policy(
    chapters: list[dict[str, Any]],
    *,
    kept_lines: list[dict[str, Any]],
    max_chapters: int,
) -> list[dict[str, Any]]:
    normalized = canonicalize_test_chapters(chapters, kept_lines)
    while len(normalized) > 1:
        metrics = [_chapter_metrics(chapter, kept_lines) for chapter in normalized]
        weak_indexes = [index for index, item in enumerate(metrics) if not bool(item["substantial"])]
        if len(normalized) <= max_chapters and not weak_indexes:
            break

        candidate_pairs: list[tuple[tuple[int, int, int, int], int]] = []
        for index in range(len(normalized) - 1):
            involves_weak = index in weak_indexes or (index + 1) in weak_indexes
            if weak_indexes and not involves_weak:
                continue
            pair_score = int(metrics[index]["score"]) + int(metrics[index + 1]["score"])
            pair_blocks = int(metrics[index]["block_count"]) + int(metrics[index + 1]["block_count"])
            pair_text = int(metrics[index]["text_length"]) + int(metrics[index + 1]["text_length"])
            rank = (0 if involves_weak else 1, pair_score, pair_blocks, pair_text)
            candidate_pairs.append((rank, index))
        if not candidate_pairs:
            for index in range(len(normalized) - 1):
                pair_score = int(metrics[index]["score"]) + int(metrics[index + 1]["score"])
                pair_blocks = int(metrics[index]["block_count"]) + int(metrics[index + 1]["block_count"])
                pair_text = int(metrics[index]["text_length"]) + int(metrics[index + 1]["text_length"])
                candidate_pairs.append(((1, pair_score, pair_blocks, pair_text), index))
        _, merge_index = min(candidate_pairs, key=lambda item: item[0])
        normalized = _merge_adjacent_chapter_pair(
            normalized,
            left_index=merge_index,
            kept_lines=kept_lines,
        )
    return normalized


class TestJobStateManager:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        self.current_stage_code = "REMOVING_REDUNDANT_LINES"

    def reset_lines(self) -> None:
        replace_test_lines(self.job_id, [])

    def mark_transcribing(self) -> None:
        self._update_running(
            progress=31,
            stage_code="TRANSCRIBING_MEDIA",
            stage_message="正在识别语音并生成字幕...",
        )

    def mark_auto_edit_stage(self, stage_code: str, stage_message: str) -> None:
        self.current_stage_code = stage_code
        progress_by_stage = {
            "REMOVING_REDUNDANT_LINES": 32,
            "POLISHING_EXPRESSION": 34,
        }
        self._update_running(
            progress=progress_by_stage.get(stage_code, 34),
            stage_code=stage_code,
            stage_message=stage_message,
        )

    def sync_preview_lines(self, lines: list[dict[str, object]]) -> None:
        if not lines:
            return
        replace_test_lines(self.job_id, lines)
        first_text = str(lines[0].get("optimized_text") or lines[0].get("original_text") or "").strip()
        logging.info(
            "[web_api] test preview sync job=%s stage=%s line_count=%s first_line=%s",
            self.job_id,
            self.current_stage_code,
            len(lines),
            first_text[:60],
        )

    def sync_raw_lines(self, lines: list[dict[str, Any]]) -> None:
        if not lines:
            return
        replace_test_lines(self.job_id, lines)
        logging.info(
            "[web_api] test flow transcribe done job=%s raw_line_count=%s",
            self.job_id,
            len(lines),
        )

    def sync_final_lines(self, lines: list[dict[str, Any]]) -> None:
        replace_test_lines(self.job_id, lines)

    def sync_chapters(self, chapters: list[dict[str, Any]]) -> None:
        replace_test_chapters(self.job_id, chapters)

    def mark_generating_chapters(self) -> None:
        self._update_running(
            progress=34,
            stage_code="GENERATING_CHAPTERS",
            stage_message="正在生成章节结构...",
        )

    def mark_ready(self) -> None:
        update_job(
            self.job_id,
            status=JOB_STATUS_TEST_READY,
            progress=PROGRESS_TEST_READY,
            stage_code="TEST_READY",
            stage_message="字幕和章节已生成，请确认内容。",
        )

    def _update_running(self, *, progress: int, stage_code: str, stage_message: str) -> None:
        update_job(
            self.job_id,
            status=JOB_STATUS_TEST_RUNNING,
            progress=progress,
            stage_code=stage_code,
            stage_message=stage_message,
        )


def run_test(job_id: str) -> None:
    state = TestJobStateManager(job_id)
    context = _build_test_run_context(job_id)
    state.reset_lines()
    asr_artifacts = _run_test_transcription(context, state)
    srt_path = asr_artifacts.srt_path
    auto_edit_artifacts = _run_test_auto_edit(context, srt_path, state)
    optimized_srt_path = auto_edit_artifacts.optimized_srt_path
    optimized_srt_upload = _upload_optimized_srt_to_oss(job_id, optimized_srt_path)
    lines = list(auto_edit_artifacts.test_lines)
    if not lines:
        raise RuntimeError("test flow produced empty line list")

    state.sync_final_lines(lines)
    chapters, chapters_draft_path = _generate_test_chapters_draft(context, lines, state)
    state.sync_chapters(chapters)
    _persist_test_artifacts(
        job_id,
        srt_path=srt_path,
        optimized_srt_path=optimized_srt_path,
        chapters_draft_path=chapters_draft_path,
        optimized_srt_upload=optimized_srt_upload,
    )
    state.mark_ready()


def _build_test_run_context(job_id: str) -> TestRunContext:
    dirs = ensure_job_dirs(job_id)
    files = _load_required_paths(job_id)
    asr_oss_key = files.get("asr_oss_key")
    video_path = Path(files["video_path"]) if files.get("video_path") else None
    media_path = _resolve_test_media_path(job_id, dirs, files, asr_oss_key)
    logging.info("[web_api] test flow transcribe using: %s", media_path)
    options = build_pipeline_options_from_settings(get_settings())
    logging.info(
        "[web_api] test flow asr backend: %s (enable_words=%s sentence_rule_with_punc=%s)",
        options.asr_backend,
        getattr(options, "asr_dashscope_enable_words", None),
        getattr(options, "asr_dashscope_sentence_rule_with_punc", None),
    )
    _ensure_test_credit(job_id)
    return TestRunContext(
        dirs=dirs,
        media_path=media_path,
        video_path=video_path,
        asr_oss_key=asr_oss_key,
        options=options,
    )


def _resolve_test_media_path(
    job_id: str,
    dirs: dict[str, Path],
    files: dict[str, str],
    asr_oss_key: str | None,
) -> Path:
    if asr_oss_key:
        media_path = dirs["input"] / "audio.mp3"
        logging.info(
            "[web_api] test inputs job=%s asr_oss_key=%s (direct OSS, skip upload)",
            job_id,
            asr_oss_key[:50] + "..." if len(asr_oss_key) > 50 else asr_oss_key,
        )
        return media_path

    media_path = Path(files["audio_path"])
    logging.info(
        "[web_api] test inputs job=%s audio_path=%s video_path=%s",
        job_id,
        files.get("audio_path"),
        files.get("video_path"),
    )
    return media_path


def _ensure_test_credit(job_id: str) -> None:
    owner_user_id = get_job_owner_user_id(job_id)
    if not owner_user_id:
        raise RuntimeError("job owner not found")
    if get_credit_balance(owner_user_id) < 1:
        raise RuntimeError("额度不足，请先兑换邀请码后重试")


def _run_test_transcription(context: TestRunContext, state: TestJobStateManager) -> Any:
    logging.info("[web_api] test flow transcribe start: %s", context.media_path)
    state.mark_transcribing()
    asr_artifacts = run_asr_transcription_stage(
        context.media_path,
        context.options,
        oss_object_key=context.asr_oss_key,
    )
    raw_lines = list(getattr(asr_artifacts, "test_lines", None) or [])
    state.sync_raw_lines(raw_lines)
    return asr_artifacts


def _run_test_auto_edit(
    context: TestRunContext,
    srt_path: Path,
    state: TestJobStateManager,
) -> Any:
    logging.info("[web_api] test flow editor start: %s", srt_path)
    state.mark_auto_edit_stage("REMOVING_REDUNDANT_LINES", "正在判断哪些字幕需要删除...")
    auto_edit_artifacts = run_auto_edit(
        srt_path,
        context.options,
        stage_callback=state.mark_auto_edit_stage,
        preview_callback=state.sync_preview_lines,
    )
    return auto_edit_artifacts


def _generate_test_chapters_draft(
    context: TestRunContext,
    lines: list[dict[str, Any]],
    state: TestJobStateManager,
) -> tuple[list[dict[str, Any]], Path]:
    state.mark_generating_chapters()
    kept_lines = kept_test_lines(lines)
    test_dir = context.dirs["base"] / "test"
    test_dir.mkdir(parents=True, exist_ok=True)
    chapters_draft_path = test_dir / "chapters_draft.txt"
    chapters = generate_test_chapters(
        output_path=chapters_draft_path,
        kept_lines=kept_lines,
        video_path=context.video_path,
    )
    return chapters, chapters_draft_path


def _persist_test_artifacts(
    job_id: str,
    *,
    srt_path: Path,
    optimized_srt_path: Path,
    chapters_draft_path: Path,
    optimized_srt_upload: dict[str, str] | None,
) -> None:
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


def _load_required_paths(job_id: str) -> dict[str, str]:
    from ..job_file_repository import get_job_files

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
