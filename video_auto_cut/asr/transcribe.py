from __future__ import annotations

import logging
import os
import time
from typing import Callable, Iterable

import srt

from ..shared import media
from . import qwen3_asr


class Transcribe:
    def __init__(self, args):
        self.args = args
        self.sampling_rate = 16000

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

    def run(self):
        for input_path in self.args.inputs:
            logging.info("Transcribing %s", input_path)
            base, _ = os.path.splitext(input_path)
            output_srt = base + ".srt"
            if media.check_exists(output_srt, bool(getattr(self.args, "force", False))):
                continue

            audio = media.load_audio(input_path, sr=self.sampling_rate)
            tic = time.time()
            language = getattr(self.args, "qwen3_language", None) or getattr(self.args, "lang", None)
            prompt = getattr(self.args, "prompt", "")
            asr_progress_callback = getattr(self.args, "asr_progress_callback", None)

            if callable(asr_progress_callback):
                tokens = self._transcribe_with_progress(
                    audio,
                    lang=language,
                    prompt=prompt,
                    progress_callback=asr_progress_callback,
                )
            else:
                tokens = self.model.transcribe(
                    audio,
                    speech_array_indices=[{"start": 0, "end": len(audio)}],
                    lang=language,
                    prompt=prompt,
                )
            logging.info("Done transcription in %.1f sec", time.time() - tic)

            subs = self.model.gen_srt(tokens)
            with open(output_srt, "wb") as f:
                f.write(srt.compose(subs).encode(getattr(self.args, "encoding", "utf-8"), "replace"))
            logging.info("Transcribed %s to %s", input_path, output_srt)

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
