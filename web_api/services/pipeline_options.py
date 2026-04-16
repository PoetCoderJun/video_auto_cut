from __future__ import annotations

from video_auto_cut.orchestration.pipeline_options_builder import build_pipeline_options_from_settings
from video_auto_cut.orchestration.pipeline_service import PipelineOptions

from ..config import get_settings


def build_pipeline_options(**overrides: object) -> PipelineOptions:
    settings = get_settings()
    return build_pipeline_options_from_settings(settings, **overrides)
