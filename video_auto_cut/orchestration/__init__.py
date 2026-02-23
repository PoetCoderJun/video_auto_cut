from __future__ import annotations


def run_full_pipeline() -> None:
    from .full_pipeline import main

    main()

__all__ = ["run_full_pipeline"]
