from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from video_auto_cut.shared.dotenv import auto_load_dotenv

try:
    from openai import OpenAI
except ModuleNotFoundError as exc:
    OpenAI = None  # type: ignore[assignment]
    _OPENAI_IMPORT_ERROR: ModuleNotFoundError | None = exc
else:
    _OPENAI_IMPORT_ERROR = None


_OPENAI_CLIENTS_BY_CFG: Dict[Tuple[str, str], Any] = {}
_TRAILING_COMMA_RE = re.compile(r",(?=\s*[}\]])")
_DEFAULT_REQUEST_RETRIES = 3
_DEFAULT_RETRY_BACKOFF_SECONDS = 1.0


def _env_flag(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _normalized_base_url(value: Optional[str]) -> str:
    return str(value or "").strip().rstrip("/").lower()


def _is_moonshot_base_url(value: Optional[str]) -> bool:
    base_url = _normalized_base_url(value)
    return "api.moonshot.cn/v1" in base_url or "platform.moonshot.cn" in base_url


def _is_kimi_k2_family_model(value: Optional[str]) -> bool:
    model = str(value or "").strip().lower()
    return model.startswith("kimi-k2")


def _resolve_api_key(*, api_key: Optional[str], base_url: Optional[str]) -> str:
    candidates = [
        api_key,
        os.environ.get("LLM_API_KEY"),
        os.environ.get("DASHSCOPE_API_KEY"),
        os.environ.get("KIMI_API_KEY"),
        os.environ.get("MOONSHOT_API_KEY"),
    ]
    if _is_moonshot_base_url(base_url):
        candidates = [
            api_key,
            os.environ.get("LLM_API_KEY"),
            os.environ.get("KIMI_API_KEY"),
            os.environ.get("MOONSHOT_API_KEY"),
            os.environ.get("DASHSCOPE_API_KEY"),
        ]
    for candidate in candidates:
        stripped = str(candidate or "").strip()
        if stripped:
            return stripped
    return ""


def build_llm_config(
    base_url: Optional[str],
    model: Optional[str],
    api_key: Optional[str] = None,
    timeout: int = 60,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    enable_thinking: Optional[bool] = None,
) -> Dict[str, Any]:
    auto_load_dotenv(
        [
            Path.cwd() / ".env",
            Path(__file__).resolve().parents[1] / ".env",
            Path(__file__).resolve().parents[2] / ".env",
        ]
    )
    resolved_base_url = (base_url or os.environ.get("LLM_BASE_URL") or "").strip()
    cfg = {
        "base_url": resolved_base_url,
        "model": (model or os.environ.get("LLM_MODEL") or "").strip(),
        "api_key": _resolve_api_key(api_key=api_key, base_url=resolved_base_url),
        "timeout": int(timeout),
        "temperature": float(temperature),
        "max_tokens": int(max_tokens) if max_tokens is not None else None,
        "request_retries": max(
            1,
            int(os.environ.get("LLM_REQUEST_RETRIES", str(_DEFAULT_REQUEST_RETRIES))),
        ),
        "retry_backoff_seconds": max(
            0.0,
            float(
                os.environ.get(
                    "LLM_RETRY_BACKOFF_SECONDS",
                    str(_DEFAULT_RETRY_BACKOFF_SECONDS),
                )
            ),
        ),
        "enable_thinking": (
            bool(enable_thinking)
            if enable_thinking is not None
            else _env_flag(os.environ.get("LLM_ENABLE_THINKING"))
        ),
    }
    return cfg


def _client_cache_key(cfg: Dict[str, Any]) -> Tuple[str, str]:
    return (
        str(cfg.get("base_url") or "").strip(),
        str(cfg.get("api_key") or "").strip(),
    )


def _require_openai_sdk() -> None:
    if OpenAI is None:
        raise RuntimeError(
            "Python package 'openai' is required for Test auto-edit. "
            "Install dependencies with `pip install -r requirements.txt` and rebuild the service image."
        ) from _OPENAI_IMPORT_ERROR


def _get_openai_client(cfg: Dict[str, Any]) -> Any:
    _require_openai_sdk()
    cache_key = _client_cache_key(cfg)
    client = _OPENAI_CLIENTS_BY_CFG.get(cache_key)
    if client is not None:
        return client
    assert OpenAI is not None
    client = OpenAI(
        api_key=cfg.get("api_key", ""),
        base_url=cfg.get("base_url") or "",
    )
    _OPENAI_CLIENTS_BY_CFG[cache_key] = client
    return client


def chat_completion(cfg: Dict[str, Any], messages: List[Dict[str, str]]) -> str:
    base_url = cfg.get("base_url") or ""
    model = cfg.get("model") or ""
    if not base_url or not model:
        raise RuntimeError("LLM base_url/model is required for this operation.")

    client = _get_openai_client(cfg)
    is_moonshot_kimi_k2 = _is_moonshot_base_url(base_url) and _is_kimi_k2_family_model(model)
    request_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if not is_moonshot_kimi_k2:
        request_kwargs["temperature"] = cfg.get("temperature", 0.2)
    extra_body: Dict[str, Any] = {}
    if is_moonshot_kimi_k2:
        if cfg.get("enable_thinking") is True:
            extra_body["thinking"] = {"type": "enabled"}
        elif cfg.get("enable_thinking") is False:
            extra_body["thinking"] = {"type": "disabled"}
    elif cfg.get("enable_thinking") is True:
        extra_body["enable_thinking"] = True
    elif cfg.get("enable_thinking") is False:
        extra_body["enable_thinking"] = False
    if extra_body:
        request_kwargs["extra_body"] = extra_body
    max_tokens = cfg.get("max_tokens")
    if max_tokens is not None:
        request_kwargs["max_tokens"] = int(max_tokens)

    attempts = max(1, int(cfg.get("request_retries", _DEFAULT_REQUEST_RETRIES) or 1))
    backoff_seconds = max(
        0.0,
        float(cfg.get("retry_backoff_seconds", _DEFAULT_RETRY_BACKOFF_SECONDS) or 0.0),
    )
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        logging.info(
            "LLM request start model=%s attempt=%s/%s message_count=%d",
            model,
            attempt,
            attempts,
            len(messages),
        )
        try:
            response = client.chat.completions.create(
                timeout=cfg.get("timeout", 60),
                **request_kwargs,
            )
            content = _extract_response_text(response)
            logging.info(
                "LLM request success model=%s attempt=%s/%s",
                model,
                attempt,
                attempts,
            )
            return content
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                logging.error(
                    "LLM request failed model=%s attempt=%s/%s error=%s",
                    model,
                    attempt,
                    attempts,
                    exc,
                )
                raise
            delay = backoff_seconds * (2 ** (attempt - 1))
            logging.warning(
                "LLM request failed model=%s attempt=%s/%s retry_in=%.1fs error=%s",
                model,
                attempt,
                attempts,
                delay,
                exc,
            )
            if delay > 0:
                time.sleep(delay)

    if last_error is not None:
        raise last_error
    raise RuntimeError("LLM request failed without an error.")


def _extract_response_text(response: Any) -> str:
    try:
        if response is None:
            raise RuntimeError("LLM request returned no data.")
        content = response.choices[0].message.content
    except Exception as exc:
        raise RuntimeError(f"Unexpected LLM response: {response}") from exc

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Empty LLM response.")
    return content


def extract_json(text: str) -> Dict[str, Any]:
    if not text:
        raise RuntimeError("Empty LLM response.")
    cleaned = _strip_code_fence(text)
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()

    candidates: List[str] = []
    for candidate in (
        cleaned,
        _extract_json_object(cleaned),
        _sanitize_json_like(cleaned),
    ):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    extracted = _extract_json_object(cleaned)
    if extracted:
        sanitized_extracted = _sanitize_json_like(extracted)
        if sanitized_extracted and sanitized_extracted not in candidates:
            candidates.append(sanitized_extracted)

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if not isinstance(payload, dict):
            raise RuntimeError("LLM output must be a JSON object.")
        return payload

    if not candidates:
        raise RuntimeError("LLM response does not contain JSON.")
    preview = cleaned[:400].replace("\n", "\\n")
    raise RuntimeError(f"Failed to parse LLM JSON payload: {preview}") from last_error


def _strip_code_fence(text: str) -> str:
    value = (text or "").strip()
    if "```" not in value:
        return value
    parts = value.split("```")
    if len(parts) >= 3:
        return parts[1].strip()
    return value


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        return ""
    return text[start : end + 1].strip()


def _sanitize_json_like(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return value
    return _TRAILING_COMMA_RE.sub("", value)
