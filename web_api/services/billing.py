from __future__ import annotations

from ..db_repository import (
    consume_guest_session_free_use,
    consume_job_export_credit,
    consume_job_test_credit,
    get_credit_balance,
    get_guest_session,
    has_job_credit_consumed,
)
from ..job_file_repository import get_job_owner_user_id

LIMITED_TIME_FREE_ENABLED = False


class BillingServiceError(Exception):
    """Base class for billing-domain service failures."""


class InsufficientCreditsError(BillingServiceError):
    pass


class JobOwnerNotFoundError(BillingServiceError):
    pass


def _guest_id_from_actor_id(actor_id: str | None) -> str | None:
    normalized = str(actor_id or "").strip()
    if not normalized.startswith("guest:"):
        return None
    guest_id = normalized.split(":", 1)[1].strip()
    return guest_id or None


def is_limited_time_free_enabled() -> bool:
    return LIMITED_TIME_FREE_ENABLED


def has_available_credits(user_id: str) -> bool:
    guest_id = _guest_id_from_actor_id(user_id)
    if guest_id:
        session = get_guest_session(guest_id)
        if not session:
            return False
        remaining = int(session.get("free_uses_remaining") or 0)
        status = str(session.get("status") or "ACTIVE").upper()
        return remaining >= 1 and status == "ACTIVE"
    return get_credit_balance(user_id) >= 1


def has_available_credits_for_job(user_id: str, job_id: str) -> bool:
    if has_job_credit_consumed(job_id):
        return True
    return has_available_credits(user_id)


def ensure_credit_available(user_id: str) -> None:
    if not has_available_credits(user_id):
        raise InsufficientCreditsError


def ensure_credit_available_for_job(user_id: str, job_id: str) -> None:
    if not has_available_credits_for_job(user_id, job_id):
        raise InsufficientCreditsError


def consume_test_credit(job_id: str) -> dict[str, object]:
    owner_user_id = get_job_owner_user_id(job_id)
    if not owner_user_id:
        raise JobOwnerNotFoundError

    guest_id = _guest_id_from_actor_id(owner_user_id)
    try:
        if guest_id:
            result = consume_guest_session_free_use(guest_id, job_id)
        else:
            result = consume_job_test_credit(owner_user_id, job_id)
    except LookupError as exc:
        if str(exc) == "INSUFFICIENT_CREDITS":
            raise InsufficientCreditsError from exc
        raise

    return {
        "consumed": bool(result["consumed"]),
        "balance": int(result["balance"]),
    }


def consume_export_credit(job_id: str) -> dict[str, object]:
    owner_user_id = get_job_owner_user_id(job_id)
    if not owner_user_id:
        raise JobOwnerNotFoundError

    guest_id = _guest_id_from_actor_id(owner_user_id)
    try:
        if guest_id:
            result = consume_guest_session_free_use(guest_id, job_id)
        else:
            result = consume_job_export_credit(owner_user_id, job_id)
    except LookupError as exc:
        if str(exc) == "INSUFFICIENT_CREDITS":
            raise InsufficientCreditsError from exc
        raise

    return {
        "consumed": bool(result["consumed"]),
        "balance": int(result["balance"]),
    }
