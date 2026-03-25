#!/usr/bin/env python3

import argparse
import json
import sys
import time
from typing import Any

from playwright.sync_api import sync_playwright

DEFAULT_SAMPLES = [
    "small_h264_aac_mp4.mp4",
    "small_hevc_aac_mp4.mp4",
    "small_hevc_aac_mov.mov",
    "small_vp9_opus_webm.webm",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the browser import/export format matrix against the dev-format-matrix page."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:3000",
        help="Base URL for the Next.js dev server.",
    )
    parser.add_argument(
        "--sample",
        action="append",
        dest="samples",
        help="Run only the given sample. Can be passed multiple times.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=120,
        help="Per-sample timeout while waiting for the page to finish.",
    )
    parser.add_argument(
        "--chrome-path",
        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        help="Chrome executable path used by Playwright.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    samples = args.samples or DEFAULT_SAMPLES
    probe_base = f"{args.base_url.rstrip('/')}/dev-format-matrix?sample="
    all_results: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=args.chrome_path,
            headless=True,
            args=["--disable-gpu"],
        )
        try:
            for sample in samples:
                page = browser.new_page()
                try:
                    page.goto(f"{probe_base}{sample}", wait_until="domcontentloaded", timeout=120_000)
                    started_at = time.time()
                    final_status = ""
                    while time.time() - started_at < args.timeout_seconds:
                        page.wait_for_timeout(5_000)
                        final_status = page.locator("#status").inner_text().strip()
                        print(
                            f"{sample}: t={int(time.time() - started_at):>3}s status={final_status}",
                            file=sys.stderr,
                            flush=True,
                        )
                        if final_status == "done" or final_status.startswith("error:"):
                            break

                    result_text = page.locator("#results").inner_text().strip()
                    logs_text = page.locator("#logs").inner_text().strip()
                    try:
                        parsed = json.loads(result_text) if result_text else []
                    except json.JSONDecodeError:
                        parsed = []

                    if parsed:
                        all_results.extend(parsed)
                    else:
                        all_results.append(
                            {
                                "sample": sample,
                                "status": final_status,
                                "logs": logs_text,
                                "resultsText": result_text,
                            }
                        )
                finally:
                    page.close()
        finally:
            browser.close()

    json.dump(all_results, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
