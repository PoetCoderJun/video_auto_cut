from __future__ import annotations

import datetime
import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import srt

from .editing import llm_client as llm_utils
from .editing.chapter_domain import canonicalize_test_chapters, kept_test_lines
from .editing.direct_prompts import (
    build_chapter_messages,
    build_delete_messages,
    build_polish_messages,
    summarize_prompt_variant,
)
from .shared.test_text_protocol import (
    parse_chapter_line,
    parse_timed_lines,
    render_chapter_line,
    render_test_line_text,
    render_time_range_tag,
)
from .shared.test_text_io import load_test_lines
from .shared.test_text_io import build_test_lines_from_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_PI_DIR = PROJECT_ROOT / ".pi"
PROJECT_PI_APPEND_SYSTEM = PROJECT_PI_DIR / "APPEND_SYSTEM.md"
REMOVE_TOKEN = "<remove>"
DEFAULT_MAX_LINES = 400
PROJECT_PI_PROVIDER = "vac-llm"
KIMI_CODING_PROVIDER = "kimi-coding"
DEFAULT_KIMI_CODING_MODEL = "k2p5"
DEFAULT_PI_REQUEST_RETRIES = 3
DEFAULT_PI_RETRY_BACKOFF_SECONDS = 1.0
RETRYABLE_PI_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}
RETRYABLE_PI_ERROR_MARKERS = (
    "rate_limit_error",
    "currently overloaded",
    "try again later",
    "too many requests",
    "temporarily unavailable",
    "service unavailable",
    "gateway timeout",
    "timed out",
    "timeout",
)
TestTask = Literal["delete", "polish", "chapter"]


def load_project_pi_system_prompt() -> str:
    text = PROJECT_PI_APPEND_SYSTEM.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"Project PI system prompt is empty: {PROJECT_PI_APPEND_SYSTEM}")
    return text


@dataclass(frozen=True)
class TestPiRequest:
    task: TestTask
    llm_config: dict[str, Any]
    segments: list[dict[str, Any]] = field(default_factory=list)
    lines: list[dict[str, Any]] = field(default_factory=list)
    title_max_chars: int = 6
    max_lines: int = DEFAULT_MAX_LINES
    max_chapters: int | None = None
    chapter_policy_hint: str = ""


@dataclass(frozen=True)
class TestPiArtifacts:
    task: TestTask
    lines: list[dict[str, Any]] = field(default_factory=list)
    chapters: list[dict[str, Any]] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PiTextBridge:
    request: TestPiRequest

    @property
    def task(self) -> TestTask:
        return self.request.task

    def render_input(self) -> str:
        if self.task == "delete":
            return _build_delete_input_text(self.request.segments)
        if self.task == "polish":
            return _build_polish_input_text(self.request.lines)
        return _build_chapter_input_text(self.request.lines)

    def build_messages(self) -> list[dict[str, str]]:
        rendered = self.render_input()
        if self.task == "delete":
            return build_delete_messages(rendered)
        if self.task == "polish":
            return build_polish_messages(rendered)
        return build_chapter_messages(
            rendered,
            title_max_chars=self.request.title_max_chars,
            max_chapters=self.request.max_chapters,
            chapter_policy_hint=self.request.chapter_policy_hint,
        )

    def parse_output(self, text: str) -> TestPiArtifacts:
        if self.task == "delete":
            return TestPiArtifacts(task="delete", lines=_parse_delete_output(text, self.request))
        if self.task == "polish":
            return TestPiArtifacts(task="polish", lines=_parse_polish_output(text, self.request))
        return TestPiArtifacts(
            task="chapter",
            lines=list(self.request.lines),
            chapters=_parse_chapter_output(text, self.request),
        )


def build_pi_command(*, pi_bin: str = "pi", pi_args: list[str] | None = None) -> list[str]:
    return [str(pi_bin), *(pi_args or [])]


