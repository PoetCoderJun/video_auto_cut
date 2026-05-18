from __future__ import annotations

import datetime
import hashlib
import json
import logging
import re
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
    render_chapter_line,
    render_test_line_text,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REMOVE_TOKEN = "<remove>"
DEFAULT_MAX_LINES = 400
DEFAULT_POLISH_CHUNK_SIZE = 25
DEFAULT_POLISH_CONCURRENCY = 1
DIRECT_PROMPT_CACHE_DIR = PROJECT_ROOT / ".cache" / "direct_prompts"
DirectPromptTask = Literal["delete", "polish", "chapter"]


@dataclass(frozen=True)
class TestPromptRequest:
    task: DirectPromptTask
    llm_config: dict[str, Any]
    segments: list[dict[str, Any]] = field(default_factory=list)
    lines: list[dict[str, Any]] = field(default_factory=list)
    title_max_chars: int = 4
    max_lines: int = DEFAULT_MAX_LINES
    polish_chunk_size: int = DEFAULT_POLISH_CHUNK_SIZE
    polish_concurrency: int = DEFAULT_POLISH_CONCURRENCY
    max_chapters: int | None = None
    chapter_policy_hint: str = ""
    script: str = ""


@dataclass(frozen=True)
class TestPromptArtifacts:
    task: DirectPromptTask
    lines: list[dict[str, Any]] = field(default_factory=list)
    chapters: list[dict[str, Any]] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DirectPromptTextBridge:
    request: TestPromptRequest

    @property
    def task(self) -> DirectPromptTask:
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
            return build_delete_messages(rendered, script=self.request.script)
        if self.task == "polish":
            return build_polish_messages(rendered, script=self.request.script)
        return build_chapter_messages(
            rendered,
            title_max_chars=self.request.title_max_chars,
            max_chapters=self.request.max_chapters,
            chapter_policy_hint=self.request.chapter_policy_hint,
        )

    def parse_output(self, text: str) -> TestPromptArtifacts:
        if self.task == "delete":
            return TestPromptArtifacts(task="delete", lines=_parse_delete_output(text, self.request))
        if self.task == "polish":
            return TestPromptArtifacts(task="polish", lines=_parse_polish_output(text, self.request))
        return TestPromptArtifacts(
            task="chapter",
            lines=list(self.request.lines),
            chapters=_parse_chapter_output(text, self.request),
        )


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


def _is_locally_deletable_text(text: str) -> bool:
    value = str(text or "").strip()
    if _canonical_special_placeholder(value) in {"< low speech >", "< no speech >"}:
        return True
    collapsed = re.sub(r"[\s，。！？!?、,.…~～\-—]+", "", value.lower())
    if not collapsed:
        return False
    filler_chars = set("嗯呃额啊呀哎唉诶欸哦噢呐呢吧哈哼呦呣嘛么")
    return all(char in filler_chars for char in collapsed)


def _render_test_line(*, start: float, end: float, text: str, remove: bool) -> str:
    return render_test_line_text(start=start, end=end, text=text, remove=remove)


def _build_delete_input_text(segments: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{int(segment.get('id') or index)}\t{str(segment.get('text') or '').strip()}"
        for index, segment in enumerate(segments, start=1)
        if str(segment.get("text") or "").strip()
        and not _is_locally_deletable_text(str(segment.get("text") or ""))
    )


def _build_polish_input_text(lines: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{int(line.get('line_id') or index)}\t{str(line.get('optimized_text') or line.get('original_text') or '').strip()}"
        for index, line in enumerate(lines, start=1)
        if str(line.get("optimized_text") or line.get("original_text") or "").strip()
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
        raise RuntimeError("Duplicate line_id detected in direct prompt output.")
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
            f"Direct prompt runner input exceeds non-chunk budget: {count} lines > {max_lines}. "
            "Use a larger-context model or an explicit non-default overflow path."
        )


def _direct_llm_config(llm_config: dict[str, Any]) -> dict[str, Any]:
    explicit_enable_thinking = llm_config.get("enable_thinking")
    enable_thinking = explicit_enable_thinking if isinstance(explicit_enable_thinking, bool) else None
    cfg = llm_utils.build_llm_config(
        base_url=str(llm_config.get("base_url") or "").strip() or None,
        model=str(llm_config.get("model") or "").strip() or None,
        api_key=str(llm_config.get("api_key") or "").strip() or None,
        timeout=int(llm_config.get("timeout") or 300),
        temperature=0.0,
        max_tokens=llm_config.get("max_tokens"),
        enable_thinking=enable_thinking,
    )
    for key in ("request_retries", "retry_backoff_seconds", "direct_prompt_cache"):
        if llm_config.get(key) is not None:
            cfg[key] = llm_config.get(key)
    return cfg


