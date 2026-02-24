from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.algorithms import RSAAlgorithm

from ..config import get_settings
from ..errors import unauthorized
from ..repository import ensure_user

_AUTH_BEARER = HTTPBearer(auto_error=False)
_JWKS_LOCK = threading.Lock()
_JWKS_CACHE_BY_KID: dict[str, dict[str, Any]] = {}
_JWKS_CACHE_EXPIRES_AT = 0.0


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    email: str | None
    account: str | None


def require_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_AUTH_BEARER),
) -> CurrentUser:
    settings = get_settings()
    if not settings.auth_enabled:
        user_id = "dev_local_user"
        ensure_user(user_id, "dev_local_user@example.local")
        return CurrentUser(user_id=user_id, email="dev_local_user@example.local", account="dev_local_user")

    token = credentials.credentials.strip() if credentials else ""
    if not token:
        raise unauthorized("请先登录后再继续")

    claims = _decode_auth_token(token)
    user_id = str(claims.get("sub") or "").strip()
    if not user_id:
        raise unauthorized("登录状态无效，请重新登录")

    email = _extract_email(claims)
    ensure_user(user_id, email)
    account = _extract_account(claims)
    return CurrentUser(user_id=user_id, email=email, account=account)


def _decode_auth_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.auth_jwks_url:
        raise unauthorized("服务端登录配置缺失（WEB_AUTH_JWKS_URL）")

    try:
        header = jwt.get_unverified_header(token)
    except Exception as exc:
        raise unauthorized(f"登录令牌无效：{exc}") from exc

    kid = str(header.get("kid") or "").strip()
    if not kid:
        raise unauthorized("登录令牌无效：缺少 kid")

    jwk = _get_jwk_by_kid(settings.auth_jwks_url, kid)
    if not jwk:
        raise unauthorized("登录令牌无效：未找到签名密钥")

    try:
        public_key = RSAAlgorithm.from_jwk(json.dumps(jwk))
    except Exception as exc:
        raise unauthorized(f"登录令牌无效：密钥解析失败（{exc}）") from exc

    decode_kwargs: dict[str, Any] = {
        "algorithms": ["RS256"],
        "leeway": settings.auth_jwt_leeway_seconds,
    }
    if settings.auth_issuer:
        decode_kwargs["issuer"] = settings.auth_issuer
    if settings.auth_audience:
        decode_kwargs["audience"] = settings.auth_audience
    else:
        decode_kwargs["options"] = {"verify_aud": False}

    try:
        payload = jwt.decode(token, public_key, **decode_kwargs)
    except Exception as exc:
        raise unauthorized(f"登录令牌校验失败：{exc}") from exc

    if not isinstance(payload, dict):
        raise unauthorized("登录令牌校验失败：payload 无效")
    return payload


def _extract_email(claims: dict[str, Any]) -> str | None:
    for key in ("email", "email_address", "primary_email_address"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    user = claims.get("user")
    if isinstance(user, dict):
        value = user.get("email")
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _extract_account(claims: dict[str, Any]) -> str | None:
    for key in ("username", "account"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    user = claims.get("user")
    if isinstance(user, dict):
        for key in ("username", "email"):
            value = user.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _get_jwk_by_kid(jwks_url: str, kid: str) -> dict[str, Any] | None:
    now = time.time()
    with _JWKS_LOCK:
        global _JWKS_CACHE_EXPIRES_AT
        if now >= _JWKS_CACHE_EXPIRES_AT:
            _JWKS_CACHE_BY_KID.clear()
            _JWKS_CACHE_BY_KID.update(_fetch_jwks(jwks_url))
            _JWKS_CACHE_EXPIRES_AT = now + 300
        return _JWKS_CACHE_BY_KID.get(kid)


def _fetch_jwks(jwks_url: str) -> dict[str, dict[str, Any]]:
    req = urllib.request.Request(jwks_url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise unauthorized(f"无法连接登录服务（JWKS）：{exc}") from exc
    except Exception as exc:
        raise unauthorized(f"读取登录服务密钥失败：{exc}") from exc

    keys = payload.get("keys")
    if not isinstance(keys, list):
        raise unauthorized("登录服务密钥格式错误")

    result: dict[str, dict[str, Any]] = {}
    for item in keys:
        if not isinstance(item, dict):
            continue
        key_id = str(item.get("kid") or "").strip()
        if not key_id:
            continue
        result[key_id] = item
    return result
