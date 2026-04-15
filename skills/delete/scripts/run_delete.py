from __future__ import annotations

import argparse
from pathlib import Path

from video_auto_cut.pi_agent_runner import main as pi_runner_main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Run delete skill via canonical PI seam.')
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--llm-base-url', default=None)
    parser.add_argument('--llm-model', default=None)
    parser.add_argument('--llm-api-key', default=None)
    parser.add_argument('--llm-timeout', type=int, default=300)
    parser.add_argument('--llm-max-tokens', type=int, default=None)
    parser.add_argument('--max-lines', type=int, default=400)
    args = parser.parse_args(argv)
    cli = [
        '--input', str(Path(args.input)),
        '--task', 'delete',
        '--output', str(Path(args.output)),
        '--llm-timeout', str(args.llm_timeout),
        '--max-lines', str(args.max_lines),
    ]
    if args.llm_base_url is not None:
        cli.extend(['--llm-base-url', str(args.llm_base_url)])
    if args.llm_model is not None:
        cli.extend(['--llm-model', str(args.llm_model)])
    if args.llm_api_key is not None:
        cli.extend(['--llm-api-key', str(args.llm_api_key)])
    if args.llm_max_tokens is not None:
        cli.extend(['--llm-max-tokens', str(args.llm_max_tokens)])
    return pi_runner_main(cli)


if __name__ == '__main__':
    raise SystemExit(main())
