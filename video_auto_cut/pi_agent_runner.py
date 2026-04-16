from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import srt

from .asr.transcribe_stage import run_asr_transcription_stage
from .editing.chapter_domain import canonicalize_test_chapters, kept_test_lines
from .orchestration.pipeline_options_builder import build_pipeline_options_from_env
from .shared.test_text_protocol import (
    parse_chapter_line,
    parse_timed_lines,
    render_chapter_line,
    render_test_line_text,
    render_time_range_tag,
)
from web_api.utils.srt_utils import build_test_lines_from_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_PI_DIR = PROJECT_ROOT / ".pi"
PROJECT_PI_APPEND_SYSTEM = PROJECT_PI_DIR / "APPEND_SYSTEM.md"
REMOVE_TOKEN = "<remove>"
DEFAULT_MAX_LINES = 400
PROJECT_PI_PROVIDER = "vac-llm"
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


@dataclass(frozen=True)
class TestPiArtifacts:
    task: TestTask
    lines: list[dict[str, Any]] = field(default_factory=list)
    chapters: list[dict[str, Any]] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)


def build_pi_command(*, pi_bin: str = "pi", pi_args: list[str] | None = None) -> list[str]:
    return [str(pi_bin), *(pi_args or [])]


def _resolve_pi_model(model: str) -> str:
    value = str(model or "").strip()
    if not value:
        raise RuntimeError("LLM model is required for PI execution.")
    if "/" in value:
        return value
    return f"{PROJECT_PI_PROVIDER}/{value}"


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
    return env


