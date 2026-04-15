from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Literal

import srt

from .editing import llm_client as llm_utils

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = PROJECT_ROOT / 'skills'
DEFAULT_SKILLS = ['delete', 'polish', 'chapter']
REMOVE_TOKEN = '<<REMOVE>>'
DEFAULT_MAX_LINES = 400
Step1Task = Literal['delete', 'polish', 'chapter']

SHARED_SYSTEM_PROMPT = (
    "你是视频口播编辑 PI agent。"
    "你在一个统一的编辑工作流中工作，只允许执行三类任务：delete、polish、chapter。"
    "delete 只负责删除被后文覆盖的重复、无效试探和应移除内容，不负责润色或分章。"
    "polish 只负责润色保留行，不负责删除，不新增事实，不跨行合并。"
    "chapter 只负责基于保留字幕生成连续覆盖的章节标题和 block_range。"
    "始终保留结构化输出纪律；如果无法满足结构要求，就宁可失败，不要编造。"
)


@dataclass(frozen=True)
class Step1PiRequest:
    task: Step1Task
    llm_config: dict[str, Any]
    segments: list[dict[str, Any]] = field(default_factory=list)
    lines: list[dict[str, Any]] = field(default_factory=list)
    title_max_chars: int = 6
    max_lines: int = DEFAULT_MAX_LINES


@dataclass(frozen=True)
class Step1PiArtifacts:
    task: Step1Task
    lines: list[dict[str, Any]] = field(default_factory=list)
    chapters: list[dict[str, Any]] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)


def skill_paths(skill_names: Iterable[str] | None = None) -> list[Path]:
    names = list(skill_names or DEFAULT_SKILLS)
    paths: list[Path] = []
    for name in names:
        path = (SKILLS_ROOT / str(name).strip()).resolve()
        if not (path / 'SKILL.md').exists():
            raise RuntimeError(f'Missing PI skill folder: {path}')
        paths.append(path)
    return paths


def _strategy_path(task: Step1Task) -> Path:
    return (SKILLS_ROOT / task / 'scripts' / 'strategy.py').resolve()


