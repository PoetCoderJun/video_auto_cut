from __future__ import annotations

import os
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path

from video_auto_cut.orchestration.pipeline_options_builder import build_pipeline_options_from_env
from video_auto_cut.shared.interfaces import PipelineOptions


@dataclass(frozen=True)
class Settings:
    work_dir: Path
    turso_local_replica_path: Path
    turso_database_url: str | None
    turso_auth_token: str | None
    turso_sync_interval: float
    max_upload_mb: int
    cleanup_enabled: bool
    cleanup_interval_seconds: float
    cleanup_ttl_seconds: int
    cleanup_batch_size: int
    cleanup_on_startup: bool
    asr_dashscope_base_url: str
    asr_dashscope_model: str
    asr_dashscope_task: str
    asr_dashscope_api_key: str | None
    asr_dashscope_poll_seconds: float
    asr_dashscope_timeout_seconds: float
    asr_dashscope_language: str | None
    asr_dashscope_language_hints: tuple[str, ...]
    asr_dashscope_context: str
    asr_dashscope_enable_itn: bool
    asr_dashscope_enable_words: bool
    asr_dashscope_channel_ids: tuple[int, ...]
    asr_dashscope_sentence_rule_with_punc: bool
    asr_dashscope_word_split_enabled: bool
    asr_dashscope_word_split_on_comma: bool
    asr_dashscope_word_split_comma_pause_s: float
    asr_dashscope_word_split_min_chars: int
    asr_dashscope_word_vad_gap_s: float
    asr_dashscope_word_max_segment_s: float
    asr_dashscope_no_speech_gap_s: float
    asr_dashscope_insert_no_speech: bool
    asr_dashscope_insert_head_no_speech: bool
    asr_oss_endpoint: str | None
    asr_oss_bucket: str | None
    asr_oss_access_key_id: str | None
    asr_oss_access_key_secret: str | None
    asr_oss_prefix: str
    asr_oss_signed_url_ttl_seconds: int
    lang: str
    llm_base_url: str | None
    llm_model: str | None
    topic_llm_model: str | None
    llm_api_key: str | None
    llm_timeout: int
    llm_temperature: float
    llm_max_tokens: int | None
    auto_edit_llm_concurrency: int
    topic_max_topics: int
    topic_title_max_chars: int
    cut_merge_gap: float
    auth_enabled: bool
    auth_jwks_url: str | None
    auth_issuer: str | None
    auth_audience: str | None
    auth_jwt_leeway_seconds: int
    public_invite_credits: int
    public_rate_limit_window_seconds: int
    public_invite_rate_limit: int
    public_coupon_verify_rate_limit: int
    max_json_body_bytes: int
    web_cors_allowed_origins: tuple[str, ...]
    web_cors_allow_credentials: bool
    web_cors_allowed_methods: tuple[str, ...]
    web_cors_allowed_headers: tuple[str, ...]
    web_cors_expose_headers: tuple[str, ...]


_PIPELINE_OPTION_FIELD_NAMES = {field.name for field in fields(PipelineOptions)}
_SETTINGS_PIPELINE_FIELD_NAMES = tuple(
    field.name for field in fields(Settings) if field.name in _PIPELINE_OPTION_FIELD_NAMES
)


