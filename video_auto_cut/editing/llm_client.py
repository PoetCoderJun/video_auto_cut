from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

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
_DEFAULT_REPAIR_RETRIES = 2
_DEFAULT_RETRY_BACKOFF_SECONDS = 1.0

JsonValidator = Callable[[Dict[str, Any]], Dict[str, Any]]


def _env_flag(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


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
    fallback_key = os.environ.get("DASHSCOPE_API_KEY") or ""
    cfg = {
        "base_url": (base_url or os.environ.get("LLM_BASE_URL") or "").strip(),
        "model": (model or os.environ.get("LLM_MODEL") or "").strip(),
        "api_key": (api_key or os.environ.get("LLM_API_KEY") or fallback_key).strip(),
        "timeout": int(timeout),
        "temperature": float(temperature),
        "max_tokens": int(max_tokens) if max_tokens is not None else None,
        "request_retries": max(
            1,
            int(os.environ.get("LLM_REQUEST_RETRIES", str(_DEFAULT_REQUEST_RETRIES))),
        ),
        "repair_retries": max(
            0,
            int(os.environ.get("LLM_REPAIR_RETRIES", str(_DEFAULT_REPAIR_RETRIES))),
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
    request_kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": cfg.get("temperature", 0.2),
    }
    if cfg.get("enable_thinking"):
        request_kwargs["extra_body"] = {"enable_thinking": True}
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


def request_json(
    cfg: Dict[str, Any],
    messages: List[Dict[str, str]],
    *,
    validate: JsonValidator | None = None,
    repair_retries: int | None = None,
    repair_instructions: str | None = None,
    chat_completion_fn: Callable[[Dict[str, Any], List[Dict[str, str]]], str] | None = None,
    initial_response: str | None = None,
) -> Dict[str, Any]:
    chat_fn = chat_completion_fn or chat_completion
    max_repairs = (
        int(cfg.get("repair_retries", _DEFAULT_REPAIR_RETRIES))
        if repair_retries is None
        else int(repair_retries)
    )
    max_repairs = max(0, max_repairs)
    current_response = initial_response if initial_response is not None else chat_fn(cfg, messages)
    last_error: Exception | None = None

    for attempt in range(0, max_repairs + 1):
        try:
            payload = extract_json(current_response)
            if validate is not None:
                payload = validate(payload)
            if not isinstance(payload, dict):
                raise RuntimeError("LLM output must be a JSON object.")
            return payload
        except Exception as exc:
            last_error = exc
            if attempt >= max_repairs:
                raise
            logging.warning(
                "LLM output repair start model=%s attempt=%s/%s error=%s",
                cfg.get("model") or "",
                attempt + 1,
                max_repairs,
                exc,
            )
            current_response = chat_fn(
                cfg,
                _build_json_repair_messages(
                    messages,
                    raw_response=current_response,
                    error=str(exc),
                    repair_instructions=repair_instructions,
                ),
            )

    if last_error is not None:
        raise last_error
    raise RuntimeError("LLM JSON request failed without an error.")


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


def _build_json_repair_messages(
    messages: List[Dict[str, str]],
    *,
    raw_response: str,
    error: str,
    repair_instructions: str | None,
) -> List[Dict[str, str]]:
    system = (
        "你是 JSON 修复代理。"
        "你会拿到原始任务说明、上一次模型输出和当前错误。"
        "请在尽量保留原意的前提下，把输出修复成一个合法的 JSON 对象。"
        "只输出 JSON，不要解释，不要 Markdown，不要额外前后缀。"
    )
    if repair_instructions:
        system += f" 额外要求：{repair_instructions.strip()}"

    formatted_messages = []
    for item in messages:
        role = str(item.get("role") or "user").strip() or "user"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        formatted_messages.append(f"[{role}]\n{content}")

    user = (
        "原始任务说明：\n"
        f"{chr(10).join(formatted_messages) or '[empty]'}\n\n"
        "上一次模型输出：\n"
        f"{raw_response.strip() or '[empty]'}\n\n"
        "当前错误：\n"
        f"{error.strip() or '[unknown error]'}\n\n"
        "请直接返回修复后的 JSON 对象。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
