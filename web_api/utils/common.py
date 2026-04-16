from __future__ import annotations

import uuid


def new_request_id(prefix: str = "req") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"