def _build_settings_pipeline_values(pipeline_options: PipelineOptions) -> dict[str, object]:
    values = {
        name: getattr(pipeline_options, name)
        for name in _SETTINGS_PIPELINE_FIELD_NAMES
    }
    values.update(
        {
            "asr_dashscope_poll_seconds": max(0.5, pipeline_options.asr_dashscope_poll_seconds),
            "asr_dashscope_timeout_seconds": max(30.0, pipeline_options.asr_dashscope_timeout_seconds),
            "asr_dashscope_word_split_comma_pause_s": max(
                0.0, pipeline_options.asr_dashscope_word_split_comma_pause_s
            ),
            "asr_dashscope_word_split_min_chars": max(1, pipeline_options.asr_dashscope_word_split_min_chars),
            "asr_dashscope_word_vad_gap_s": max(0.0, pipeline_options.asr_dashscope_word_vad_gap_s),
            "asr_dashscope_word_max_segment_s": max(1.0, pipeline_options.asr_dashscope_word_max_segment_s),
            "asr_dashscope_no_speech_gap_s": max(0.2, pipeline_options.asr_dashscope_no_speech_gap_s),
            "asr_oss_signed_url_ttl_seconds": max(60, pipeline_options.asr_oss_signed_url_ttl_seconds),
            "auto_edit_llm_concurrency": max(1, pipeline_options.auto_edit_llm_concurrency),
            "topic_max_topics": min(6, pipeline_options.topic_max_topics),
        }
    )
    return values


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    def parse_csv(value: str) -> tuple[str, ...]:
        return tuple(item.strip() for item in value.split(",") if item.strip())

    def getenv_first(*names: str) -> str | None:
        for name in names:
            value = os.getenv(name)
            if value is None:
                continue
            stripped = value.strip()
            if stripped:
                return stripped
        return None

    repo_root = Path(__file__).resolve().parents[1]
    work_dir = Path(os.getenv("WORK_DIR", str(repo_root / "workdir"))).expanduser().resolve()
    replica_path_raw = os.getenv("TURSO_LOCAL_REPLICA_PATH") or str(work_dir / "web_api_turso_replica.db")
    turso_local_replica_path = Path(replica_path_raw).expanduser().resolve()
    turso_database_url = (os.getenv("TURSO_DATABASE_URL") or "").strip() or None
    turso_auth_token = (os.getenv("TURSO_AUTH_TOKEN") or "").strip() or None
    auth_base_url = (
        (os.getenv("WEB_AUTH_BASE_URL") or "").strip()
        or (os.getenv("BETTER_AUTH_URL") or "").strip()
        or (os.getenv("NEXT_PUBLIC_SITE_URL") or "").strip()
        or "http://127.0.0.1:3000"
    )
    auth_jwks_url = (os.getenv("WEB_AUTH_JWKS_URL") or "").strip() or f"{auth_base_url.rstrip('/')}/api/auth/jwks"
    auth_issuer = (os.getenv("WEB_AUTH_ISSUER") or "").strip() or auth_base_url
    auth_audience = (os.getenv("WEB_AUTH_AUDIENCE") or "").strip() or auth_base_url
    cors_origins_raw = (
        os.getenv("WEB_CORS_ALLOWED_ORIGINS")
        or "http://127.0.0.1:3000,http://localhost:3000"
    ).strip()
    cors_methods_raw = (os.getenv("WEB_CORS_ALLOWED_METHODS") or "GET,POST,PUT,PATCH,DELETE,OPTIONS").strip()
    cors_headers_raw = (os.getenv("WEB_CORS_ALLOWED_HEADERS") or "*").strip()
    cors_expose_headers_raw = (os.getenv("WEB_CORS_EXPOSE_HEADERS") or "").strip()
    pipeline_options = build_pipeline_options_from_env(
        lang=(os.getenv("WEB_LANG") or "Chinese").strip() or "Chinese",
        llm_model=(os.getenv("LLM_MODEL") or "qwen-plus").strip() or "qwen-plus",
        topic_llm_model=(os.getenv("TOPIC_LLM_MODEL") or os.getenv("LLM_MODEL") or "kimi-k2.5").strip()
        or "kimi-k2.5",
        topic_max_topics=min(
            6,
            int((os.getenv("TOPIC_MAX_TOPICS") or "5").strip() or "5"),
        ),
    )
    if pipeline_options.asr_backend != "dashscope_filetrans":
        raise RuntimeError(
            f"Unsupported ASR_BACKEND={pipeline_options.asr_backend}. "
            "This deployment only supports ASR_BACKEND=dashscope_filetrans."
        )
    pipeline_settings = _build_settings_pipeline_values(pipeline_options)

    return Settings(
        work_dir=work_dir,
        turso_local_replica_path=turso_local_replica_path,
        turso_database_url=turso_database_url,
        turso_auth_token=turso_auth_token,
        turso_sync_interval=max(0.0, float(os.getenv("TURSO_SYNC_INTERVAL", "2.0"))),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "2048")),
        cleanup_enabled=os.getenv("WEB_CLEANUP_ENABLED", "1").strip().lower() in {"1", "true", "yes"},
        cleanup_interval_seconds=max(1.0, float(os.getenv("WEB_CLEANUP_INTERVAL_SECONDS", "300"))),
        cleanup_ttl_seconds=max(0, int(os.getenv("WEB_CLEANUP_TTL_SECONDS", "3600"))),
        cleanup_batch_size=max(1, int(os.getenv("WEB_CLEANUP_BATCH_SIZE", "10"))),
        cleanup_on_startup=os.getenv("WEB_CLEANUP_ON_STARTUP", "1").strip().lower() in {"1", "true", "yes"},
        **pipeline_settings,
        auth_enabled=os.getenv("WEB_AUTH_ENABLED", "1").strip().lower() in {"1", "true", "yes"},
        auth_jwks_url=auth_jwks_url,
        auth_issuer=auth_issuer,
        auth_audience=auth_audience,
        auth_jwt_leeway_seconds=max(0, int(os.getenv("WEB_AUTH_JWT_LEEWAY_SECONDS", "10"))),
        public_invite_credits=max(1, int(os.getenv("PUBLIC_INVITE_CREDITS", "10"))),
        public_rate_limit_window_seconds=max(
            1, int(os.getenv("WEB_PUBLIC_RATE_LIMIT_WINDOW_SECONDS", "60"))
        ),
        public_invite_rate_limit=max(1, int(os.getenv("WEB_PUBLIC_INVITE_RATE_LIMIT", "5"))),
        public_coupon_verify_rate_limit=max(
            1, int(os.getenv("WEB_PUBLIC_COUPON_VERIFY_RATE_LIMIT", "30"))
        ),
        max_json_body_bytes=max(1024, int(os.getenv("WEB_MAX_JSON_BODY_BYTES", "1048576"))),
        web_cors_allowed_origins=parse_csv(cors_origins_raw),
        web_cors_allow_credentials=os.getenv("WEB_CORS_ALLOW_CREDENTIALS", "1").strip().lower()
        in {"1", "true", "yes"},
        web_cors_allowed_methods=parse_csv(cors_methods_raw),
        web_cors_allowed_headers=parse_csv(cors_headers_raw),
        web_cors_expose_headers=parse_csv(cors_expose_headers_raw),
    )


def ensure_work_dirs() -> None:
    settings = get_settings()
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    settings.turso_local_replica_path.parent.mkdir(parents=True, exist_ok=True)


def job_dir(job_id: str) -> Path:
    settings = get_settings()
    return settings.work_dir / "jobs" / job_id


def ensure_job_dirs(job_id: str) -> dict[str, Path]:
    base = job_dir(job_id)
    paths = {
        "base": base,
        "input": base / "input",
        "test": base / "test",
        "render": base / "render",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths
