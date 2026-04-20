#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from video_auto_cut.rendering.subtitle_render_contract import (
    build_subtitle_render_v1_contract,
    build_subtitle_style_llm_config,
    load_timed_captions_from_text,
    normalize_subtitle_theme,
    write_subtitle_render_v1_contract,
)
from web_api.config import get_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert timed subtitle text into subtitle-render.v1 JSON for Remotion.",
    )
    parser.add_argument("--input", required=True, help="Timed subtitle text file, one row per caption.")
    parser.add_argument("--output", required=True, help="Output subtitle-render.v1 JSON path.")
    parser.add_argument("--theme", default="white", choices=("white", "black"), help="Base subtitle text color.")
    parser.add_argument("--output-name", default="subtitle-render_export.mp4", help="Suggested exported video filename.")
    parser.add_argument("--topics-json", help="Optional JSON file containing [{title,start,end}] topic items.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    captions = load_timed_captions_from_text(input_path)
    segments = [{"start": float(item["start"]), "end": float(item["end"])} for item in captions]

    topics = []
    if args.topics_json:
        topics = json.loads(Path(args.topics_json).read_text(encoding="utf-8"))

    settings = get_settings()
    llm_config = build_subtitle_style_llm_config(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        timeout=int(settings.llm_timeout),
        max_tokens=settings.llm_max_tokens,
    )
    contract = build_subtitle_render_v1_contract(
        captions=captions,
        segments=segments,
        topics=topics,
        output_name=args.output_name,
        subtitle_theme=normalize_subtitle_theme(args.theme),
        llm_config=llm_config,
    )
    write_subtitle_render_v1_contract(contract, output_path)
    print(str(output_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
