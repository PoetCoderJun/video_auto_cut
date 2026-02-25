from __future__ import annotations

import datetime as dt
import logging
import os
import re
import time
from pathlib import Path
from typing import Callable, Iterable

import srt

from ..shared import media
from . import qwen3_asr
from .dashscope_filetrans import DashScopeFiletransClient, DashScopeFiletransConfig
from .filetrans_like import (
    FiletransSegment,
    FiletransTask,
    LocalFiletransLikeASR,
    segments_to_tokens,
)
from .oss_uploader import OSSAudioUploader


class Transcribe:
    def __init__(self, args):
        self.args = args
        self.sampling_rate = 16000
        self.asr_backend = (
            getattr(self.args, "asr_backend", "local_filetrans")
            or "local_filetrans"
        ).strip().lower()
        self.model = None
        self.filetrans_client: DashScopeFiletransClient | None = None
        self.oss_uploader: OSSAudioUploader | None = None

        if self.asr_backend in {"local_filetrans", "local_qwen3"}:
            self._init_local_model()
        elif self.asr_backend == "dashscope_filetrans":
            self._init_dashscope_filetrans()
        else:
            raise RuntimeError(f"Unsupported ASR backend: {self.asr_backend}")

    def _init_local_model(self) -> None:
        tic = time.time()
        model_id = qwen3_asr.default_model_id(
            getattr(self.args, "qwen3_model", None),
            "Qwen3-ASR-0.6B",
            qwen3_asr.DEFAULT_ASR_ID,
        )
        aligner_id = qwen3_asr.default_model_id(
            getattr(self.args, "qwen3_aligner", None),
            "Qwen3-ForcedAligner-0.6B",
            qwen3_asr.DEFAULT_ALIGNER_ID,
        )
        llm_config = None
        qwen3_correct = bool(getattr(self.args, "qwen3_correct", False))
        if qwen3_correct:
            from ..editing import llm_client

            llm_config = llm_client.build_llm_config(
                base_url=getattr(self.args, "llm_base_url", None),
                model=getattr(self.args, "llm_model", None),
                api_key=getattr(self.args, "llm_api_key", None),
                timeout=int(getattr(self.args, "llm_timeout", 60)),
                temperature=float(getattr(self.args, "llm_temperature", 0.2)),
                max_tokens=int(getattr(self.args, "llm_max_tokens", 4096)),
            )
            if not llm_config.get("base_url") or not llm_config.get("model"):
                raise RuntimeError(
                    "Qwen3 ASR correction requires LLM config: llm_base_url and llm_model."
                )

        self.model = qwen3_asr.Qwen3Model(
            sample_rate=self.sampling_rate,
            gap_s=float(getattr(self.args, "qwen3_gap", 0.6)),
            max_seg_s=float(getattr(self.args, "qwen3_max_seg", 20.0)),
            max_chars=int(getattr(self.args, "qwen3_max_chars", 0)),
            no_speech_gap_s=float(getattr(self.args, "qwen3_no_speech_gap", 1.0)),
            language=getattr(self.args, "qwen3_language", None),
            use_punct=bool(getattr(self.args, "qwen3_use_punct", True)),
            correct_with_llm=qwen3_correct,
            llm_config=llm_config,
            correct_max_length_diff_ratio=float(
                getattr(self.args, "qwen3_correct_max_diff_ratio", 0.3)
            ),
        )
        self.model.load(
            model_id=model_id,
            aligner_id=aligner_id,
            device=getattr(self.args, "device", None),
            offline=bool(getattr(self.args, "qwen3_offline", False)),
            use_modelscope=bool(getattr(self.args, "qwen3_use_modelscope", False)),
        )
        elapsed = time.time() - tic
        if getattr(self.model, "last_load_cache_hit", False):
            logging.info("Reuse cached Qwen3 model in %.1f sec", elapsed)
        else:
            logging.info("Done Init Qwen3 model in %.1f sec", elapsed)

    def _init_dashscope_filetrans(self) -> None:
        config = DashScopeFiletransConfig(
            base_url=(getattr(self.args, "asr_dashscope_base_url", "") or "").strip(),
            api_key=(getattr(self.args, "asr_dashscope_api_key", "") or "").strip(),
            model=(getattr(self.args, "asr_dashscope_model", "qwen3-asr-flash-filetrans") or "").strip(),
            task=(getattr(self.args, "asr_dashscope_task", "") or "").strip() or None,
            poll_seconds=max(0.5, float(getattr(self.args, "asr_dashscope_poll_seconds", 2.0))),
            timeout_seconds=max(
                30.0, float(getattr(self.args, "asr_dashscope_timeout_seconds", 3600.0))
            ),
            language_hints=tuple(getattr(self.args, "asr_dashscope_language_hints", []) or []),
            context=(getattr(self.args, "asr_dashscope_context", "") or "").strip(),
            enable_words=bool(getattr(self.args, "asr_dashscope_enable_words", False)),
            word_split_enabled=bool(getattr(self.args, "asr_dashscope_word_split_enabled", True)),
            word_split_on_comma=bool(getattr(self.args, "asr_dashscope_word_split_on_comma", True)),
            word_split_comma_pause_s=float(
                max(0.0, float(getattr(self.args, "asr_dashscope_word_split_comma_pause_s", 0.4)))
            ),
            word_split_min_chars=int(max(1, int(getattr(self.args, "asr_dashscope_word_split_min_chars", 18)))),
            word_vad_gap_s=float(max(0.0, float(getattr(self.args, "asr_dashscope_word_vad_gap_s", 0.6)))),
            word_max_segment_s=float(max(1.0, float(getattr(self.args, "asr_dashscope_word_max_segment_s", 8.0)))),
        )
        self.filetrans_client = DashScopeFiletransClient(config)
        self.oss_uploader = OSSAudioUploader(
            endpoint=(getattr(self.args, "asr_oss_endpoint", "") or "").strip(),
            bucket_name=(getattr(self.args, "asr_oss_bucket", "") or "").strip(),
            access_key_id=(getattr(self.args, "asr_oss_access_key_id", "") or "").strip(),
            access_key_secret=(getattr(self.args, "asr_oss_access_key_secret", "") or "").strip(),
            prefix=(getattr(self.args, "asr_oss_prefix", "video-auto-cut/asr") or "").strip(),
            signed_url_ttl_seconds=int(
                max(60, int(getattr(self.args, "asr_oss_signed_url_ttl_seconds", 86400)))
            ),
        )
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
        for input_path in self.args.inputs:
            logging.info("Transcribing %s", input_path)
            base, _ = os.path.splitext(input_path)
            output_srt = base + ".srt"
            if media.check_exists(output_srt, bool(getattr(self.args, "force", False))):
                continue

            tic = time.time()
            language = getattr(self.args, "qwen3_language", None) or getattr(self.args, "lang", None)
            prompt = getattr(self.args, "prompt", "")
            asr_progress_callback = getattr(self.args, "asr_progress_callback", None)

            tokens = self._filetrans_like_transcribe(
                media_path=input_path,
                lang=language,
                prompt=prompt,
                progress_callback=asr_progress_callback,
            )
            logging.info("Done transcription in %.1f sec", time.time() - tic)

            if self.model is not None:
                subs = self.model.gen_srt(tokens)
            else:
                subs = self._tokens_to_subtitles(tokens)
            with open(output_srt, "wb") as f:
                f.write(srt.compose(subs).encode(getattr(self.args, "encoding", "utf-8"), "replace"))
            logging.info("Transcribed %s to %s", input_path, output_srt)

    def _filetrans_like_transcribe(
        self,
        *,
        media_path: str,
        lang: str | None,
        prompt: str,
        progress_callback,
    ) -> list[dict]:
        if self.asr_backend in {"local_filetrans", "local_qwen3"}:
            return self._local_filetrans_like_transcribe(
                media_path=media_path,
                lang=lang,
                prompt=prompt,
                progress_callback=progress_callback,
            )
        if self.asr_backend == "dashscope_filetrans":
            return self._dashscope_filetrans_transcribe(
                media_path=media_path,
                lang=lang,
                prompt=prompt,
                progress_callback=progress_callback,
            )
        raise RuntimeError(f"Unsupported ASR backend: {self.asr_backend}")

    def _local_filetrans_like_transcribe(
        self,
        *,
        media_path: str,
        lang: str | None,
        prompt: str,
        progress_callback,
    ) -> list[dict]:
        if self.model is None:
            raise RuntimeError("Local ASR backend not initialized.")

        def _transcribe_fn(*, media_path: Path, lang: str | None, prompt: str) -> list[dict]:
            audio = media.load_audio(str(media_path), sr=self.sampling_rate)
            if callable(progress_callback):
                return self._transcribe_with_progress(
                    audio,
                    lang=lang,
                    prompt=prompt,
                    progress_callback=progress_callback,
                )
            return self.model.transcribe(
                audio,
                speech_array_indices=[{"start": 0, "end": len(audio)}],
                lang=lang,
                prompt=prompt,
            )

        media_p = Path(media_path)
        result_dir = media_p.parent / ".asr"
        client = LocalFiletransLikeASR(result_dir=result_dir)
        submit = client.submit(media_path=media_p, transcribe_fn=_transcribe_fn, lang=lang, prompt=prompt)
        task = client.poll(submit.task_id)
        if task.task_status != "SUCCEEDED" or not task.transcription_url:
            raise RuntimeError(f"Local ASR task not finished: {task.task_id} status={task.task_status}")
        result = client.load_result(task.transcription_url)
        return segments_to_tokens(result.segments)

    def _dashscope_filetrans_transcribe(
        self,
        *,
        media_path: str,
        lang: str | None,
        prompt: str,
        progress_callback,
    ) -> list[dict]:
        if self.filetrans_client is None or self.oss_uploader is None:
            raise RuntimeError("DashScope Filetrans backend not initialized.")

        media_p = Path(media_path)
        self._emit_progress(progress_callback, 0.0)
        logging.info("[asr] oss upload start: %s", media_p)
        uploaded = self.oss_uploader.upload_audio(media_p)
        logging.info(
            "[asr] oss upload done: key=%s size=%s signed_url_len=%s",
            uploaded.object_key,
            uploaded.size_bytes,
            len(uploaded.signed_url),
        )
        self._emit_progress(progress_callback, 0.08)

        submit = self.filetrans_client.submit(
            file_url=uploaded.signed_url,
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
        if bool(getattr(self.args, "asr_dashscope_insert_no_speech", True)):
            segments = self._insert_no_speech_segments(
                segments,
                min_gap_s=float(getattr(self.args, "qwen3_no_speech_gap", 1.0)),
                include_head=bool(getattr(self.args, "asr_dashscope_insert_head_no_speech", True)),
            )
        sentence_rule_with_punc = bool(
            getattr(self.args, "asr_dashscope_sentence_rule_with_punc", True)
        )
        enable_words = bool(getattr(self.args, "asr_dashscope_enable_words", False))
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
        punct_pattern = re.compile(r"[^。！？!?；;]+[。！？!?；;]?")
        output: list[FiletransSegment] = []
        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            pieces = [item.strip() for item in punct_pattern.findall(text) if item and item.strip()]
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

    def _transcribe_with_progress(
        self,
        audio,
        *,
        lang: str | None,
        prompt: str,
        progress_callback: Callable[[float], None],
    ) -> list[dict]:
        total_samples = int(len(audio))
        if total_samples <= 0:
            self._emit_progress(progress_callback, 1.0)
            return []

        chunk_seconds = max(
            2.0, float(getattr(self.args, "qwen3_progress_chunk_s", 8.0))
        )
        chunk_samples = max(int(chunk_seconds * self.sampling_rate), self.sampling_rate)
        self._emit_progress(progress_callback, 0.0)

        tokens: list[dict] = []
        cursor = 0
        while cursor < total_samples:
            end = min(total_samples, cursor + chunk_samples)
            chunk_audio = audio[cursor:end]
            chunk_tokens = self.model.transcribe(
                chunk_audio,
                speech_array_indices=[{"start": 0, "end": len(chunk_audio)}],
                lang=lang,
                prompt=prompt,
            )
            offset_s = float(cursor) / float(self.sampling_rate)
            tokens.extend(self._shift_tokens(chunk_tokens, offset_s))
            cursor = end
            self._emit_progress(progress_callback, float(cursor) / float(total_samples))

        tokens.sort(key=lambda item: float(item.get("start", 0.0)))
        return tokens

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

    @staticmethod
    def _shift_tokens(tokens: Iterable[dict], offset_s: float) -> list[dict]:
        shifted: list[dict] = []
        for item in tokens:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            start = item.get("start")
            end = item.get("end")
            if text is None or start is None or end is None:
                continue
            try:
                start_v = float(start) + offset_s
                end_v = float(end) + offset_s
            except Exception:
                continue
            shifted.append(
                {
                    "text": str(text),
                    "start": start_v,
                    "end": end_v if end_v >= start_v else start_v,
                }
            )
        return shifted
