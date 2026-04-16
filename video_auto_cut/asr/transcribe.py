from __future__ import annotations

import datetime as dt
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Iterable

import srt

from ..shared.interfaces import PipelineOptions
from .dashscope_filetrans import DashScopeFiletransClient, DashScopeFiletransConfig
from .filetrans_like import FiletransSegment, FiletransTask, segments_to_tokens
from .oss_uploader import OSSAudioUploader, create_oss_uploader_from_config


class Transcribe:
    def __init__(
        self,
        args_or_input: Any,
        options: PipelineOptions | None = None,
        *,
        oss_object_key: str | None = None,
        progress_callback=None,
    ):
        self.options = options
        self.args = args_or_input if options is None else None
        if options is None:
            self.inputs = [str(path) for path in getattr(args_or_input, "inputs", [])]
            self.force = bool(getattr(args_or_input, "force", False))
            self.encoding = str(getattr(args_or_input, "encoding", "utf-8"))
            self.lang = getattr(args_or_input, "lang", None)
            self.prompt = str(getattr(args_or_input, "prompt", ""))
            self.oss_object_key = getattr(args_or_input, "oss_object_key", None) or None
            self.progress_callback = getattr(args_or_input, "asr_progress_callback", None)
        else:
            self.inputs = [str(Path(args_or_input))]
            self.force = bool(options.force)
            self.encoding = options.encoding
            self.lang = options.lang
            self.prompt = options.prompt
            self.oss_object_key = oss_object_key
            self.progress_callback = progress_callback
        self.asr_backend = (
            (
                options.asr_backend
                if options is not None
                else getattr(args_or_input, "asr_backend", "dashscope_filetrans")
            )
            or "dashscope_filetrans"
        ).strip().lower()
        if self.asr_backend != "dashscope_filetrans":
            raise RuntimeError(
                f"Unsupported ASR backend for web deployment: {self.asr_backend}. "
                "Only dashscope_filetrans is supported."
            )

        self.filetrans_client: DashScopeFiletransClient | None = None
        self.oss_uploader: OSSAudioUploader | None = None
        self._init_dashscope_filetrans()

    def _init_dashscope_filetrans(self) -> None:
        source = self.options or self.args
        config = DashScopeFiletransConfig(
            base_url=(getattr(source, "asr_dashscope_base_url", "") or "").strip(),
            api_key=(getattr(source, "asr_dashscope_api_key", "") or "").strip(),
            model=(getattr(source, "asr_dashscope_model", "qwen3-asr-flash-filetrans") or "").strip(),
            task=(getattr(source, "asr_dashscope_task", "") or "").strip() or None,
            poll_seconds=max(0.5, float(getattr(source, "asr_dashscope_poll_seconds", 2.0))),
            timeout_seconds=max(30.0, float(getattr(source, "asr_dashscope_timeout_seconds", 3600.0))),
            language=(getattr(source, "asr_dashscope_language", "") or "").strip() or None,
            language_hints=tuple(getattr(source, "asr_dashscope_language_hints", []) or []),
            text=(getattr(source, "asr_dashscope_context", "") or "").strip(),
            enable_itn=bool(getattr(source, "asr_dashscope_enable_itn", False)),
            enable_words=bool(getattr(source, "asr_dashscope_enable_words", False)),
            channel_ids=tuple(
                int(max(0, int(item)))
                for item in (getattr(source, "asr_dashscope_channel_ids", [0]) or [0])
            ),
            word_split_enabled=bool(getattr(source, "asr_dashscope_word_split_enabled", True)),
            word_split_on_comma=bool(getattr(source, "asr_dashscope_word_split_on_comma", True)),
            word_split_comma_pause_s=float(
                max(0.0, float(getattr(source, "asr_dashscope_word_split_comma_pause_s", 0.4)))
            ),
            word_split_min_chars=int(
                max(1, int(getattr(source, "asr_dashscope_word_split_min_chars", 18)))
            ),
            word_vad_gap_s=float(max(0.0, float(getattr(source, "asr_dashscope_word_vad_gap_s", 0.6)))),
            word_max_segment_s=float(
                max(1.0, float(getattr(source, "asr_dashscope_word_max_segment_s", 8.0))
            )),
        )
        self.filetrans_client = DashScopeFiletransClient(config)
        oss_ok = bool(
            (getattr(source, "asr_oss_endpoint", "") or "").strip()
            and (getattr(source, "asr_oss_bucket", "") or "").strip()
            and (getattr(source, "asr_oss_access_key_id", "") or "").strip()
            and (getattr(source, "asr_oss_access_key_secret", "") or "").strip()
        )
        if oss_ok:
            self.oss_uploader = create_oss_uploader_from_config(source)
            logging.info("[asr] using own OSS bucket for upload")
        else:
            logging.info("[asr] own OSS upload is unavailable because OSS config is incomplete")
        logging.info(
            "Init DashScope Filetrans backend with model=%s task=%s enable_words=%s word_split=%s",
            config.model,
            config.task,
            config.enable_words,
            config.word_split_enabled,
        )
        if bool(getattr(self.args, "asr_dashscope_sentence_rule_with_punc", True)) and not config.enable_words:
            logging.info(
                "[asr] sentence rule with punctuation is enabled via local post-process because enable_words=false"
            )
        if bool(getattr(self.args, "asr_dashscope_sentence_rule_with_punc", True)) and config.enable_words:
            logging.info("[asr] sentence rule with punctuation follows cloud sentence boundaries (enable_words=true)")

    def run(self):
        for input_path in self.inputs:
            logging.info("Transcribing %s", input_path)
            base, _ = os.path.splitext(input_path)
            output_srt = base + ".srt"
            if os.path.exists(output_srt):
                if self.force:
                    logging.info("%s exists. Will overwrite it", output_srt)
                else:
                    logging.info("%s exists, skipping... Use --force to overwrite", output_srt)
                    continue

            tic = time.time()
            tokens = self._dashscope_filetrans_transcribe(
                media_path=input_path,
                lang=self.lang,
                prompt=self.prompt,
                progress_callback=self.progress_callback,
                oss_object_key=self.oss_object_key,
            )
            logging.info("Done transcription in %.1f sec", time.time() - tic)

            subs = self._tokens_to_subtitles(tokens)
            with open(output_srt, "wb") as f:
                f.write(srt.compose(subs).encode(self.encoding, "replace"))
            logging.info("Transcribed %s to %s", input_path, output_srt)

    def _dashscope_filetrans_transcribe(
        self,
        *,
        media_path: str,
        lang: str | None,
        prompt: str,
        progress_callback,
        oss_object_key: str | None = None,
    ) -> list[dict]:
        if self.filetrans_client is None:
            raise RuntimeError("DashScope Filetrans backend not initialized.")

        self._emit_progress(progress_callback, 0.0)
        file_url: str
        if self.oss_uploader is not None and oss_object_key:
            logging.info("[asr] using existing OSS object: %s (skip upload)", oss_object_key)
            file_url = self.oss_uploader.get_signed_get_url(oss_object_key)
        elif self.oss_uploader is not None:
            media_p = Path(media_path)
            logging.info("[asr] oss upload start: %s", media_p)
            uploaded = self.oss_uploader.upload_audio(media_p)
            logging.info(
                "[asr] oss upload done: key=%s size=%s signed_url_len=%s",
                uploaded.object_key,
                uploaded.size_bytes,
                len(uploaded.signed_url),
            )
            file_url = uploaded.signed_url
        else:
            raise RuntimeError(
                "OSS config missing for DashScope Filetrans upload. "
                "Configure OSS_ENDPOINT / OSS_BUCKET / OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET "
                "or pass an existing OSS object key."
            )
        self._emit_progress(progress_callback, 0.08)

        submit = self.filetrans_client.submit(
            file_url=file_url,
            lang=lang,
            prompt=prompt,
        )
        logging.info("[asr] filetrans task submitted: %s", submit.task_id)

        task = self._poll_filetrans_task(submit.task_id, progress_callback=progress_callback)
        if task.task_status != "SUCCEEDED" or not task.transcription_url:
            message = task.error_message or "unknown error"
            raise RuntimeError(f"DashScope ASR task failed: task_id={task.task_id} error={message}")

        logging.info("[asr] filetrans result fetch: %s", task.transcription_url)
        result = None
        retries = 5
        for attempt in range(1, retries + 1):
            try:
                result = self.filetrans_client.load_result(task.transcription_url)
                break
            except Exception:
                if attempt >= retries:
                    raise
                logging.warning(
                    "[asr] filetrans result not ready, retry %s/%s task_id=%s",
                    attempt,
                    retries,
                    task.task_id,
                )
                time.sleep(max(0.5, float(self.filetrans_client.poll_seconds)))
        if result is None:
            raise RuntimeError(f"DashScope ASR result missing: task_id={task.task_id}")
        self._emit_progress(progress_callback, 1.0)

        segments = result.segments
        source = self.options or self.args
        if bool(getattr(source, "asr_dashscope_insert_no_speech", True)):
            segments = self._insert_no_speech_segments(
                segments,
                min_gap_s=float(getattr(source, "asr_dashscope_no_speech_gap_s", 1.0)),
                include_head=bool(getattr(source, "asr_dashscope_insert_head_no_speech", True)),
            )
        sentence_rule_with_punc = bool(
            getattr(source, "asr_dashscope_sentence_rule_with_punc", True)
        )
        enable_words = bool(getattr(source, "asr_dashscope_enable_words", False))
        if sentence_rule_with_punc and not enable_words:
            segments = self._split_segments_by_punctuation(segments)
        return segments_to_tokens(segments)

    @staticmethod
    def _insert_no_speech_segments(
        segments: list[FiletransSegment],
        *,
        min_gap_s: float,
        include_head: bool,
    ) -> list[FiletransSegment]:
        if not segments:
            return []
        threshold = max(0.2, float(min_gap_s))
        ordered = sorted(segments, key=lambda item: (item.start, item.end))
        output: list[FiletransSegment] = []
        if include_head and float(ordered[0].start) >= threshold:
            output.append(
                FiletransSegment(
                    start=0.0,
                    end=float(ordered[0].start),
                    text="< No Speech >",
                )
            )
        prev_end = None
        for seg in ordered:
            if prev_end is not None:
                gap = float(seg.start) - float(prev_end)
                if gap >= threshold:
                    output.append(
                        FiletransSegment(
                            start=float(prev_end),
                            end=float(seg.start),
                            text="< No Speech >",
                        )
                    )
            output.append(seg)
            prev_end = max(float(prev_end or seg.end), float(seg.end))
        return output

    @staticmethod
    def _split_segments_by_punctuation(segments: list[FiletransSegment]) -> list[FiletransSegment]:
        punct_chars = set("，,。！？!?；;")
        strong_breaks = set("。！？!?；;")
        comma_breaks = set("，,")
        punct_limit = 2
        output: list[FiletransSegment] = []
        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            pieces: list[str] = []
            buf: list[str] = []
            punct_count = 0
            for ch in text:
                buf.append(ch)
                if ch in punct_chars:
                    punct_count += 1
                    if ch in strong_breaks or ch in comma_breaks or punct_count >= punct_limit:
                        piece = "".join(buf).strip()
                        if piece:
                            pieces.append(piece)
                        buf = []
                        punct_count = 0
            tail = "".join(buf).strip()
            if tail:
                pieces.append(tail)
            if len(pieces) <= 1:
                output.append(seg)
                continue
            total_len = sum(max(1, len(piece)) for piece in pieces)
            span = max(0.02, float(seg.end - seg.start))
            cursor = float(seg.start)
            for idx, piece in enumerate(pieces):
                ratio = float(max(1, len(piece))) / float(total_len)
                piece_span = span * ratio
                start = cursor
                end = float(seg.end) if idx == len(pieces) - 1 else min(float(seg.end), cursor + piece_span)
                if end <= start:
                    end = start + 0.01
                output.append(FiletransSegment(start=start, end=end, text=piece))
                cursor = end
        output.sort(key=lambda item: (item.start, item.end))
        return output

    def _poll_filetrans_task(
        self,
        task_id: str,
        *,
        progress_callback,
    ) -> FiletransTask:
        if self.filetrans_client is None:
            raise RuntimeError("DashScope Filetrans backend not initialized.")

        timeout = max(30.0, float(self.filetrans_client.timeout_seconds))
        poll_interval = max(0.5, float(self.filetrans_client.poll_seconds))
        begin = time.time()
        deadline = begin + timeout
        last_status = ""

        while True:
            task = self.filetrans_client.poll(task_id)
            if task.task_status != last_status:
                logging.info("[asr] filetrans task status=%s task_id=%s", task.task_status, task_id)
                last_status = task.task_status

            if task.task_status == "SUCCEEDED" and task.transcription_url:
                return task
            if task.task_status == "FAILED":
                return task

            now = time.time()
            if now >= deadline:
                raise RuntimeError(
                    f"DashScope ASR timeout after {timeout:.0f}s (task_id={task_id})"
                )

            elapsed = max(0.0, now - begin)
            ratio = min(0.95, 0.08 + 0.87 * (elapsed / timeout))
            self._emit_progress(progress_callback, ratio)
            time.sleep(min(poll_interval, max(0.1, deadline - now)))

    @staticmethod
    def _emit_progress(callback: Callable[[float], None], ratio: float) -> None:
        if not callable(callback):
            return
        try:
            normalized = max(0.0, min(1.0, float(ratio)))
            callback(normalized)
        except Exception:
            logging.exception("asr progress callback failed")

    @staticmethod
    def _tokens_to_subtitles(tokens: Iterable[dict]) -> list[srt.Subtitle]:
        rows: list[tuple[float, float, str]] = []
        for item in tokens:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            try:
                start = float(item.get("start"))
                end = float(item.get("end"))
            except Exception:
                continue
            if end <= start:
                end = start + 0.01
            rows.append((start, end, text))
        rows.sort(key=lambda row: (row[0], row[1]))
        result: list[srt.Subtitle] = []
        for index, (start, end, text) in enumerate(rows, start=1):
            result.append(
                srt.Subtitle(
                    index=index,
                    start=dt.timedelta(seconds=max(0.0, start)),
                    end=dt.timedelta(seconds=max(0.0, end)),
                    content=text,
                )
            )
        return result
