import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from openai import OpenAI
except ModuleNotFoundError as exc:
    OpenAI = None  # type: ignore[assignment]
    _OPENAI_IMPORT_ERROR: ModuleNotFoundError | None = exc
else:
    _OPENAI_IMPORT_ERROR = None


_ENV_LOADED = False
_OPENAI_CLIENTS_BY_CFG: Dict[Tuple[str, str], Any] = {}


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _env_flag(value: Optional[str]) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


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
        Path(__file__).resolve().parents[1] / ".env",
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
    enable_thinking: Optional[bool] = None,
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
            "Python package 'openai' is required for Step1 auto-edit. "
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

    logging.info(
        "LLM request start model=%s attempt=1/1 message_count=%d",
        model,
        len(messages),
    )
    try:
        response = client.chat.completions.create(
            timeout=cfg.get("timeout", 60),
            **request_kwargs,
        )
        logging.info("LLM request success model=%s attempt=1/1", model)
    except Exception as exc:
        logging.error(f"LLM request failed: {exc}")
        raise

    try:
        if response is None:
            raise RuntimeError("LLM request returned no data.")
        return response.choices[0].message.content
    except Exception as exc:
        raise RuntimeError(f"Unexpected LLM response: {response}") from exc


def extract_json(text: str) -> Dict[str, Any]:
    if not text:
        raise RuntimeError("Empty LLM response.")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise RuntimeError("LLM response does not contain JSON.")
    return json.loads(match.group(0))
