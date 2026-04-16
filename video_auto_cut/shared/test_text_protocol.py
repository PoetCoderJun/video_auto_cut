from __future__ import annotations

import re

TIMED_LINE_RE = re.compile(
    r"^【(?P<start>\d{2}:\d{2}:\d{2}\.\d{3})-(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})】(?P<remove><remove>)?(?P<text>.*)$"
)
CHAPTER_LINE_RE = re.compile(r"^【(?P<start>\d+)(?:-(?P<end>\d+))?】(?P<title>.+)$")


def format_time(seconds: float) -> str:
    total_ms = int(round(float(seconds) * 1000.0))
    hours = total_ms // 3_600_000
    total_ms %= 3_600_000
    minutes = total_ms // 60_000
    total_ms %= 60_000
    secs = total_ms // 1000
    millis = total_ms % 1000
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def parse_time(value: str) -> float:
    parts = value.strip().split(":")
    if len(parts) != 3:
        raise RuntimeError(f"invalid test time: {value}")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds, millis = parts[2].split(".")
    return hours * 3600 + minutes * 60 + int(seconds) + int(millis) / 1000.0


def render_time_range_tag(start: float, end: float) -> str:
    return f"【{format_time(start)}-{format_time(end)}】"


def render_test_line_text(*, start: float, end: float, text: str, remove: bool) -> str:
    body = f"<remove>{text}" if remove else text
    return f"{render_time_range_tag(start, end)}{body}".rstrip()


def parse_timed_lines(text: str) -> list[tuple[float, float, bool, str]]:
    rows: list[tuple[float, float, bool, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = TIMED_LINE_RE.match(line)
        if not match:
            raise RuntimeError(f"Invalid timed line format: {line}")
        rows.append(
            (
                parse_time(match.group("start")),
                parse_time(match.group("end")),
                bool(match.group("remove")),
                (match.group("text") or "").strip(),
            )
        )
    return rows


def parse_chapter_line(line: str) -> tuple[int, int, str]:
    match = CHAPTER_LINE_RE.match(line.strip())
    if not match:
        raise RuntimeError(f"invalid chapter text line: {line.strip()}")
    start = int(match.group("start"))
    end = int(match.group("end") or start)
    title = (match.group("title") or "").strip()
    return start, end, title


def render_chapter_line(*, block_range: str, title: str) -> str:
    return f"【{str(block_range or '').strip()}】{str(title or '').strip()}".rstrip()
