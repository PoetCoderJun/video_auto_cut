from __future__ import annotations

from ..errors import coupon_code_exhausted, coupon_code_expired, coupon_code_invalid
from ..repository import get_credit_balance, get_recent_credit_ledger, get_user, redeem_coupon_code


def get_user_profile(user_id: str) -> dict[str, object]:
    user = get_user(user_id)
    if not user:
        return {
            "user_id": user_id,
            "email": None,
            "status": "PENDING_INVITE",
            "invite_activated_at": None,
            "credits": {"balance": 0, "recent_ledger": []},
        }
    return {
        "user_id": str(user["user_id"]),
        "email": user.get("email"),
        "status": user.get("status") or "PENDING_INVITE",
        "invite_activated_at": user.get("invite_activated_at"),
        "credits": {
            "balance": get_credit_balance(user_id),
            "recent_ledger": get_recent_credit_ledger(user_id, limit=20),
        },
    }


def redeem_coupon_for_user(user_id: str, code: str) -> dict[str, object]:
    try:
        result = redeem_coupon_code(user_id, code)
    except LookupError as exc:
        flag = str(exc)
        if flag == "COUPON_CODE_EXPIRED":
            raise coupon_code_expired("兑换码已过期，请联系管理员获取新码") from exc
        if flag == "COUPON_CODE_EXHAUSTED":
            raise coupon_code_exhausted("兑换码已用完，请联系管理员获取新码") from exc
        raise coupon_code_invalid("兑换码无效，请检查后重试") from exc
    except ValueError as exc:
        raise coupon_code_invalid("兑换码不能为空") from exc
    except RuntimeError as exc:
        raise coupon_code_invalid("兑换码服务暂不可用，请稍后再试") from exc

    return {
        "already_activated": bool(result["already_activated"]),
        "coupon_redeemed": bool(result["coupon_redeemed"]),
        "granted_credits": int(result["granted_credits"]),
        "balance": int(result["balance"]),
    }