def _normalized_url(value: str) -> str:
    return str(value or "").strip().rstrip("/").lower()


def _is_kimi_coding_base_url(value: str) -> bool:
    normalized = _normalized_url(value)
    return normalized.startswith("https://api.kimi.com/coding")


def _resolve_pi_provider(llm_config: dict[str, Any], env: dict[str, str] | None = None) -> str:
    runtime_env = env or os.environ
    provider_override = str(runtime_env.get("PI_PROVIDER") or "").strip().lower()
    if provider_override:
        return provider_override
    base_url = str(llm_config.get("base_url") or runtime_env.get("LLM_BASE_URL") or "").strip()
    model = (
        str(llm_config.get("model") or "").strip()
        or str(runtime_env.get("LLM_MODEL") or "").strip()
    )
    if _is_kimi_coding_base_url(base_url):
        return KIMI_CODING_PROVIDER
    if base_url and model:
        return PROJECT_PI_PROVIDER
    if str(runtime_env.get("KIMI_API_KEY") or runtime_env.get("MOONSHOT_API_KEY") or "").strip():
        return KIMI_CODING_PROVIDER
    return PROJECT_PI_PROVIDER


def _normalize_kimi_coding_model(model: str) -> str:
    value = str(model or "").strip()
    if not value:
        return f"{KIMI_CODING_PROVIDER}/{DEFAULT_KIMI_CODING_MODEL}"
    lowered = value.lower()
    if lowered.startswith(f"{KIMI_CODING_PROVIDER}/"):
        return value
    if lowered in {"kimi-k2.5", "kimi-for-coding", "k2p5"}:
        return f"{KIMI_CODING_PROVIDER}/{DEFAULT_KIMI_CODING_MODEL}"
    if lowered == "kimi-k2-thinking":
        return f"{KIMI_CODING_PROVIDER}/kimi-k2-thinking"
    return f"{KIMI_CODING_PROVIDER}/{value}"


def _resolve_pi_model(llm_config: dict[str, Any], env: dict[str, str] | None = None) -> str:
    runtime_env = env or os.environ
    base_url = str(llm_config.get("base_url") or runtime_env.get("LLM_BASE_URL") or "").strip()
    model = (
        str(runtime_env.get("PI_MODEL") or "").strip()
        or str(llm_config.get("model") or "").strip()
        or str(runtime_env.get("LLM_MODEL") or "").strip()
    )
    if _resolve_pi_provider(llm_config, runtime_env) == KIMI_CODING_PROVIDER or _is_kimi_coding_base_url(base_url):
        return _normalize_kimi_coding_model(model)
    if not model:
        raise RuntimeError("LLM model is required for PI execution.")
    if "/" in model:
        return model
    return f"{PROJECT_PI_PROVIDER}/{model}"


def _normalize_line_text(text: str) -> str:
    value = (text or "").strip()
    if value.endswith(("？", "?")):
        return value
    while value and value[-1] in "，。、；：!！.":
        value = value[:-1].rstrip()
    return value


def _canonical_special_placeholder(text: str) -> str:
    value = str(text or "").strip()
    collapsed = re.sub(r"\s+", "", value).lower()
    if collapsed == "<nospeech>":
        return "< no speech >"
    if collapsed == "<lowspeech>":
        return "< low speech >"
    return value


