from __future__ import annotations

from ..db_repository import consume_job_export_credit, get_credit_balance
from ..job_file_repository import get_job_owner_user_id


class BillingServiceError(Exception):
    """Base class for billing-domain service failures."""


class InsufficientCreditsError(BillingServiceError):
    pass


class JobOwnerNotFoundError(BillingServiceError):
    pass


def has_available_credits(user_id: str) -> bool:
    return get_credit_balance(user_id) >= 1


def ensure_credit_available(user_id: str) -> None:
    if not has_available_credits(user_id):
        raise InsufficientCreditsError


def consume_export_credit(job_id: str) -> dict[str, object]:
    owner_user_id = get_job_owner_user_id(job_id)
    if not owner_user_id:
        raise JobOwnerNotFoundError

    try:
        result = consume_job_export_credit(owner_user_id, job_id)
    except LookupError as exc:
        if str(exc) == "INSUFFICIENT_CREDITS":
            raise InsufficientCreditsError from exc
        raise

    return {
        "consumed": bool(result["consumed"]),
        "balance": int(result["balance"]),
    }