def _request_llm_config(request: TestPromptRequest) -> dict[str, Any]:
    cfg = dict(request.llm_config)
    if request.task in {"polish", "chapter"}:
        cfg["enable_thinking"] = False
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


def _direct_prompt_cache_enabled(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("direct_prompt_cache", False))


def _direct_prompt_cache_key(*, cfg: dict[str, Any], messages: list[dict[str, str]]) -> str:
    payload = {
        "cache_version": 2,
        "base_url": str(cfg.get("base_url") or "").strip(),
        "model": str(cfg.get("model") or "").strip(),
        "temperature": cfg.get("temperature"),
        "max_tokens": cfg.get("max_tokens"),
        "enable_thinking": cfg.get("enable_thinking"),
        "messages": messages,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _read_direct_prompt_cache(cache_key: str) -> str | None:
    path = DIRECT_PROMPT_CACHE_DIR / f"{cache_key}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception as exc:
        logging.warning("direct prompt cache read ignored key=%s error=%s", cache_key[:12], exc)
        return None
    response_text = payload.get("response_text") if isinstance(payload, dict) else None
    return response_text if isinstance(response_text, str) else None


def _write_direct_prompt_cache(cache_key: str, response_text: str) -> None:
    try:
        DIRECT_PROMPT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path = DIRECT_PROMPT_CACHE_DIR / f"{cache_key}.json"
        tmp_path = path.with_suffix(f".{time.time_ns()}.tmp")
        tmp_path.write_text(
            json.dumps({"response_text": response_text}, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp_path.replace(path)
    except Exception as exc:
        logging.warning("direct prompt cache write ignored key=%s error=%s", cache_key[:12], exc)


def _run_direct_prompt(*, llm_config: dict[str, Any], messages: list[dict[str, str]]) -> tuple[str, bool, str]:
    cfg = _direct_llm_config(llm_config)
    cache_key = ""
    if _direct_prompt_cache_enabled(cfg):
        cache_key = _direct_prompt_cache_key(cfg=cfg, messages=messages)
        cached = _read_direct_prompt_cache(cache_key)
        if cached is not None:
            logging.info("direct prompt cache hit key=%s model=%s", cache_key[:12], cfg.get("model"))
            return _strip_response_code_fence(cached), True, cache_key
    response_text = llm_utils.chat_completion(cfg, messages)
    stripped = _strip_response_code_fence(response_text)
    return stripped, False, cache_key


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _log_direct_prompt_step_done(debug: dict[str, Any]) -> None:
    elapsed = float(debug.get("elapsed_seconds") or 0.0)
    logging.info(
        "direct prompt step done task=%s elapsed_seconds=%.2f input_lines=%s output_lines=%s cache_hit=%s skipped_model=%s chunked=%s chunk_count=%s runner=%s",
        debug.get("task"),
        elapsed,
        debug.get("input_lines"),
        debug.get("output_lines"),
        debug.get("cache_hit"),
        debug.get("skipped_model"),
        debug.get("chunked", False),
        debug.get("chunk_count", 0),
        debug.get("runner"),
    )


def _parse_sparse_index_output(text: str) -> list[int]:
    parsed: list[int] = []
    seen: set[int] = set()
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for part in re.split(r"[\s,，]+", line):
            token = str(part or "").strip()
            if not token:
                continue
            try:
                value = int(token)
            except ValueError as exc:
                raise RuntimeError(f"Invalid sparse index output token: {token}") from exc
            if value in seen:
                continue
            parsed.append(value)
            seen.add(value)
    return parsed


def _parse_sparse_polish_output(text: str) -> dict[int, str]:
    parsed: dict[int, str] = {}
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "\t" in line:
            index_text, payload = line.split("\t", 1)
        else:
            parts = line.split(None, 1)
            if len(parts) < 2:
                raise RuntimeError(f"Invalid sparse polish output line: {line}")
            index_text, payload = parts
        try:
            index_value = int(str(index_text).strip())
        except ValueError as exc:
            raise RuntimeError(f"Invalid sparse polish output index: {index_text}") from exc
        if index_value in parsed:
            raise RuntimeError(f"Duplicate sparse polish output index: {index_value}")
        parsed[index_value] = str(payload or "").strip()
    return parsed


def _parse_delete_output(text: str, request: TestPromptRequest) -> list[dict[str, Any]]:
    deleted_indexes = set(_parse_sparse_index_output(text))
    valid_indexes = {int(segment["id"]) for segment in request.segments}
    unknown_indexes = sorted(index for index in deleted_indexes if index not in valid_indexes)
    if unknown_indexes:
        raise RuntimeError(f"Delete output referenced unknown line ids: {unknown_indexes}")

    lines: list[dict[str, Any]] = []
    for segment in request.segments:
        line_id = int(segment["id"])
        start = float(segment.get("start") or 0.0)
        end = float(segment.get("end") or 0.0)
        original_text = str(segment.get("text") or "").strip()
        forced_remove = _is_locally_deletable_text(original_text)
        final_remove = bool(forced_remove or line_id in deleted_indexes)
        lines.append(
            _build_runtime_line(
                line_id=line_id,
                start=start,
                end=end,
                original_text=original_text,
                ai_suggest_remove=final_remove,
                user_final_remove=final_remove,
            )
        )
    return _sort_runtime_lines(lines)


def _parse_polish_output(text: str, request: TestPromptRequest) -> list[dict[str, Any]]:
    changes = _parse_sparse_polish_output(text)
    valid_indexes = {int(line["line_id"]) for line in request.lines}
    unknown_indexes = sorted(index for index in changes if index not in valid_indexes)
    if unknown_indexes:
        raise RuntimeError(f"Polish output referenced unknown line ids: {unknown_indexes}")

    lines: list[dict[str, Any]] = []
    for raw_line in request.lines:
        source = dict(raw_line)
        line_id = int(source["line_id"])
        if line_id not in changes:
            lines.append(source)
            continue
        body = str(changes[line_id] or "").strip()
        lowered = body.lower()
        if not body or "<empty>" in lowered or "<remove>" in lowered:
            source["ai_suggest_remove"] = True
            source["user_final_remove"] = True
            lines.append(source)
            continue
        source["optimized_text"] = _normalize_line_text(body)
        lines.append(source)
    return _sort_runtime_lines(lines)


def _parse_chapter_output(text: str, request: TestPromptRequest) -> list[dict[str, Any]]:
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


def _run_via_prompt(request: TestPromptRequest) -> TestPromptArtifacts:
    bridge = DirectPromptTextBridge(request)
    input_text = bridge.render_input()
    input_lines_count = len([line for line in input_text.splitlines() if line.strip()])
    local_predelete_ids: list[int] = []
    if request.task == "delete":
        local_predelete_ids = [
            int(segment.get("id") or index)
            for index, segment in enumerate(request.segments, start=1)
            if _is_locally_deletable_text(str(segment.get("text") or ""))
        ]
        if input_lines_count == 0:
            artifacts = bridge.parse_output("")
            debug = {
                "task": request.task,
                "bridge": "DirectPromptTextBridge",
                "runner": summarize_prompt_variant(request.task),
                "elapsed_seconds": 0.0,
                "input_lines": 0,
                "output_lines": 0,
                "response_text": "",
                "cache_hit": False,
                "skipped_model": True,
                "local_predelete_line_ids": local_predelete_ids,
            }
            _log_direct_prompt_step_done(debug)
            return TestPromptArtifacts(
                task=artifacts.task,
                lines=artifacts.lines,
                chapters=artifacts.chapters,
                debug=debug,
            )
    start_time = time.time()
    response_text, cache_hit, cache_key = _run_direct_prompt(
        llm_config=_request_llm_config(request),
        messages=bridge.build_messages(),
    )
    elapsed = time.time() - start_time
    artifacts = bridge.parse_output(response_text)
    if cache_key and not cache_hit:
        _write_direct_prompt_cache(cache_key, response_text)
    output_lines_count = len([line for line in response_text.splitlines() if line.strip()])
    debug = {
        "task": request.task,
        "bridge": "DirectPromptTextBridge",
        "runner": summarize_prompt_variant(request.task),
        "elapsed_seconds": round(elapsed, 2),
        "input_lines": input_lines_count,
        "output_lines": output_lines_count,
        "response_text": response_text,
        "cache_hit": cache_hit,
        "skipped_model": False,
        "local_predelete_line_ids": local_predelete_ids,
    }
    _log_direct_prompt_step_done(debug)
    return TestPromptArtifacts(
        task=artifacts.task,
        lines=artifacts.lines,
        chapters=artifacts.chapters,
        debug=debug,
    )


def _run_polish_prompt(request: TestPromptRequest) -> TestPromptArtifacts:
    return _run_via_prompt(request)


def run_test_prompt(request: TestPromptRequest) -> TestPromptArtifacts:
    if request.task not in {"delete", "polish", "chapter"}:
        raise RuntimeError(f"Unsupported direct prompt task: {request.task}")
    if request.task == "delete":
        _require_line_budget(len(request.segments), max_lines=request.max_lines)
        return _run_via_prompt(request)
    _require_line_budget(len(request.lines), max_lines=request.max_lines)
    if request.task == "polish":
        return _run_polish_prompt(request)
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
