from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    work_dir: Path
    turso_local_replica_path: Path
    turso_database_url: str | None
    turso_auth_token: str | None
    turso_sync_interval: float
    max_upload_mb: int
    worker_poll_seconds: float
    cleanup_enabled: bool
    cleanup_interval_seconds: float
    cleanup_ttl_seconds: int
    cleanup_batch_size: int
    cleanup_on_download: bool
    cleanup_on_startup: bool
    embedded_worker: bool
    qwen3_prewarm_on_startup: bool
    qwen3_model: str
    qwen3_aligner: str
    qwen3_progress_chunk_s: float
    qwen3_correct: bool
    qwen3_correct_max_diff_ratio: float
    asr_backend: str
    asr_dashscope_base_url: str
    asr_dashscope_model: str
    asr_dashscope_task: str
    asr_dashscope_api_key: str | None
    asr_dashscope_poll_seconds: float
    asr_dashscope_timeout_seconds: float
    asr_dashscope_language_hints: tuple[str, ...]
    asr_dashscope_context: str
    asr_dashscope_enable_words: bool
    asr_dashscope_sentence_rule_with_punc: bool
    asr_dashscope_word_split_enabled: bool
    asr_dashscope_word_split_on_comma: bool
    asr_dashscope_word_split_comma_pause_s: float
    asr_dashscope_word_split_min_chars: int
    asr_dashscope_word_vad_gap_s: float
    asr_dashscope_word_max_segment_s: float
    asr_dashscope_insert_no_speech: bool
    asr_dashscope_insert_head_no_speech: bool
    asr_oss_endpoint: str | None
    asr_oss_bucket: str | None
    asr_oss_access_key_id: str | None
    asr_oss_access_key_secret: str | None
    asr_oss_prefix: str
    asr_oss_signed_url_ttl_seconds: int
    device: str
    lang: str
    llm_base_url: str | None
    llm_model: str | None
    llm_api_key: str | None
    llm_timeout: int
    llm_temperature: float
    llm_max_tokens: int
    topic_max_topics: int
    topic_title_max_chars: int
    topic_summary_max_chars: int
    render_bitrate: str
    cut_merge_gap: float
    auth_enabled: bool
    auth_jwks_url: str | None
    auth_issuer: str | None
    auth_audience: str | None
    auth_jwt_leeway_seconds: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[1]
    work_dir = Path(os.getenv("WORK_DIR", str(repo_root / "workdir"))).expanduser().resolve()
    replica_path_raw = os.getenv("TURSO_LOCAL_REPLICA_PATH") or str(work_dir / "web_api_turso_replica.db")
    turso_local_replica_path = Path(replica_path_raw).expanduser().resolve()
    turso_database_url = (os.getenv("TURSO_DATABASE_URL") or "").strip() or None
    turso_auth_token = (os.getenv("TURSO_AUTH_TOKEN") or "").strip() or None
    llm_api_key = os.getenv("LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    asr_api_key = os.getenv("ASR_DASHSCOPE_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    asr_language_hints_raw = (os.getenv("ASR_DASHSCOPE_LANGUAGE_HINTS") or "").strip()
    asr_language_hints = tuple(
        item.strip() for item in asr_language_hints_raw.split(",") if item.strip()
    )
    auth_base_url = (
        (os.getenv("WEB_AUTH_BASE_URL") or "").strip()
        or (os.getenv("BETTER_AUTH_URL") or "").strip()
        or (os.getenv("NEXT_PUBLIC_SITE_URL") or "").strip()
        or "http://127.0.0.1:3000"
    )
    auth_jwks_url = (os.getenv("WEB_AUTH_JWKS_URL") or "").strip() or f"{auth_base_url.rstrip('/')}/api/auth/jwks"
    auth_issuer = (os.getenv("WEB_AUTH_ISSUER") or "").strip() or auth_base_url
    auth_audience = (os.getenv("WEB_AUTH_AUDIENCE") or "").strip() or auth_base_url

    return Settings(
        work_dir=work_dir,
        turso_local_replica_path=turso_local_replica_path,
        turso_database_url=turso_database_url,
        turso_auth_token=turso_auth_token,
        turso_sync_interval=max(0.0, float(os.getenv("TURSO_SYNC_INTERVAL", "2.0"))),
        max_upload_mb=int(os.getenv("MAX_UPLOAD_MB", "2048")),
        worker_poll_seconds=float(os.getenv("WORKER_POLL_SECONDS", "1.0")),
        cleanup_enabled=os.getenv("WEB_CLEANUP_ENABLED", "1").strip().lower() in {"1", "true", "yes"},
        cleanup_interval_seconds=max(1.0, float(os.getenv("WEB_CLEANUP_INTERVAL_SECONDS", "300"))),
        cleanup_ttl_seconds=max(0, int(os.getenv("WEB_CLEANUP_TTL_SECONDS", "3600"))),
        cleanup_batch_size=max(1, int(os.getenv("WEB_CLEANUP_BATCH_SIZE", "10"))),
        cleanup_on_download=os.getenv("WEB_CLEANUP_ON_DOWNLOAD", "1").strip().lower() in {"1", "true", "yes"},
        cleanup_on_startup=os.getenv("WEB_CLEANUP_ON_STARTUP", "1").strip().lower() in {"1", "true", "yes"},
        embedded_worker=os.getenv("WEB_EMBEDDED_WORKER", "0").strip().lower() in {"1", "true", "yes"},
        qwen3_prewarm_on_startup=os.getenv("WEB_QWEN3_PREWARM_ON_STARTUP", "1").strip().lower()
        in {"1", "true", "yes"},
        qwen3_model=os.getenv("QWEN3_MODEL", "./model/Qwen3-ASR-0.6B"),
        qwen3_aligner=os.getenv("QWEN3_ALIGNER", "./model/Qwen3-ForcedAligner-0.6B"),
        qwen3_progress_chunk_s=max(2.0, float(os.getenv("QWEN3_PROGRESS_CHUNK_S", "8.0"))),
        qwen3_correct=os.getenv("QWEN3_CORRECT", "1").strip().lower() in {"1", "true", "yes"},
        qwen3_correct_max_diff_ratio=float(os.getenv("QWEN3_CORRECT_MAX_DIFF_RATIO", "0.3")),
        asr_backend=(os.getenv("ASR_BACKEND", "dashscope_filetrans").strip().lower() or "dashscope_filetrans"),
        asr_dashscope_base_url=(
            os.getenv("ASR_DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com")
            .strip()
            .rstrip("/")
        ),
        asr_dashscope_model=os.getenv("ASR_DASHSCOPE_MODEL", "qwen3-asr-flash-filetrans").strip(),
        asr_dashscope_task=os.getenv("ASR_DASHSCOPE_TASK", "").strip(),
        asr_dashscope_api_key=(asr_api_key or "").strip() or None,
        asr_dashscope_poll_seconds=max(0.5, float(os.getenv("ASR_DASHSCOPE_POLL_SECONDS", "2.0"))),
        asr_dashscope_timeout_seconds=max(
            30.0, float(os.getenv("ASR_DASHSCOPE_TIMEOUT_SECONDS", "3600"))
        ),
        asr_dashscope_language_hints=asr_language_hints,
        asr_dashscope_context=os.getenv("ASR_DASHSCOPE_CONTEXT", "").strip(),
        asr_dashscope_enable_words=os.getenv("ASR_DASHSCOPE_ENABLE_WORDS", "1").strip().lower()
        in {"1", "true", "yes"},
        asr_dashscope_sentence_rule_with_punc=os.getenv(
            "ASR_DASHSCOPE_SENTENCE_RULE_WITH_PUNC", "1"
        ).strip().lower()
        in {"1", "true", "yes"},
        asr_dashscope_word_split_enabled=os.getenv(
            "ASR_DASHSCOPE_WORD_SPLIT_ENABLED", "1"
        ).strip().lower()
        in {"1", "true", "yes"},
        asr_dashscope_word_split_on_comma=os.getenv(
            "ASR_DASHSCOPE_WORD_SPLIT_ON_COMMA", "1"
        ).strip().lower()
        in {"1", "true", "yes"},
        asr_dashscope_word_split_comma_pause_s=max(
            0.0, float(os.getenv("ASR_DASHSCOPE_WORD_SPLIT_COMMA_PAUSE_S", "0.4"))
        ),
        asr_dashscope_word_split_min_chars=max(
            1, int(os.getenv("ASR_DASHSCOPE_WORD_SPLIT_MIN_CHARS", "12"))
        ),
        asr_dashscope_word_vad_gap_s=max(
            0.0, float(os.getenv("ASR_DASHSCOPE_WORD_VAD_GAP_S", "1.0"))
        ),
        asr_dashscope_word_max_segment_s=max(
            1.0, float(os.getenv("ASR_DASHSCOPE_WORD_MAX_SEGMENT_S", "8.0"))
        ),
        asr_dashscope_insert_no_speech=os.getenv(
            "ASR_DASHSCOPE_INSERT_NO_SPEECH", "1"
        ).strip().lower()
        in {"1", "true", "yes"},
        asr_dashscope_insert_head_no_speech=os.getenv(
            "ASR_DASHSCOPE_INSERT_HEAD_NO_SPEECH", "1"
        ).strip().lower()
        in {"1", "true", "yes"},
        asr_oss_endpoint=(os.getenv("OSS_ENDPOINT") or "").strip() or None,
        asr_oss_bucket=(os.getenv("OSS_BUCKET") or "").strip() or None,
        asr_oss_access_key_id=(os.getenv("OSS_ACCESS_KEY_ID") or "").strip() or None,
        asr_oss_access_key_secret=(os.getenv("OSS_ACCESS_KEY_SECRET") or "").strip() or None,
        asr_oss_prefix=(os.getenv("OSS_AUDIO_PREFIX") or "video-auto-cut/asr").strip().strip("/"),
        asr_oss_signed_url_ttl_seconds=max(
            60, int(os.getenv("OSS_SIGNED_URL_TTL_SECONDS", "86400"))
        ),
        device=os.getenv("WEB_DEVICE", "cpu"),
        lang=os.getenv("WEB_LANG", "Chinese"),
        llm_base_url=(os.getenv("LLM_BASE_URL") or "").strip() or None,
        llm_model=(os.getenv("LLM_MODEL") or "").strip() or None,
        llm_api_key=(llm_api_key or "").strip() or None,
        llm_timeout=int(os.getenv("LLM_TIMEOUT", "60")),
        llm_temperature=float(os.getenv("LLM_TEMPERATURE", "0.2")),
        llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "4096")),
        topic_max_topics=int(os.getenv("TOPIC_MAX_TOPICS", "8")),
        topic_title_max_chars=int(os.getenv("TOPIC_TITLE_MAX_CHARS", "6")),
        topic_summary_max_chars=int(os.getenv("TOPIC_SUMMARY_MAX_CHARS", "6")),
        render_bitrate=os.getenv("RENDER_BITRATE", "10m"),
        cut_merge_gap=float(os.getenv("CUT_MERGE_GAP", "0.0")),
        auth_enabled=os.getenv("WEB_AUTH_ENABLED", "1").strip().lower() in {"1", "true", "yes"},
        auth_jwks_url=auth_jwks_url,
        auth_issuer=auth_issuer,
        auth_audience=auth_audience,
        auth_jwt_leeway_seconds=max(0, int(os.getenv("WEB_AUTH_JWT_LEEWAY_SECONDS", "10"))),
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
        "step1": base / "step1",
        "step2": base / "step2",
        "render": base / "render",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths
