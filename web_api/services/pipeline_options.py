from __future__ import annotations

from video_auto_cut.orchestration.pipeline_service import PipelineOptions

from ..config import get_settings
from ..constants import DEFAULT_ENCODING


def build_pipeline_options(**overrides: object) -> PipelineOptions:
    settings = get_settings()
    values = {
        "encoding": DEFAULT_ENCODING,
        "force": True,
        "device": settings.device,
        "lang": settings.lang,
        "prompt": "",
        "qwen3_model": settings.qwen3_model,
        "qwen3_aligner": settings.qwen3_aligner,
        "qwen3_language": None,
        "qwen3_use_modelscope": False,
        "qwen3_offline": True,
        "qwen3_gap": 0.6,
        "qwen3_max_seg": 20.0,
        "qwen3_max_chars": 0,
        "qwen3_no_speech_gap": 1.0,
        "qwen3_use_punct": True,
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
        "llm_api_key": settings.llm_api_key,
        "llm_timeout": settings.llm_timeout,
        "llm_temperature": settings.llm_temperature,
        "llm_max_tokens": settings.llm_max_tokens,
        "auto_edit_merge_gap": 0.5,
        "auto_edit_pad_head": 0.0,
        "auto_edit_pad_tail": 0.0,
        "bitrate": settings.render_bitrate,
        "cut_merge_gap": settings.cut_merge_gap,
        "render_output": None,
        "render_cut_srt_output": None,
        "render_fps": None,
        "render_preview": False,
        "render_codec": None,
        "render_crf": None,
        "render_topics": False,
        "render_topics_input": None,
        "topic_output": None,
        "topic_strict": False,
        "topic_max_topics": settings.topic_max_topics,
        "topic_summary_max_chars": settings.topic_summary_max_chars,
    }
    values.update(overrides)
    return PipelineOptions(**values)
