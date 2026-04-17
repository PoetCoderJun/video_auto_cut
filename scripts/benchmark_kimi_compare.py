from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from video_auto_cut.editing.llm_client import build_llm_config, chat_completion, request_json
from video_auto_cut.editing.topic_segment import TopicBlock, _build_segmentation_prompt
from video_auto_cut.shared.dotenv import auto_load_dotenv


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    model: str
    api_key: str


@dataclass(frozen=True)
class SampleResult:
    provider: str
    scenario: str
    round_index: int
    elapsed_seconds: float
    success: bool
    detail: dict[str, Any]


def _load_env() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    auto_load_dotenv([repo_root / ".env"])


def _require_env(name: str) -> str:
    value = str(os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _default_model() -> str:
    return str(os.getenv("LLM_MODEL") or "kimi-k2.5").strip() or "kimi-k2.5"


def _build_providers() -> list[Provider]:
    current_base_url = _require_env("LLM_BASE_URL")
    current_model = _default_model()
    current_api_key = (
        str(os.getenv("LLM_API_KEY") or "").strip()
        or str(os.getenv("DASHSCOPE_API_KEY") or "").strip()
        or str(os.getenv("KIMI_API_KEY") or "").strip()
        or str(os.getenv("MOONSHOT_API_KEY") or "").strip()
    )
    if not current_api_key:
        raise RuntimeError("Missing current provider API key: set LLM_API_KEY or DASHSCOPE_API_KEY.")

    kimi_api_key = (
        str(os.getenv("KIMI_API_KEY") or "").strip()
        or str(os.getenv("MOONSHOT_API_KEY") or "").strip()
    )
    if not kimi_api_key:
        raise RuntimeError("Missing KIMI_API_KEY (or MOONSHOT_API_KEY) for official Kimi benchmark.")

    return [
        Provider(
            name="current_env",
            base_url=current_base_url,
            model=current_model,
            api_key=current_api_key,
        ),
        Provider(
            name="kimi_official",
            base_url=str(os.getenv("KIMI_BASE_URL") or "https://api.moonshot.cn/v1").strip(),
            model=str(os.getenv("KIMI_MODEL") or current_model).strip() or current_model,
            api_key=kimi_api_key,
        ),
    ]


def _sample_blocks() -> list[TopicBlock]:
    return [
        TopicBlock(1, [1, 2], 0.0, 6.8, "很多人做短视频一上来先铺背景，观众三秒内就划走了。"),
        TopicBlock(2, [3, 4], 6.8, 13.5, "真正更有效的做法是开头直接把结果亮出来，让人先知道看完能得到什么。"),
        TopicBlock(3, [5, 6], 13.5, 20.2, "第二步再补一两个反常识细节，观众会觉得这个方法有门槛，愿意继续看。"),
        TopicBlock(4, [7, 8], 20.2, 27.8, "等注意力被抓住以后，再用一个真实案例把方法拆开，转化率会比空讲概念高很多。"),
        TopicBlock(5, [9, 10], 27.8, 35.1, "如果你的案例太长，就只保留冲突、动作和结果，其他背景信息尽量删掉。"),
        TopicBlock(6, [11, 12], 35.1, 43.0, "结尾不要重复总结，而是给一个下一步动作，比如评论关键词或者领取模板。"),
    ]


def _build_simple_messages() -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "你是一个简洁的中文短视频策划助手。"},
        {
            "role": "user",
            "content": "请用两句话说明，为什么短视频开头最好先给结果，再补背景。",
        },
    ]


def _build_topic_messages() -> list[dict[str, str]]:
    return _build_segmentation_prompt(
        _sample_blocks(),
        total_segments=12,
        min_topics=3,
        max_topics=4,
        recommended_topics=3,
        title_max_chars=6,
        min_segments_per_topic=2,
    )


def _run_simple_chat(provider: Provider, timeout: int, max_tokens: int | None) -> dict[str, Any]:
    cfg = build_llm_config(
        base_url=provider.base_url,
        model=provider.model,
        api_key=provider.api_key,
        timeout=timeout,
        max_tokens=max_tokens,
        enable_thinking=False,
    )
    content = chat_completion(cfg, _build_simple_messages())
    return {
        "chars": len(content),
        "preview": content[:120],
    }


