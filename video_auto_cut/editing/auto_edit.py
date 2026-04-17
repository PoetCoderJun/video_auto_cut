from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import srt

from . import llm_client as llm_utils
from video_auto_cut.pi_agent_runner import TestPiRequest, build_edl_from_lines, build_subtitles_from_lines, run_test_pi
from video_auto_cut.shared.interfaces import PipelineOptions
from video_auto_cut.shared.test_text_io import write_test_text

REMOVE_TOKEN = "<remove>"


@dataclass
class AutoEditConfig:
    merge_gap_s: float = 0.5
    pad_head_s: float = 0.0
    pad_tail_s: float = 0.0


@dataclass(frozen=True)
class AutoEditRuntime:
    inputs: tuple[str, ...]
    encoding: str = "utf-8"
    force: bool = False
    stage_callback: Callable[[str, str], None] | None = None
    preview_callback: Callable[[list[dict[str, Any]]], None] | None = None


def _load_segments(input_path: str, encoding: str) -> tuple[list[dict[str, Any]], float | None]:
    path = Path(input_path)
    if path.suffix.lower() == ".srt":
        subtitles = list(srt.parse(path.read_text(encoding=encoding)))
        segments: list[dict[str, Any]] = []
        total_length = None
        for subtitle in subtitles:
            start = float(subtitle.start.total_seconds())
            end = float(subtitle.end.total_seconds())
            segments.append(
                {
                    "id": int(subtitle.index),
                    "start": start,
                    "end": end,
                    "duration": max(0.0, end - start),
                    "text": str(subtitle.content or "").strip(),
                }
            )
            total_length = max(total_length or 0.0, end)
        return segments, total_length

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("segments") or payload
    if not isinstance(payload, list):
        raise RuntimeError(f"Unsupported auto-edit input payload: {input_path}")

    segments: list[dict[str, Any]] = []
    total_length = None
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            continue
        start = float(item.get("start") or 0.0)
        end = float(item.get("end") or 0.0)
        segments.append(
            {
                "id": int(item.get("id") or index),
                "start": start,
                "end": end,
                "duration": max(0.0, end - start),
                "text": str(item.get("text") or "").strip(),
            }
        )
        total_length = max(total_length or 0.0, end)
    return segments, total_length


def _write_json(path: str, data: Any) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_optimized_srt(path: str, subs: list[srt.Subtitle], encoding: str) -> None:
    Path(path).write_text(srt.compose(subs, reindex=False), encoding=encoding)


def _maybe_skip(path: str, force: bool) -> bool:
    target = Path(path)
    if target.exists():
        if force:
            logging.info("%s exists. Will overwrite it", path)
            return False
        logging.info("%s exists, skipping... Use --force to overwrite", path)
        return True
    return False


def _build_auto_edit_llm_config(
    *,
    base_url: str | None,
    model: str | None,
    api_key: str | None,
    timeout: int,
    max_tokens: int | None,
) -> dict[str, Any]:
    llm_config = llm_utils.build_llm_config(
        base_url=base_url,
        model=model,
        api_key=api_key,
        timeout=timeout,
        temperature=0.0,
        max_tokens=max_tokens,
        enable_thinking=False,
    )
    if not llm_config.get("base_url") or not llm_config.get("model"):
        raise RuntimeError("LLM config missing. Set --llm-base-url and --llm-model to use auto-edit LLM.")
    return llm_config