def _is_empty_polish_elision_allowed(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    normalized = re.sub(r"[，。、；：!！？?\s]+", "", value)
    if not normalized:
        return False
    filler_chars = {"嗯", "啊", "呃", "额", "哦", "噢", "唔", "哎", "诶", "欸"}
    return all(char in filler_chars for char in normalized)


def _time_range_tag(start: float, end: float) -> str:
    return render_time_range_tag(start, end)


def _time_range_key(start: float, end: float) -> tuple[int, int]:
    return (
        int(round(float(start) * 1000.0)),
        int(round(float(end) * 1000.0)),
    )


def _delete_output_text_matches(original_text: str, candidate_text: str) -> bool:
    if _canonical_special_placeholder(candidate_text) == _canonical_special_placeholder(original_text):
        return True
    return _normalize_line_text(candidate_text) == _normalize_line_text(original_text)


def _render_test_line(*, start: float, end: float, text: str, remove: bool) -> str:
    return render_test_line_text(start=start, end=end, text=text, remove=remove)


def _build_delete_input_text(segments: list[dict[str, Any]]) -> str:
    return "\n".join(
        _render_test_line(
            start=float(segment.get("start") or 0.0),
            end=float(segment.get("end") or 0.0),
            text=str(segment.get("text") or "").strip(),
            remove=False,
        )
        for segment in segments
    )


def _build_polish_input_text(lines: list[dict[str, Any]]) -> str:
    return "\n".join(
        _render_test_line(
            start=float(line.get("start") or 0.0),
            end=float(line.get("end") or 0.0),
            text=str(line.get("optimized_text") or line.get("original_text") or "").strip(),
            remove=bool(line.get("user_final_remove", False)),
        )
        for line in lines
    )


def _build_chapter_input_text(lines: list[dict[str, Any]]) -> str:
    kept = kept_test_lines(lines)
    return "\n".join(
        f"【{index}】{str(line.get('optimized_text') or line.get('original_text') or '').strip()}"
        for index, line in enumerate(kept, start=1)
    )


def _render_test_text_from_lines(lines: list[dict[str, Any]]) -> str:
    return "\n".join(
        _render_test_line(
            start=float(line.get("start") or 0.0),
            end=float(line.get("end") or 0.0),
            text=str(line.get("optimized_text") or line.get("original_text") or "").strip(),
            remove=bool(line.get("user_final_remove", False)),
        )
        for line in sorted(lines, key=lambda item: int(item["line_id"]))
    )


def _render_chapters_text(chapters: list[dict[str, Any]]) -> str:
    return "\n".join(
        render_chapter_line(
            block_range=str(chapter.get("block_range") or "").strip(),
            title=str(chapter.get("title") or "").strip(),
        )
        for chapter in sorted(chapters, key=lambda item: int(item.get("chapter_id", 0)))
    )


def _sort_runtime_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = [int(item.get("line_id")) for item in lines]
    if len(seen) != len(set(seen)):
        raise RuntimeError("Duplicate line_id detected in PI output.")
    return sorted((dict(item) for item in lines), key=lambda item: int(item["line_id"]))


def _build_runtime_line(
    *,
    line_id: int,
    start: float,
    end: float,
    original_text: str,
    optimized_text: str | None = None,
    ai_suggest_remove: bool = False,
    user_final_remove: bool | None = None,
) -> dict[str, Any]:
    original = str(original_text or "").strip()
    optimized = str(optimized_text or original).strip() or original
    suggested_remove = bool(ai_suggest_remove)
    final_remove = suggested_remove if user_final_remove is None else bool(user_final_remove)
    return {
        "line_id": int(line_id),
        "start": float(start),
        "end": float(end),
        "original_text": original,
        "optimized_text": optimized,
        "ai_suggest_remove": suggested_remove,
        "user_final_remove": final_remove,
    }


def _require_line_budget(count: int, *, max_lines: int) -> None:
    if count > max_lines:
        raise RuntimeError(
            f"PI runner input exceeds non-chunk budget: {count} lines > {max_lines}. "
            "Use a larger-context model or an explicit non-default overflow path."
        )


def _direct_llm_config(llm_config: dict[str, Any]) -> dict[str, Any]:
    cfg = llm_utils.build_llm_config(
        base_url=str(llm_config.get("base_url") or "").strip() or None,
        model=str(llm_config.get("model") or "").strip() or None,
        api_key=str(llm_config.get("api_key") or "").strip() or None,
        timeout=int(llm_config.get("timeout") or 300),
        temperature=0.0,
        max_tokens=llm_config.get("max_tokens"),
        enable_thinking=False,
    )
    for key in ("request_retries", "retry_backoff_seconds", "repair_retries"):
        if llm_config.get(key) is not None:
            cfg[key] = llm_config.get(key)
    return cfg



def _strip_response_code_fence(text: str) -> str:
    value = str(text or "").strip()
    if not value.startswith("```"):
        return value
    lines = value.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    while lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()



def _run_direct_prompt(*, llm_config: dict[str, Any], messages: list[dict[str, str]]) -> str:
    cfg = _direct_llm_config(llm_config)
    response_text = llm_utils.chat_completion(cfg, messages)
    return _strip_response_code_fence(response_text)



def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_delete_output(text: str, request: TestPiRequest) -> list[dict[str, Any]]:
    expected: dict[tuple[int, int], dict[str, Any]] = {
        _time_range_key(float(segment.get("start") or 0.0), float(segment.get("end") or 0.0)): segment
        for segment in request.segments
    }
    parsed = parse_timed_lines(text)
    seen: set[tuple[int, int]] = set()
    lines: list[dict[str, Any]] = []
    for start, end, remove, body in parsed:
        key = _time_range_key(start, end)
        if key not in expected:
            raise RuntimeError(f"Delete output time range not found in input: {_time_range_tag(start, end)}")
        if key in seen:
            raise RuntimeError(f"Delete output duplicated time range: {_time_range_tag(start, end)}")
        seen.add(key)
        segment = expected[key]
        original_text = str(segment.get("text") or "").strip()
        if not _delete_output_text_matches(original_text, body):
            raise RuntimeError(f"Delete output changed text for {_time_range_tag(start, end)}")
        forced_remove = _canonical_special_placeholder(original_text) in {"< low speech >", "< no speech >"}
        final_remove = bool(remove or forced_remove)
        lines.append(
            _build_runtime_line(
                line_id=int(segment["id"]),
                start=start,
                end=end,
                original_text=original_text,
                ai_suggest_remove=final_remove,
                user_final_remove=final_remove,
            )
        )
    expected_ids = {int(segment["id"]) for segment in request.segments}
    if {line["line_id"] for line in lines} != expected_ids:
        raise RuntimeError("Delete output must cover all input subtitle lines exactly once")
    return _sort_runtime_lines(lines)


def _parse_polish_output(text: str, request: TestPiRequest) -> list[dict[str, Any]]:
    expected: dict[tuple[int, int], dict[str, Any]] = {
        _time_range_key(float(line.get("start") or 0.0), float(line.get("end") or 0.0)): line
        for line in request.lines
    }
    parsed = parse_timed_lines(text)
    seen: set[tuple[int, int]] = set()
    lines: list[dict[str, Any]] = []
    for start, end, remove, body in parsed:
        key = _time_range_key(start, end)
        if key not in expected:
            raise RuntimeError(f"Polish output time range not found in input: {_time_range_tag(start, end)}")
        if key in seen:
            raise RuntimeError(f"Polish output duplicated time range: {_time_range_tag(start, end)}")
        seen.add(key)
        source = dict(expected[key])
        was_removed = bool(source.get("user_final_remove", False))
        if was_removed:
            lines.append(source)
            continue
        if remove:
            source["ai_suggest_remove"] = True
            source["user_final_remove"] = True
            lines.append(source)
            continue
        if not body:
            if _is_empty_polish_elision_allowed(source.get("optimized_text") or source.get("original_text") or ""):
                source["ai_suggest_remove"] = True
                source["user_final_remove"] = True
                lines.append(source)
                continue
            raise RuntimeError(f"Polish output missing text for {_time_range_tag(start, end)}")
        source["optimized_text"] = _normalize_line_text(body)
        lines.append(source)
    expected_ids = {int(line["line_id"]) for line in request.lines}
    if {int(line["line_id"]) for line in lines} != expected_ids:
        raise RuntimeError("Polish output must cover all input subtitle lines exactly once")
    return _sort_runtime_lines(lines)


def _parse_chapter_output(text: str, request: TestPiRequest) -> list[dict[str, Any]]:
    kept = kept_test_lines(request.lines)
    chapters: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        start, end, title = parse_chapter_line(line)
        chapters.append(
            {
                "chapter_id": len(chapters) + 1,
                "title": title,
                "block_range": f"{start}-{end}" if start != end else str(start),
            }
        )
    if not chapters:
        raise RuntimeError("Chapter output missing chapter lines")
    return canonicalize_test_chapters(chapters, kept)


def _run_via_prompt(request: TestPiRequest) -> TestPiArtifacts:
    bridge = PiTextBridge(request)
    input_text = bridge.render_input()
    input_lines_count = len([line for line in input_text.splitlines() if line.strip()])
    start_time = time.time()
    response_text = _run_direct_prompt(
        llm_config=request.llm_config,
        messages=bridge.build_messages(),
    )
    elapsed = time.time() - start_time
    artifacts = bridge.parse_output(response_text)
    output_lines_count = len([line for line in response_text.splitlines() if line.strip()])
    return TestPiArtifacts(
        task=artifacts.task,
        lines=artifacts.lines,
        chapters=artifacts.chapters,
        debug={
            "task": request.task,
            "bridge": "PiTextBridge",
            "runner": summarize_prompt_variant(request.task),
            "elapsed_seconds": round(elapsed, 2),
            "input_lines": input_lines_count,
            "output_lines": output_lines_count,
            "response_text": response_text,
        },
    )


def run_test_pi(request: TestPiRequest) -> TestPiArtifacts:
    if request.task not in {"delete", "polish", "chapter"}:
        raise RuntimeError(f"Unsupported Test PI task: {request.task}")
    if request.task == "delete":
        _require_line_budget(len(request.segments), max_lines=request.max_lines)
        return _run_via_prompt(request)
    _require_line_budget(len(request.lines), max_lines=request.max_lines)
    return _run_via_prompt(request)


def build_subtitles_from_lines(lines: list[dict[str, Any]]) -> list[srt.Subtitle]:
    subtitles: list[srt.Subtitle] = []
    for line in _sort_runtime_lines(lines):
        line_id = int(line["line_id"])
        text = str(line.get("optimized_text") or line.get("original_text") or "").strip()
        if bool(line.get("ai_suggest_remove", False)):
            text = f"{REMOVE_TOKEN}{str(line.get('original_text') or text).strip()}".strip()
        else:
            text = _normalize_line_text(text)
        subtitles.append(
            srt.Subtitle(
                index=line_id,
                start=datetime.timedelta(seconds=float(line.get("start") or 0.0)),
                end=datetime.timedelta(seconds=float(line.get("end") or 0.0)),
                content=text,
            )
        )
    return subtitles


def build_edl_from_lines(lines: list[dict[str, Any]], *, merge_gap_s: float, total_length: float | None) -> list[dict[str, float]]:
    edl: list[dict[str, float]] = []
    for line in _sort_runtime_lines(lines):
        if bool(line.get("ai_suggest_remove", False)):
            continue
        start = float(line.get("start") or 0.0)
        end = float(line.get("end") or 0.0)
        if total_length is not None:
            end = min(total_length, end)
        if end <= start:
            continue
        if not edl:
            edl.append({"start": start, "end": end})
            continue
        if start - edl[-1]["end"] <= merge_gap_s:
            edl[-1]["end"] = max(edl[-1]["end"], end)
        else:
            edl.append({"start": start, "end": end})
    return edl


def main(argv: list[str] | None = None) -> int:
    from .orchestration.test_cli import main as test_cli_main

    return test_cli_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