def _run_pi_prompt(*, llm_config: dict[str, Any], prompt: str) -> subprocess.CompletedProcess[str]:
    command = build_pi_command(
        pi_args=[
            "--model",
            _resolve_pi_model(str(llm_config.get("model") or "")),
            "--thinking",
            "off",
            "--tools",
            "read,write,ls",
            "--no-session",
            "-p",
            prompt,
        ]
    )
    completed = subprocess.run(
        command,
        cwd=str(PROJECT_ROOT),
        env=_pi_env(llm_config),
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"PI task failed (exit={completed.returncode}).\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )
    return completed


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
        "7. 不要输出 markdown，不要输出解释；只把结果行写入输出文件，写完后立即结束。"
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


def _build_chapter_prompt(*, input_path: Path, output_path: Path, title_max_chars: int) -> str:
    return (
        "读取输入 Test 轻量字幕文本，并使用项目自动加载的 chapter skill 生成最终章节。\n"
        f"输入文件: {input_path}\n"
        f"输出文件: {output_path}\n"
        "要求：\n"
        "1. 只做 chapter，不改字幕正文。\n"
        "2. 只读取上面的输入文件，只写入上面的输出文件；不要探索仓库，不要读取无关文件，不要修改任何源码或其他文件。\n"
        "3. 输入文件中每一行都长这样：`【block_index】句子`，只包含保留字幕。\n"
        f"4. title 尽量不超过 {title_max_chars} 个字。\n"
        "5. 输出文件必须逐行使用轻量格式：`【start-end】标题`，例如 `【1-3】开场`。\n"
        "6. 所有 block_range 必须连续覆盖全部 block，不能空洞、重叠、跳号、越界。\n"
        "7. 不要输出 markdown，不要输出解释；只把章节行写入输出文件，写完后立即结束。"
    )


def _parse_delete_output(text: str, request: TestPiRequest) -> list[dict[str, Any]]:
    expected: dict[tuple[float, float], dict[str, Any]] = {
        (round(float(segment.get("start") or 0.0), 3), round(float(segment.get("end") or 0.0), 3)): segment
        for segment in request.segments
    }
    parsed = parse_timed_lines(text)
    seen: set[tuple[float, float]] = set()
    lines: list[dict[str, Any]] = []
    for start, end, remove, body in parsed:
        key = (round(start, 3), round(end, 3))
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
    expected: dict[tuple[float, float], dict[str, Any]] = {
        (round(float(line.get("start") or 0.0), 3), round(float(line.get("end") or 0.0), 3)): line
        for line in request.lines
    }
    parsed = parse_timed_lines(text)
    seen: set[tuple[float, float]] = set()
    lines: list[dict[str, Any]] = []
    for start, end, remove, body in parsed:
        key = (round(start, 3), round(end, 3))
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


def _run_delete_via_pi(request: TestPiRequest) -> TestPiArtifacts:
    with tempfile.TemporaryDirectory(prefix="pi-delete-") as tmpdir:
        root = Path(tmpdir)
        input_path = root / "input_segments.txt"
        output_path = root / "delete_output.txt"
        _write_text(input_path, _build_delete_input_text(request.segments))
        completed = _run_pi_prompt(
            llm_config=request.llm_config,
            prompt=_build_delete_prompt(input_path=input_path, output_path=output_path),
        )
        lines = _parse_delete_output(output_path.read_text(encoding="utf-8"), request)
        return TestPiArtifacts(
            task="delete",
            lines=lines,
            debug={"task": "delete", "pi_stdout": completed.stdout, "pi_stderr": completed.stderr},
        )


def _run_polish_via_pi(request: TestPiRequest) -> TestPiArtifacts:
    with tempfile.TemporaryDirectory(prefix="pi-polish-") as tmpdir:
        root = Path(tmpdir)
        input_path = root / "input_lines.txt"
        output_path = root / "polish_output.txt"
        _write_text(input_path, _build_polish_input_text(request.lines))
        completed = _run_pi_prompt(
            llm_config=request.llm_config,
            prompt=_build_polish_prompt(input_path=input_path, output_path=output_path),
        )
        lines = _parse_polish_output(output_path.read_text(encoding="utf-8"), request)
        return TestPiArtifacts(
            task="polish",
            lines=lines,
            debug={"task": "polish", "pi_stdout": completed.stdout, "pi_stderr": completed.stderr},
        )


def _run_chapter_via_pi(request: TestPiRequest) -> TestPiArtifacts:
    with tempfile.TemporaryDirectory(prefix="pi-chapter-") as tmpdir:
        root = Path(tmpdir)
        input_path = root / "input_lines.txt"
        output_path = root / "chapter_output.txt"
        _write_text(input_path, _build_chapter_input_text(request.lines))
        completed = _run_pi_prompt(
            llm_config=request.llm_config,
            prompt=_build_chapter_prompt(
                input_path=input_path,
                output_path=output_path,
                title_max_chars=request.title_max_chars,
            ),
        )
        chapters = _parse_chapter_output(output_path.read_text(encoding="utf-8"), request)
        return TestPiArtifacts(
            task="chapter",
            lines=list(request.lines),
            chapters=chapters,
            debug={"task": "chapter", "pi_stdout": completed.stdout, "pi_stderr": completed.stderr},
        )


def run_test_pi(request: TestPiRequest) -> TestPiArtifacts:
    if request.task not in {"delete", "polish", "chapter"}:
        raise RuntimeError(f"Unsupported Test PI task: {request.task}")
    if request.task == "delete":
        _require_line_budget(len(request.segments), max_lines=request.max_lines)
        return _run_delete_via_pi(request)
    _require_line_budget(len(request.lines), max_lines=request.max_lines)
    if request.task == "polish":
        return _run_polish_via_pi(request)
    return _run_chapter_via_pi(request)


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


def _load_segments_from_path(input_path: Path, encoding: str) -> list[dict[str, Any]]:
    if input_path.suffix.lower() == ".srt":
        segments: list[dict[str, Any]] = []
        for sub in srt.parse(input_path.read_text(encoding=encoding)):
            segments.append(
                {
                    "id": int(sub.index),
                    "start": float(sub.start.total_seconds()),
                    "end": float(sub.end.total_seconds()),
                    "duration": max(0.0, float(sub.end.total_seconds() - sub.start.total_seconds())),
                    "text": str(sub.content or "").strip(),
                }
            )
        return segments
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("segments"), list):
        payload = payload["segments"]
    if not isinstance(payload, list):
        raise RuntimeError(f"Unsupported input payload for {input_path}")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        result.append(
            {
                "id": int(item.get("id") or item.get("line_id") or index),
                "start": float(item.get("start") or 0.0),
                "end": float(item.get("end") or 0.0),
                "duration": max(0.0, float(item.get("end") or 0.0) - float(item.get("start") or 0.0)),
                "text": str(item.get("text") or item.get("original_text") or "").strip(),
            }
        )
    return result