class AutoEdit:
    def __init__(self, runtime: AutoEditRuntime, *, cfg: AutoEditConfig, llm_config: dict[str, Any]):
        self.inputs = list(runtime.inputs)
        self.force = runtime.force
        self.encoding = runtime.encoding
        self.stage_callback = runtime.stage_callback
        self.preview_callback = runtime.preview_callback
        self.last_result: dict[str, Any] | None = None
        self.cfg = cfg
        self.llm_config = llm_config

    @classmethod
    def from_args(cls, args: Any) -> "AutoEdit":
        if not bool(getattr(args, "auto_edit_llm", False)):
            raise RuntimeError("Auto-edit requires --auto-edit-llm.")
        runtime = AutoEditRuntime(
            inputs=tuple(str(path) for path in getattr(args, "inputs", [])),
            encoding=str(getattr(args, "encoding", "utf-8")),
            force=bool(getattr(args, "force", False)),
            stage_callback=getattr(args, "auto_edit_stage_callback", None),
            preview_callback=getattr(args, "auto_edit_preview_callback", None),
        )
        cfg = AutoEditConfig(
            merge_gap_s=float(getattr(args, "auto_edit_merge_gap", 0.5)),
            pad_head_s=float(getattr(args, "auto_edit_pad_head", 0.0)),
            pad_tail_s=float(getattr(args, "auto_edit_pad_tail", 0.0)),
        )
        llm_config = _build_auto_edit_llm_config(
            base_url=getattr(args, "llm_base_url", None),
            model=getattr(args, "llm_model", None),
            api_key=getattr(args, "llm_api_key", None),
            timeout=int(getattr(args, "llm_timeout", 300)),
            max_tokens=getattr(args, "llm_max_tokens", None),
        )
        return cls(runtime, cfg=cfg, llm_config=llm_config)

    @classmethod
    def from_pipeline_options(
        cls,
        input_path: str | Path,
        options: PipelineOptions,
        *,
        stage_callback: Callable[[str, str], None] | None = None,
        preview_callback: Callable[[list[dict[str, Any]]], None] | None = None,
    ) -> "AutoEdit":
        runtime = AutoEditRuntime(
            inputs=(str(Path(input_path)),),
            encoding=options.encoding,
            force=bool(options.force),
            stage_callback=stage_callback,
            preview_callback=preview_callback,
        )
        cfg = AutoEditConfig(
            merge_gap_s=float(options.auto_edit_merge_gap),
            pad_head_s=float(options.auto_edit_pad_head),
            pad_tail_s=float(options.auto_edit_pad_tail),
        )
        llm_config = _build_auto_edit_llm_config(
            base_url=options.llm_base_url,
            model=options.llm_model,
            api_key=options.llm_api_key,
            timeout=int(options.llm_timeout),
            max_tokens=options.llm_max_tokens,
        )
        return cls(runtime, cfg=cfg, llm_config=llm_config)

    def _emit_stage(self, code: str, message: str) -> None:
        if callable(self.stage_callback):
            self.stage_callback(code, message)

    def _emit_preview(self, lines: list[dict[str, Any]]) -> None:
        if callable(self.preview_callback):
            self.preview_callback(lines)

    def _auto_edit_segments(self, segments: list[dict[str, Any]], total_length: float | None) -> dict[str, Any]:
        self._emit_stage("REMOVING_REDUNDANT_LINES", "正在判断哪些字幕需要删除...")
        delete_artifacts = run_test_pi(
            TestPiRequest(
                task="delete",
                llm_config=self.llm_config,
                segments=segments,
            )
        )
        kept_lines = [line for line in delete_artifacts.lines if not bool(line.get("user_final_remove", False))]
        if not kept_lines:
            raise RuntimeError("All segments removed. Check LLM output.")
        self._emit_preview(delete_artifacts.lines)

        self._emit_stage("POLISHING_EXPRESSION", "正在润色表达...")
        polish_artifacts = run_test_pi(
            TestPiRequest(
                task="polish",
                llm_config=self.llm_config,
                lines=delete_artifacts.lines,
            )
        )
        self._emit_preview(polish_artifacts.lines)

        optimized_subs = build_subtitles_from_lines(polish_artifacts.lines)
        edl = build_edl_from_lines(
            polish_artifacts.lines,
            merge_gap_s=self.cfg.merge_gap_s,
            total_length=total_length,
        )
        return {
            "optimized_subs": optimized_subs,
            "raw_optimized_subs": list(optimized_subs),
            "edl": edl,
            "test_lines": polish_artifacts.lines,
            "debug": {
                "pi_agent": True,
                "canonical_runner": True,
                "task_contracts": ["delete", "polish", "chapter"],
                "default_chunk_first": False,
                "delete": delete_artifacts.debug,
                "polish": polish_artifacts.debug,
            },
        }

    def run(self) -> None:
        for input_path in self.inputs:
            segments, total_length = _load_segments(input_path, self.encoding)
            if not segments:
                logging.warning("No segments found in %s", input_path)
                continue

            base = str(Path(input_path).with_suffix(""))
            optimized_srt = base + ".optimized.srt"
            optimized_raw_srt = base + ".optimized.raw.srt"
            cache_dir = Path.cwd() / ".cache" / "auto_edit"
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_base = cache_dir / Path(base).name
            edl_json = str(cache_base) + ".edl.json"
            debug_json = str(cache_base) + ".debug.json"

            if _maybe_skip(optimized_srt, self.force):
                continue

            result = self._auto_edit_segments(segments, total_length)
            _write_optimized_srt(optimized_srt, result["optimized_subs"], self.encoding)
            _write_optimized_srt(optimized_raw_srt, result["raw_optimized_subs"], self.encoding)
            _write_json(edl_json, result["edl"])
            _write_json(debug_json, result["debug"])
            test_text = Path(optimized_srt).with_suffix(".test.txt")
            write_test_text(result["test_lines"], test_text)
            self.last_result = {
                **result,
                "optimized_srt_path": optimized_srt,
                "optimized_raw_srt_path": optimized_raw_srt,
                "edl_path": edl_json,
                "debug_json_path": debug_json,
                "test_text_path": str(test_text),
            }
