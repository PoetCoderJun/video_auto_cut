from __future__ import annotations


def parse_decision_and_text(content: str) -> str:
    return "\n".join(line.strip() for line in (content or "").splitlines() if line.strip()).strip()
