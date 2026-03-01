import json
import logging
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


_ENV_LOADED = False


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _load_env_file(path: Path):
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = _strip_quotes(value.strip())
        if not key or key in os.environ:
            continue
        os.environ[key] = value


def _auto_load_dotenv():
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    for candidate in candidates:
        if candidate.exists():
            _load_env_file(candidate)
            break
    _ENV_LOADED = True


def build_llm_config(
    base_url: Optional[str],
    model: Optional[str],
    api_key: Optional[str] = None,
    timeout: int = 60,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    _auto_load_dotenv()
    fallback_key = os.environ.get("DASHSCOPE_API_KEY") or ""
    cfg = {
        "base_url": (base_url or os.environ.get("LLM_BASE_URL") or "").strip(),
        "model": (model or os.environ.get("LLM_MODEL") or "").strip(),
        "api_key": (api_key or os.environ.get("LLM_API_KEY") or fallback_key).strip(),
        "timeout": int(timeout),
        "temperature": float(temperature),
        "max_tokens": int(max_tokens) if max_tokens is not None else None,
        "request_retries": max(1, int(os.environ.get("LLM_REQUEST_RETRIES", "3"))),
    }
    return cfg


def _resolve_chat_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    return base + "/chat/completions"


def _post_json(url: str, payload: Dict[str, Any], api_key: str, timeout: int) -> Dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _is_retryable_llm_error(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        code = int(getattr(exc, "code", 0) or 0)
        return code == 429 or 500 <= code < 600
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (ssl.SSLError, TimeoutError, OSError)):
            return True
        reason_text = str(reason or "").lower()
        for token in (
            "timed out",
            "temporary failure",
            "connection reset",
            "connection aborted",
            "unexpected eof",
            "eof occurred",
            "tls",
            "ssl",
        ):
            if token in reason_text:
                return True
        return False
    return isinstance(
        exc,
        (TimeoutError, ssl.SSLError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError),
    )


def chat_completion(cfg: Dict[str, Any], messages: List[Dict[str, str]]) -> str:
    base_url = cfg.get("base_url") or ""
    model = cfg.get("model") or ""
    if not base_url or not model:
        raise RuntimeError("LLM base_url/model is required for this operation.")

    url = _resolve_chat_url(base_url)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": cfg.get("temperature", 0.2),
    }
    max_tokens = cfg.get("max_tokens")
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)

    retries = max(1, int(cfg.get("request_retries", 3)))
    data: Dict[str, Any] | None = None
    for attempt in range(1, retries + 1):
        try:
            data = _post_json(url, payload, cfg.get("api_key", ""), cfg.get("timeout", 60))
            break
        except Exception as exc:
            retryable = _is_retryable_llm_error(exc)
            if retryable and attempt < retries:
                delay = min(8.0, 0.8 * (2 ** (attempt - 1)))
                logging.warning(
                    "LLM request transient failure (attempt %d/%d), retrying in %.1fs: %s",
                    attempt,
                    retries,
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue
            logging.error(f"LLM request failed: {exc}")
            raise

    try:
        if data is None:
            raise RuntimeError("LLM request returned no data.")
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"Unexpected LLM response: {data}") from exc


def extract_json(text: str) -> Dict[str, Any]:
    if not text:
        raise RuntimeError("Empty LLM response.")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise RuntimeError("LLM response does not contain JSON.")
    return json.loads(match.group(0))
