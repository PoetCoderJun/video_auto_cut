from __future__ import annotations

import re
from pathlib import Path


def extract_labeled_path(prompt: str, label: str) -> Path:
    match = re.search(rf"{label}: (.+)", prompt)
    if not match:
        raise AssertionError(f"missing {label} in prompt: {prompt}")
    return Path(match.group(1).strip())
