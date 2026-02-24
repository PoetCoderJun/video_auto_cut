from __future__ import annotations

import csv
import io
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_settings


@dataclass(frozen=True)
class SheetCode:
    code: str
    credits: int
    max_uses: int | None
    expires_at: str | None
    status: str
    source: str | None


_CACHE_LOCK = threading.Lock()
_CACHE_EXPIRES_AT = 0.0
_CACHE_BY_CODE: dict[str, SheetCode] = {}


def get_sheet_code(code: str) -> SheetCode | None:
    normalized = (code or "").strip().upper()
    if not normalized:
        return None
    mapping = _load_codes_with_cache()
    return mapping.get(normalized)


def _load_codes_with_cache() -> dict[str, SheetCode]:
    settings = get_settings()
    source = (settings.coupon_code_sheet_csv_url or "").strip()
    if not source:
        raise RuntimeError("coupon code csv source is not configured")

    now = time.time()
    with _CACHE_LOCK:
        global _CACHE_EXPIRES_AT
        if now < _CACHE_EXPIRES_AT and _CACHE_BY_CODE:
            return dict(_CACHE_BY_CODE)
        mapping = _fetch_codes_from_csv(source)
        _CACHE_BY_CODE.clear()
        _CACHE_BY_CODE.update(mapping)
        ttl = max(5, int(settings.coupon_code_sheet_cache_seconds))
        _CACHE_EXPIRES_AT = now + ttl
        return dict(_CACHE_BY_CODE)


def _fetch_codes_from_csv(source: str) -> dict[str, SheetCode]:
    source = source.strip()
    if source.startswith(("http://", "https://", "file://")):
        req = urllib.request.Request(source, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                raw = resp.read().decode("utf-8-sig")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"failed to fetch coupon csv: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"failed to fetch coupon csv: {exc}") from exc
    else:
        path = Path(source).expanduser().resolve()
        try:
            raw = path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            raise RuntimeError(f"failed to read coupon csv from {path}: {exc}") from exc

    reader = csv.DictReader(io.StringIO(raw))
    result: dict[str, SheetCode] = {}
    for row in reader:
        if not isinstance(row, dict):
            continue
        item = _parse_row(row)
        if item is None:
            continue
        result[item.code] = item
    return result


def _parse_row(row: dict[str, Any]) -> SheetCode | None:
    code = str(_pick(row, "code", "coupon_code", "邀请码", "兑换码") or "").strip().upper()
    if not code:
        return None

    credits_text = str(_pick(row, "credits", "额度", "次数") or "").strip()
    try:
        credits = int(credits_text)
    except Exception:
        credits = 0
    if credits <= 0:
        return None

    max_uses_text = str(_pick(row, "max_uses", "max_redemptions", "最大使用次数") or "").strip()
    if max_uses_text:
        try:
            parsed = int(max_uses_text)
            max_uses = parsed if parsed > 0 else None
        except Exception:
            max_uses = None
    else:
        max_uses = None

    expires_at = str(_pick(row, "expires_at", "过期时间") or "").strip() or None
    status = str(_pick(row, "status", "状态") or "ACTIVE").strip().upper() or "ACTIVE"
    source = str(_pick(row, "source", "渠道", "来源") or "").strip() or None
    return SheetCode(
        code=code,
        credits=credits,
        max_uses=max_uses,
        expires_at=expires_at,
        status=status,
        source=source,
    )


def _pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row.get(key)
    return None
