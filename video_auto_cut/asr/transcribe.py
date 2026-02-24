import logging
import os
import time

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

        self.model = qwen3_asr.Qwen3Model(
            sample_rate=self.sampling_rate,
            gap_s=float(getattr(self.args, "qwen3_gap", 0.6)),
            max_seg_s=float(getattr(self.args, "qwen3_max_seg", 20.0)),
            max_chars=int(getattr(self.args, "qwen3_max_chars", 0)),
            no_speech_gap_s=float(getattr(self.args, "qwen3_no_speech_gap", 1.0)),
            language=getattr(self.args, "qwen3_language", None),
            use_punct=bool(getattr(self.args, "qwen3_use_punct", True)),
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
            tokens = self.model.transcribe(
                audio,
                speech_array_indices=[{"start": 0, "end": len(audio)}],
                lang=getattr(self.args, "qwen3_language", None)
                or getattr(self.args, "lang", None),
                prompt=getattr(self.args, "prompt", ""),
            )
            logging.info("Done transcription in %.1f sec", time.time() - tic)

            subs = self.model.gen_srt(tokens)
            with open(output_srt, "wb") as f:
                f.write(srt.compose(subs).encode(getattr(self.args, "encoding", "utf-8"), "replace"))
            logging.info("Transcribed %s to %s", input_path, output_srt)