def _load_module_from_path(*, path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'Unable to load module from {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_strategy_module(task: Step1Task) -> ModuleType:
    path = _strategy_path(task)
    if not path.exists():
        raise RuntimeError(f'Missing strategy module for task {task}: {path}')
    return _load_module_from_path(path=path, module_name=f'video_auto_cut_skill_{task}_strategy')


def build_pi_command(*, pi_bin: str = 'pi', extra_skills: list[str] | None = None, pi_args: list[str] | None = None) -> list[str]:
    command: list[str] = [str(pi_bin), '--no-skills']
    for skill_path in skill_paths(extra_skills):
        command.extend(['--skill', str(skill_path)])
    command.extend(['--append-system-prompt', SHARED_SYSTEM_PROMPT])
    command.extend(list(pi_args or []))
    return command


def _normalize_line_text(text: str) -> str:
    value = (text or '').strip()
    if value.endswith(("？", "?")):
        return value
    while value and value[-1] in '，。、；：!！.':
        value = value[:-1].rstrip()
    return value


def _require_line_budget(count: int, *, max_lines: int) -> None:
    if count > max_lines:
        raise RuntimeError(
            f'PI runner input exceeds non-chunk budget: {count} lines > {max_lines}. '
            'Use a larger-context model or an explicit non-default overflow path.'
        )


def _request_json(llm_config: dict[str, Any], messages: list[dict[str, str]], *, validate) -> dict[str, Any]:
    return llm_utils.request_json(
        llm_config,
        messages,
        validate=validate,
        repair_retries=0,
    )


def run_step1_pi(request: Step1PiRequest) -> Step1PiArtifacts:
    if request.task not in {'delete', 'polish', 'chapter'}:
        raise RuntimeError(f'Unsupported Step1 PI task: {request.task}')
    if request.task == 'delete':
        _require_line_budget(len(request.segments), max_lines=request.max_lines)
    else:
        _require_line_budget(len(request.lines), max_lines=request.max_lines)
    strategy = load_strategy_module(request.task)
    messages = strategy.build_messages(SHARED_SYSTEM_PROMPT, request)
    payload = _request_json(
        request.llm_config,
        messages,
        validate=lambda data: strategy.validate_payload(data, request),
    )
    materialized = strategy.materialize(payload, request)
    return Step1PiArtifacts(
        task=request.task,
        lines=list(materialized.get('lines') or []),
        chapters=list(materialized.get('chapters') or []),
        debug=dict(materialized.get('debug') or {}),
    )


def build_subtitles_from_lines(lines: list[dict[str, Any]]) -> list[srt.Subtitle]:
    subtitles: list[srt.Subtitle] = []
    for line in sorted(lines, key=lambda item: int(item['line_id'])):
        line_id = int(line['line_id'])
        text = str(line.get('optimized_text') or line.get('original_text') or '').strip()
        if bool(line.get('ai_suggest_remove', False)):
            text = f"{REMOVE_TOKEN} {str(line.get('original_text') or text).strip()}".strip()
        else:
            text = _normalize_line_text(text)
        subtitles.append(
            srt.Subtitle(
                index=line_id,
                start=datetime.timedelta(seconds=float(line.get('start') or 0.0)),
                end=datetime.timedelta(seconds=float(line.get('end') or 0.0)),
                content=text,
            )
        )
    return subtitles


def build_edl_from_lines(lines: list[dict[str, Any]], *, merge_gap_s: float, total_length: float | None) -> list[dict[str, float]]:
    edl: list[dict[str, float]] = []
    for line in sorted(lines, key=lambda item: int(item['line_id'])):
        if bool(line.get('ai_suggest_remove', False)):
            continue
        start = float(line.get('start') or 0.0)
        end = float(line.get('end') or 0.0)
        if total_length is not None:
            end = min(total_length, end)
        if end <= start:
            continue
        if not edl:
            edl.append({'start': start, 'end': end})
            continue
        if start - edl[-1]['end'] <= merge_gap_s:
            edl[-1]['end'] = max(edl[-1]['end'], end)
        else:
            edl.append({'start': start, 'end': end})
    return edl


def _load_segments_from_path(input_path: Path, encoding: str) -> list[dict[str, Any]]:
    if input_path.suffix.lower() == '.srt':
        segments: list[dict[str, Any]] = []
        for sub in srt.parse(input_path.read_text(encoding=encoding)):
            segments.append(
                {
                    'id': int(sub.index),
                    'start': float(sub.start.total_seconds()),
                    'end': float(sub.end.total_seconds()),
                    'duration': max(0.0, float(sub.end.total_seconds() - sub.start.total_seconds())),
                    'text': str(sub.content or '').strip(),
                }
            )
        return segments
    payload = json.loads(input_path.read_text(encoding='utf-8'))
    if isinstance(payload, dict) and isinstance(payload.get('segments'), list):
        payload = payload['segments']
    if not isinstance(payload, list):
        raise RuntimeError(f'Unsupported input payload for {input_path}')
    result: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        result.append(
            {
                'id': int(item.get('id') or index),
                'start': float(item.get('start') or 0.0),
                'end': float(item.get('end') or 0.0),
                'duration': max(0.0, float(item.get('end') or 0.0) - float(item.get('start') or 0.0)),
                'text': str(item.get('text') or '').strip(),
            }
        )
    return result


def _load_lines_from_step1_json(input_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(input_path.read_text(encoding='utf-8'))
    lines = payload.get('lines') if isinstance(payload, dict) else payload
    if not isinstance(lines, list):
        raise RuntimeError(f'Invalid Step1 lines payload: {input_path}')
    return [dict(item) for item in lines if isinstance(item, dict)]


def _build_cli_llm_config(args: argparse.Namespace) -> dict[str, Any]:
    cfg = llm_utils.build_llm_config(
        base_url=args.llm_base_url,
        model=args.llm_model,
        api_key=args.llm_api_key,
        timeout=args.llm_timeout,
        temperature=0.0,
        max_tokens=args.llm_max_tokens,
        enable_thinking=False,
    )
    if not cfg.get('base_url') or not cfg.get('model'):
        raise RuntimeError('LLM config missing. Set --llm-base-url and --llm-model.')
    return cfg


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run PI agent with repo-local editing skills or execute canonical PI tasks directly.')
    parser.add_argument('--pi-bin', default='pi')
    parser.add_argument('--skill', action='append', default=[])
    parser.add_argument('--input', default=None)
    parser.add_argument('--task', choices=['delete', 'polish', 'chapter'], default=None)
    parser.add_argument('--output', default=None)
    parser.add_argument('--encoding', default='utf-8')
    parser.add_argument('--llm-base-url', default=None)
    parser.add_argument('--llm-model', default=None)
    parser.add_argument('--llm-api-key', default=None)
    parser.add_argument('--llm-timeout', type=int, default=300)
    parser.add_argument('--llm-max-tokens', type=int, default=None)
    parser.add_argument('--title-max-chars', type=int, default=6)
    parser.add_argument('--max-lines', type=int, default=DEFAULT_MAX_LINES)
    parser.add_argument('pi_args', nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def _run_cli_task(args: argparse.Namespace) -> int:
    llm_config = _build_cli_llm_config(args)
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if args.task == 'delete':
        segments = _load_segments_from_path(input_path, args.encoding)
        artifacts = run_step1_pi(Step1PiRequest(task='delete', llm_config=llm_config, segments=segments, max_lines=args.max_lines))
        output_path.write_text(json.dumps({'lines': artifacts.lines}, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0

    if args.task == 'polish':
        if input_path.suffix.lower().endswith('.json'):
            lines = _load_lines_from_step1_json(input_path)
        else:
            segments = _load_segments_from_path(input_path, args.encoding)
            lines = run_step1_pi(Step1PiRequest(task='delete', llm_config=llm_config, segments=segments, max_lines=args.max_lines)).lines
        artifacts = run_step1_pi(Step1PiRequest(task='polish', llm_config=llm_config, lines=lines, max_lines=args.max_lines))
        output_path.write_text(json.dumps({'lines': artifacts.lines}, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0

    if input_path.suffix.lower().endswith('.json'):
        lines = _load_lines_from_step1_json(input_path)
    else:
        segments = _load_segments_from_path(input_path, args.encoding)
        lines = run_step1_pi(Step1PiRequest(task='delete', llm_config=llm_config, segments=segments, max_lines=args.max_lines)).lines
        lines = run_step1_pi(Step1PiRequest(task='polish', llm_config=llm_config, lines=lines, max_lines=args.max_lines)).lines
    artifacts = run_step1_pi(Step1PiRequest(task='chapter', llm_config=llm_config, lines=lines, title_max_chars=args.title_max_chars, max_lines=args.max_lines))
    output_path.write_text(json.dumps({'topics': artifacts.chapters}, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.task:
        if not args.input or not args.output:
            raise RuntimeError('--input and --output are required when --task is used')
        return _run_cli_task(args)
    command = build_pi_command(pi_bin=args.pi_bin, extra_skills=list(args.skill or []), pi_args=list(args.pi_args or []))
    env = dict(os.environ)
    env.setdefault('VIDEO_AUTO_CUT_SKILLS_ROOT', str(SKILLS_ROOT))
    completed = subprocess.run(command, env=env, check=False)
    return int(completed.returncode)


if __name__ == '__main__':
    raise SystemExit(main())
