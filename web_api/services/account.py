from __future__ import annotations

from typing import Any

from ..config import get_settings
from ..db_repository import (
    claim_public_coupon_code,
    ensure_user,
    get_credit_balance,
    get_recent_credit_ledger,
    get_user,
    preview_coupon_code,
    redeem_coupon_code,
)


class AccountServiceError(Exception):
    """Base class for account-domain service failures."""


class UserActivationRequiredError(AccountServiceError):
    pass


class CouponCodeInvalidError(AccountServiceError):
    pass


class CouponCodeExpiredError(AccountServiceError):
    pass


class CouponCodeExhaustedError(AccountServiceError):
    pass


class InviteClaimFailedError(AccountServiceError):
    pass


class InviteClaimExhaustedError(AccountServiceError):
    pass


class ClientIpUnavailableError(AccountServiceError):
    pass


def ensure_active_user(user_id: str, email: str | None = None) -> None:
    ensure_user(user_id, email)
    user = get_user(user_id)
    status = str((user or {}).get("status") or "PENDING_COUPON").upper()
    if status != "ACTIVE":
        raise UserActivationRequiredError


def get_user_profile(user_id: str, email: str | None = None) -> dict[str, object]:
    ensure_user(user_id, email)
    user = get_user(user_id)
    if not user:
        return {
            "user_id": user_id,
            "email": None,
            "status": "PENDING_COUPON",
            "activated_at": None,
            "credits": {"balance": 0, "recent_ledger": []},
        }
    return {
        "user_id": str(user["user_id"]),
        "email": user.get("email"),
        "status": user.get("status") or "PENDING_COUPON",
        "activated_at": user.get("activated_at"),
        "credits": {
            "balance": get_credit_balance(user_id),
            "recent_ledger": get_recent_credit_ledger(user_id, limit=20),
        },
    }


def redeem_coupon_for_user(user_id: str, code: str, email: str | None = None) -> dict[str, object]:
    ensure_user(user_id, email)
    try:
        result = redeem_coupon_code(user_id, code)
    except LookupError as exc:
        raise _map_coupon_lookup_error(str(exc)) from exc
    except ValueError as exc:
        raise CouponCodeInvalidError from exc
    except RuntimeError as exc:
        raise CouponCodeInvalidError from exc

    return {
        "already_activated": bool(result["already_activated"]),
        "coupon_redeemed": bool(result["coupon_redeemed"]),
        "granted_credits": int(result["granted_credits"]),
        "balance": int(result["balance"]),
    }


def check_coupon_for_signup(code: str) -> dict[str, object]:
    try:
        result = preview_coupon_code(code)
    except LookupError as exc:
        raise _map_coupon_lookup_error(str(exc)) from exc
    except ValueError as exc:
        raise CouponCodeInvalidError from exc
    except RuntimeError as exc:
        raise CouponCodeInvalidError from exc

    return {
        "valid": True,
        "code": str(result["code"]),
        "credits": int(result["credits"]),
    }


def claim_public_invite_for_ip(ip_address: str) -> dict[str, object]:
    normalized_ip = str(ip_address or "").strip()
    if not normalized_ip:
        raise ClientIpUnavailableError

    settings = get_settings()
    try:
        result = claim_public_coupon_code(
            normalized_ip,
            credits=settings.public_invite_credits,
            source="PUBLIC_WEB_INVITE",
        )
    except LookupError as exc:
        if str(exc) == "PUBLIC_INVITE_EXHAUSTED":
            raise InviteClaimExhaustedError from exc
        raise InviteClaimFailedError from exc
    except ValueError as exc:
        raise ClientIpUnavailableError from exc
    except RuntimeError as exc:
        raise InviteClaimFailedError from exc

    return {
        "code": str(result["code"]),
        "credits": int(result["credits"]),
        "already_claimed": bool(result["already_claimed"]),
    }


def _map_coupon_lookup_error(flag: str) -> AccountServiceError:
    if flag == "COUPON_CODE_EXPIRED":
        return CouponCodeExpiredError()
    if flag == "COUPON_CODE_EXHAUSTED":
        return CouponCodeExhaustedError()
    return CouponCodeInvalidError()
