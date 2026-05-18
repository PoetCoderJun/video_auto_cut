from __future__ import annotations

from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

def auto_load_dotenv(candidates: Iterable[Path], *, override: bool = False) -> Path | None:
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if not path.is_file():
            continue
        load_dotenv(path, override=override)
        return path
    return None