def _run_topic_json(provider: Provider, timeout: int, max_tokens: int | None) -> dict[str, Any]:
    cfg = build_llm_config(
        base_url=provider.base_url,
        model=provider.model,
        api_key=provider.api_key,
        timeout=timeout,
        max_tokens=max_tokens,
        enable_thinking=False,
    )
    payload = request_json(cfg, _build_topic_messages())
    topics = payload.get("topics")
    titles = []
    if isinstance(topics, list):
        for item in topics[:4]:
            if isinstance(item, dict):
                titles.append(str(item.get("title") or "").strip())
    return {
        "topic_count": len(topics) if isinstance(topics, list) else 0,
        "titles": titles,
    }


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    lower_value = ordered[lower]
    upper_value = ordered[upper]
    return lower_value + (upper_value - lower_value) * (index - lower)


def _summarize(results: list[SampleResult]) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[SampleResult]] = {}
    for result in results:
        grouped.setdefault((result.provider, result.scenario), []).append(result)

    summary: dict[str, Any] = {}
    for key, items in grouped.items():
        provider, scenario = key
        elapsed = [item.elapsed_seconds for item in items if item.success]
        failures = [item.detail for item in items if not item.success]
        summary[f"{provider}:{scenario}"] = {
            "runs": len(items),
            "successes": len(elapsed),
            "failures": len(failures),
            "avg_seconds": round(statistics.mean(elapsed), 3) if elapsed else None,
            "min_seconds": round(min(elapsed), 3) if elapsed else None,
            "max_seconds": round(max(elapsed), 3) if elapsed else None,
            "p50_seconds": round(_percentile(elapsed, 0.5), 3) if elapsed else None,
            "p95_seconds": round(_percentile(elapsed, 0.95), 3) if elapsed else None,
            "last_detail": items[-1].detail if items else {},
            "failure_samples": failures[:2],
        }
    return summary


def _print_summary(summary: dict[str, Any]) -> None:
    print("\n=== Benchmark summary ===")
    for key in sorted(summary):
        item = summary[key]
        print(
            f"{key}: success {item['successes']}/{item['runs']} | "
            f"avg={item['avg_seconds']}s p50={item['p50_seconds']}s p95={item['p95_seconds']}s"
        )
        if item["last_detail"]:
            print(f"  last_detail={json.dumps(item['last_detail'], ensure_ascii=False)}")
        if item["failure_samples"]:
            print(f"  failures={json.dumps(item['failure_samples'], ensure_ascii=False)}")


def run_benchmark(*, runs: int, timeout: int, max_tokens: int | None) -> dict[str, Any]:
    providers = _build_providers()
    scenarios: list[tuple[str, Callable[[Provider, int, int | None], dict[str, Any]]]] = [
        ("simple_chat", _run_simple_chat),
        ("topic_json", _run_topic_json),
    ]
    results: list[SampleResult] = []

    for round_index in range(1, runs + 1):
        ordered_providers = providers if round_index % 2 == 1 else list(reversed(providers))
        for scenario_name, runner in scenarios:
            for provider in ordered_providers:
                started = time.perf_counter()
                try:
                    detail = runner(provider, timeout, max_tokens)
                    success = True
                except Exception as exc:  # pragma: no cover - exercised in live benchmark only
                    detail = {"error": f"{type(exc).__name__}: {exc}"}
                    success = False
                elapsed_seconds = time.perf_counter() - started
                result = SampleResult(
                    provider=provider.name,
                    scenario=scenario_name,
                    round_index=round_index,
                    elapsed_seconds=elapsed_seconds,
                    success=success,
                    detail=detail,
                )
                results.append(result)
                print(
                    f"[round {round_index}] {provider.name} {scenario_name} "
                    f"{'ok' if success else 'fail'} {elapsed_seconds:.3f}s "
                    f"{json.dumps(detail, ensure_ascii=False)}"
                )

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runs": runs,
        "timeout": timeout,
        "max_tokens": max_tokens,
        "providers": [asdict(provider) | {"api_key": "***redacted***"} for provider in providers],
        "results": [asdict(item) for item in results],
        "summary": _summarize(results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare current LLM endpoint vs official Kimi API latency.")
    parser.add_argument("--runs", type=int, default=3, help="Number of rounds per scenario.")
    parser.add_argument("--timeout", type=int, default=90, help="Per-request timeout in seconds.")
    parser.add_argument("--max-tokens", type=int, default=512, help="Max tokens per request.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path (recommended under workdir/).",
    )
    args = parser.parse_args()

    _load_env()
    benchmark = run_benchmark(runs=max(1, args.runs), timeout=max(1, args.timeout), max_tokens=args.max_tokens)
    _print_summary(benchmark["summary"])
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(benchmark, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nSaved JSON report to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