def _load_lines_from_test_json(input_path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _sort_runtime_lines(build_test_lines_from_text(input_path))
    lines = payload.get("lines") if isinstance(payload, dict) else payload
    if not isinstance(lines, list):
        raise RuntimeError(f"Invalid Test lines payload: {input_path}")
    return _sort_runtime_lines([dict(item) for item in lines if isinstance(item, dict)])


def _build_cli_llm_config(args: argparse.Namespace) -> dict[str, Any]:
    cfg = {
        "base_url": (args.llm_base_url or os.environ.get("LLM_BASE_URL") or "").strip(),
        "model": (args.llm_model or os.environ.get("LLM_MODEL") or "").strip(),
        "api_key": (args.llm_api_key or os.environ.get("LLM_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or "").strip(),
        "timeout": int(args.llm_timeout),
        "max_tokens": args.llm_max_tokens,
    }
    if not cfg.get("base_url") or not cfg.get("model"):
        raise RuntimeError("LLM config missing. Set --llm-base-url and --llm-model.")
    return cfg


def _build_cli_pipeline_options(args: argparse.Namespace):
    return build_pipeline_options_from_env(
        force=True,
        lang=(args.lang or None),
        prompt=str(args.prompt or ""),
    )


def _write_srt(path: Path, subtitles: list[srt.Subtitle], encoding: str) -> None:
    path.write_text(srt.compose(subtitles, reindex=False), encoding=encoding)


def _run_cli_test(args: argparse.Namespace) -> int:
    llm_config = _build_cli_llm_config(args)
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if input_path.suffix.lower() == ".json":
        raise RuntimeError("`--task test` currently expects media or .srt input, not .json")

    raw_srt_path: Path
    raw_lines: list[dict[str, Any]]
    if input_path.suffix.lower() == ".srt":
        raw_srt_path = input_path
        segments = _load_segments_from_path(input_path, args.encoding)
        raw_lines = [
            _build_runtime_line(
                line_id=int(segment["id"]),
                start=float(segment.get("start") or 0.0),
                end=float(segment.get("end") or 0.0),
                original_text=str(segment.get("text") or "").strip(),
            )
            for segment in segments
        ]
    else:
        asr_artifacts = run_asr_transcription_stage(
            input_path,
            _build_cli_pipeline_options(args),
        )
        raw_srt_path = asr_artifacts.srt_path
        raw_lines = asr_artifacts.test_lines
        segments = [
            {
                "id": int(line["line_id"]),
                "start": float(line["start"]),
                "end": float(line["end"]),
                "duration": max(0.0, float(line["end"]) - float(line["start"])),
                "text": str(line["original_text"]),
            }
            for line in raw_lines
        ]

    delete_artifacts = run_test_pi(
        TestPiRequest(task="delete", llm_config=llm_config, segments=segments, max_lines=args.max_lines)
    )
    polish_artifacts = run_test_pi(
        TestPiRequest(task="polish", llm_config=llm_config, lines=delete_artifacts.lines, max_lines=args.max_lines)
    )
    chapter_artifacts = run_test_pi(
        TestPiRequest(
            task="chapter",
            llm_config=llm_config,
            lines=polish_artifacts.lines,
            title_max_chars=args.title_max_chars,
            max_lines=args.max_lines,
        )
    )

    raw_test_json_path = output_path.with_suffix(".raw.test.json")
    final_test_text_path = output_path.with_suffix(".test.json")
    final_test_srt_path = output_path.with_suffix(".test.srt")
    chapters_json_path = output_path.with_suffix(".chapters.json")

    _write_json(raw_test_json_path, {"lines": raw_lines})
    _write_json(final_test_text_path, {"lines": polish_artifacts.lines})
    _write_srt(final_test_srt_path, build_subtitles_from_lines(polish_artifacts.lines), args.encoding)
    _write_json(chapters_json_path, {"topics": chapter_artifacts.chapters})

    payload = {
        "input_path": str(input_path),
        "raw_srt_path": str(raw_srt_path),
        "raw_test_json_path": str(raw_test_json_path),
        "final_test_text_path": str(final_test_text_path),
        "final_test_srt_path": str(final_test_srt_path),
        "chapters_json_path": str(chapters_json_path),
        "line_count": len(polish_artifacts.lines),
        "chapter_count": len(chapter_artifacts.chapters),
    }
    _write_json(output_path, payload)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PI agent with project auto-loaded skills/system prompt or execute canonical PI tasks directly.")
    parser.add_argument("--pi-bin", default="pi")
    parser.add_argument("--input", default=None)
    parser.add_argument("--task", choices=["delete", "polish", "chapter", "test"], default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--encoding", default="utf-8")
    parser.add_argument("--llm-base-url", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--llm-api-key", default=None)
    parser.add_argument("--llm-timeout", type=int, default=300)
    parser.add_argument("--llm-max-tokens", type=int, default=None)
    parser.add_argument("--title-max-chars", type=int, default=6)
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    parser.add_argument("--lang", default=None)
    parser.add_argument("--prompt", default="")
    parser.add_argument("pi_args", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def _run_cli_task(args: argparse.Namespace) -> int:
    if args.task == "test":
        return _run_cli_test(args)

    llm_config = _build_cli_llm_config(args)
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if args.task == "delete":
        segments = _load_segments_from_path(input_path, args.encoding)
        artifacts = run_test_pi(TestPiRequest(task="delete", llm_config=llm_config, segments=segments, max_lines=args.max_lines))
        _write_text(output_path, _render_test_text_from_lines(artifacts.lines) + "\n")
        return 0

    if args.task == "polish":
        if input_path.suffix.lower().endswith(".json"):
            lines = _load_lines_from_test_json(input_path)
        else:
            segments = _load_segments_from_path(input_path, args.encoding)
            lines = run_test_pi(TestPiRequest(task="delete", llm_config=llm_config, segments=segments, max_lines=args.max_lines)).lines
        artifacts = run_test_pi(TestPiRequest(task="polish", llm_config=llm_config, lines=lines, max_lines=args.max_lines))
        _write_text(output_path, _render_test_text_from_lines(artifacts.lines) + "\n")
        return 0

    if input_path.suffix.lower().endswith(".json"):
        lines = _load_lines_from_test_json(input_path)
    else:
        segments = _load_segments_from_path(input_path, args.encoding)
        lines = run_test_pi(TestPiRequest(task="delete", llm_config=llm_config, segments=segments, max_lines=args.max_lines)).lines
        lines = run_test_pi(TestPiRequest(task="polish", llm_config=llm_config, lines=lines, max_lines=args.max_lines)).lines
    artifacts = run_test_pi(
        TestPiRequest(task="chapter", llm_config=llm_config, lines=lines, title_max_chars=args.title_max_chars, max_lines=args.max_lines)
    )
    _write_text(output_path, _render_chapters_text(artifacts.chapters) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.task:
        if not args.input or not args.output:
            raise RuntimeError("--input and --output are required when --task is used")
        return _run_cli_task(args)
    completed = subprocess.run(build_pi_command(pi_bin=args.pi_bin, pi_args=list(args.pi_args or [])), env=dict(os.environ), cwd=str(PROJECT_ROOT), check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
