from __future__ import annotations

import datetime
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import srt

from .editing.chapter_domain import canonicalize_test_chapters, kept_test_lines
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

    def input_filename(self) -> str:
        return {
            "delete": "input_segments.txt",
            "polish": "input_lines.txt",
            "chapter": "input_lines.txt",
        }[self.task]

    def output_filename(self) -> str:
        return {
            "delete": "delete_output.txt",
            "polish": "polish_output.txt",
            "chapter": "chapter_output.txt",
        }[self.task]

    def render_input(self) -> str:
        if self.task == "delete":
            return _build_delete_input_text(self.request.segments)
        if self.task == "polish":
            return _build_polish_input_text(self.request.lines)
        return _build_chapter_input_text(self.request.lines)

    def build_prompt(self, *, input_path: Path, output_path: Path) -> str:
        if self.task == "delete":
            return _build_delete_prompt(input_path=input_path, output_path=output_path)
        if self.task == "polish":
            return _build_polish_prompt(input_path=input_path, output_path=output_path)
        return _build_chapter_prompt(
            input_path=input_path,
            output_path=output_path,
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
    if str(runtime_env.get("KIMI_API_KEY") or runtime_env.get("MOONSHOT_API_KEY") or "").strip():
        return KIMI_CODING_PROVIDER
    base_url = str(llm_config.get("base_url") or runtime_env.get("LLM_BASE_URL") or "").strip()
    if _is_kimi_coding_base_url(base_url):
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


def _time_range_tag(start: float, end: float) -> str:
    return render_time_range_tag(start, end)


def _time_range_key(start: float, end: float) -> tuple[int, int]:
    return (
        int(round(float(start) * 1000.0)),
        int(round(float(end) * 1000.0)),
    )


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


def _pi_env(llm_config: dict[str, Any]) -> dict[str, str]:
    env = dict(os.environ)
    base_url = str(llm_config.get("base_url") or env.get("LLM_BASE_URL") or "").strip()
    model = str(llm_config.get("model") or env.get("LLM_MODEL") or "").strip()
    api_key = str(llm_config.get("api_key") or env.get("LLM_API_KEY") or env.get("DASHSCOPE_API_KEY") or "").strip()
    if base_url:
        env["LLM_BASE_URL"] = base_url
    if model:
        env["LLM_MODEL"] = model
    if api_key:
        env["LLM_API_KEY"] = api_key
        env.setdefault("DASHSCOPE_API_KEY", api_key)
    if _resolve_pi_model(llm_config, env).startswith(f"{KIMI_CODING_PROVIDER}/"):
        kimi_api_key = (
            str(env.get("KIMI_API_KEY") or "").strip()
            or str(env.get("MOONSHOT_API_KEY") or "").strip()
            or str(llm_config.get("api_key") or "").strip()
        )
        if kimi_api_key:
            env["KIMI_API_KEY"] = kimi_api_key
    return env


def _pi_retry_attempts(llm_config: dict[str, Any]) -> int:
    return max(1, int(llm_config.get("request_retries", DEFAULT_PI_REQUEST_RETRIES) or 1))


def _pi_retry_backoff_seconds(llm_config: dict[str, Any]) -> float:
    return max(
        0.0,
        float(llm_config.get("retry_backoff_seconds", DEFAULT_PI_RETRY_BACKOFF_SECONDS) or 0.0),
    )


def _is_retryable_pi_failure(completed: subprocess.CompletedProcess[str]) -> bool:
    combined_output = "\n".join(
        part for part in ((completed.stdout or "").strip(), (completed.stderr or "").strip()) if part
    ).lower()
    if not combined_output:
        return False
    if any(marker in combined_output for marker in RETRYABLE_PI_ERROR_MARKERS):
        return True
    return any(re.search(rf"(?<!\d){status}(?!\d)", combined_output) for status in RETRYABLE_PI_STATUS_CODES)


def _format_pi_failure(completed: subprocess.CompletedProcess[str]) -> str:
    return (
        f"PI task failed (exit={completed.returncode}).\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
    )


def _run_pi_prompt(*, llm_config: dict[str, Any], prompt: str) -> subprocess.CompletedProcess[str]:
    command_env = _pi_env(llm_config)
    model = _resolve_pi_model(llm_config, command_env)
    command = build_pi_command(
        pi_args=[
            "--model",
            model,
            "--thinking",
            "off",
            "--tools",
            "read,write,ls",
            "--no-session",
            "-p",
            prompt,
        ]
    )
    attempts = _pi_retry_attempts(llm_config)
    backoff_seconds = _pi_retry_backoff_seconds(llm_config)
    completed: subprocess.CompletedProcess[str] | None = None
    for attempt in range(1, attempts + 1):
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            env=command_env,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            return completed
        if attempt >= attempts or not _is_retryable_pi_failure(completed):
            raise RuntimeError(_format_pi_failure(completed))
        delay = backoff_seconds * (2 ** (attempt - 1))
        logging.warning(
            "PI task transient failure model=%s attempt=%s/%s retry_in=%.1fs stderr=%s",
            model,
            attempt,
            attempts,
            delay,
            (completed.stderr or completed.stdout or "").strip(),
        )
        if delay > 0:
            time.sleep(delay)
    if completed is not None:
        raise RuntimeError(_format_pi_failure(completed))
    raise RuntimeError("PI task failed before subprocess execution started.")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _build_delete_prompt(*, input_path: Path, output_path: Path) -> str:
    return (
        "读取输入字幕文本，并使用项目自动加载的 delete skill 完成删除判断。\n"
        f"输入文件: {input_path}\n"
        f"输出文件: {output_path}\n"
        "要求：\n"
        "1. 只做 delete，不做 polish，不做 chapter。\n"
        "2. 只读取上面的输入文件，只写入上面的输出文件；不要探索仓库，不要读取无关文件，不要修改任何源码或其他文件。\n"
        "3. 输入中的每一行都长这样：`【time】句子`。\n"
        "4. 输出文件也必须逐行保持这个轻量格式：`【time】句子` 或 `【time】<remove>句子`。\n"
        "5. 必须覆盖全部输入行且只能输出一次；时间标签必须原样保留。\n"
        "6. delete 阶段只允许决定是否加 `<remove>`，不允许改写句子内容。\n"
        "7. 唯一删除原则：只要后一句和前一句属于重复语义，必须删除前面的重复部分，保留后面的句子；后面的句子一律视为纠正后的最终版本，绝不能删后面的保留前面的。\n"
        "8. 不要输出 markdown，不要输出解释；只把结果行写入输出文件，写完后立即结束。"
    )


def _build_polish_prompt(*, input_path: Path, output_path: Path) -> str:
    return (
        "读取输入 Test 轻量字幕文本，并使用项目自动加载的 polish skill 完成逐行润色。\n"
        f"输入文件: {input_path}\n"
        f"输出文件: {output_path}\n"
        "要求：\n"
        "1. 只做 polish，不做 delete，不做 chapter。\n"
        "2. 只读取上面的输入文件，只写入上面的输出文件；不要探索仓库，不要读取无关文件，不要修改任何源码或其他文件。\n"
        "3. 输入中的每一行都长这样：`【time】句子` 或 `【time】<remove>句子`。\n"
        "4. 输出文件也必须逐行保持这个轻量格式：`【time】句子` 或 `【time】<remove>句子`。\n"
        "5. `<remove>` 行必须逐字原样保留，连 `<remove>` 标记和正文都不能改动；非 `<remove>` 行才允许润色句子。\n"
        "6. 必须覆盖全部输入行且只能输出一次；时间标签必须原样保留。\n"
        "7. 不要输出 markdown，不要输出解释；只把结果行写入输出文件，写完后立即结束。"
    )


def _build_chapter_prompt(
    *,
    input_path: Path,
    output_path: Path,
    title_max_chars: int,
    max_chapters: int | None = None,
    chapter_policy_hint: str = "",
) -> str:
    requirements = [
        "1. 只做 chapter，不改字幕正文。",
        "2. 只读取上面的输入文件，只写入上面的输出文件；不要探索仓库，不要读取无关文件，不要修改任何源码或其他文件。",
        "3. 输入文件中每一行都长这样：`【block_index】句子`，只包含保留字幕。",
    ]
    if max_chapters is not None and max_chapters > 0:
        policy_hint = str(chapter_policy_hint or "").strip()
        if policy_hint:
            requirements.append(f"4. 当前按{policy_hint}处理，本次最多只能分成 {int(max_chapters)} 章。")
        else:
            requirements.append(f"4. 本次最多只能分成 {int(max_chapters)} 章。")
    next_index = len(requirements) + 1
    requirements.extend(
        [
            f"{next_index}. title 尽量不超过 {title_max_chars} 个字。",
            f"{next_index + 1}. 只有出现明确话题/阶段切换时才新开章节；寒暄、过渡句、重复补充、没有实质新内容的短段落必须并入相邻章节，不要单独成章。",
            f"{next_index + 2}. 输出文件必须逐行使用轻量格式：`【start-end】标题`，例如 `【1-3】开场`。",
            f"{next_index + 3}. 所有 block_range 必须连续覆盖全部 block，不能空洞、重叠、跳号、越界。",
            f"{next_index + 4}. 不要输出 markdown，不要输出解释；只把章节行写入输出文件，写完后立即结束。",
        ]
    )
    return (
        "读取输入 Test 轻量字幕文本，并使用项目自动加载的 chapter skill 生成最终章节。\n"
        f"输入文件: {input_path}\n"
        f"输出文件: {output_path}\n"
        "要求：\n"
        + "\n".join(requirements)
    )


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
        if _canonical_special_placeholder(body) != _canonical_special_placeholder(original_text):
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
        if not body:
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


def _run_via_pi(request: TestPiRequest) -> TestPiArtifacts:
    bridge = PiTextBridge(request)
    with tempfile.TemporaryDirectory(prefix=f"pi-{request.task}-") as tmpdir:
        root = Path(tmpdir)
        input_path = root / bridge.input_filename()
        output_path = root / bridge.output_filename()
        _write_text(input_path, bridge.render_input())
        completed = _run_pi_prompt(
            llm_config=request.llm_config,
            prompt=bridge.build_prompt(input_path=input_path, output_path=output_path),
        )
        artifacts = bridge.parse_output(output_path.read_text(encoding="utf-8"))
        return TestPiArtifacts(
            task=artifacts.task,
            lines=artifacts.lines,
            chapters=artifacts.chapters,
            debug={
                "task": request.task,
                "bridge": "PiTextBridge",
                "pi_stdout": completed.stdout,
                "pi_stderr": completed.stderr,
            },
        )


def run_test_pi(request: TestPiRequest) -> TestPiArtifacts:
    if request.task not in {"delete", "polish", "chapter"}:
        raise RuntimeError(f"Unsupported Test PI task: {request.task}")
    if request.task == "delete":
        _require_line_budget(len(request.segments), max_lines=request.max_lines)
        return _run_via_pi(request)
    _require_line_budget(len(request.lines), max_lines=request.max_lines)
    return _run_via_pi(request)


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
