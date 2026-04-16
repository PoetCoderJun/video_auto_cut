from __future__ import annotations

from typing import Any, TypedDict


class TestLine(TypedDict):
    line_id: int
    start: float
    end: float
    original_text: str
    optimized_text: str
    ai_suggest_remove: bool
    user_final_remove: bool


REQUIRED_TEST_LINE_FIELDS = (
    "line_id",
    "start",
    "end",
    "original_text",
    "optimized_text",
    "ai_suggest_remove",
    "user_final_remove",
)


def build_test_line(
    *,
    line_id: int,
    start: float,
    end: float,
    original_text: str,
    optimized_text: str | None = None,
    ai_suggest_remove: bool = False,
    user_final_remove: bool | None = None,
) -> TestLine:
    original = str(original_text or "").strip()
    optimized = str(optimized_text or original).strip() or original
    ai_remove = bool(ai_suggest_remove)
    final_remove = ai_remove if user_final_remove is None else bool(user_final_remove)
    return {
        "line_id": int(line_id),
        "start": float(start),
        "end": float(end),
        "original_text": original,
        "optimized_text": optimized,
        "ai_suggest_remove": ai_remove,
        "user_final_remove": final_remove,
    }


def normalize_test_line(line: dict[str, Any]) -> TestLine:
    for field in REQUIRED_TEST_LINE_FIELDS:
        if field not in line:
            raise RuntimeError(f"test line missing field: {field}")
    return build_test_line(
        line_id=int(line["line_id"]),
        start=float(line["start"]),
        end=float(line["end"]),
        original_text=str(line.get("original_text") or "").strip(),
        optimized_text=str(line.get("optimized_text") or "").strip(),
        ai_suggest_remove=bool(line.get("ai_suggest_remove", False)),
        user_final_remove=bool(line.get("user_final_remove", False)),
    )


def normalize_test_lines(lines: list[dict[str, Any]]) -> list[TestLine]:
    seen = [int(item.get("line_id")) for item in lines]
    if len(seen) != len(set(seen)):
        raise RuntimeError("Duplicate line_id detected in PI output.")
    return sorted((normalize_test_line(item) for item in lines), key=lambda item: int(item["line_id"]))
