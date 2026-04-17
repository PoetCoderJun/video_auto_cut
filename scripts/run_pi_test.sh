#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
用法：
  ./scripts/run_pi_test.sh <媒体或SRT输入> [额外 pi_agent_runner 参数]

说明：
  - 自动进入仓库根目录
  - 自动加载仓库 .env（如果存在）
  - 自动复用 .pi/settings.json 中的 skills 配置
  - 自动执行四步：asr -> delete -> polish -> chapter

示例：
  ./scripts/run_pi_test.sh test_data/media/1.wav
  ./scripts/run_pi_test.sh /path/to/video.mp4 --lang zh
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" || $# -lt 1 ]]; then
  usage
  exit 0
fi

INPUT_PATH="$1"
shift || true

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi

PI_PROVIDER_NORMALIZED="$(printf '%s' "${PI_PROVIDER:-}" | tr '[:upper:]' '[:lower:]')"
if [[ -z "$PI_PROVIDER_NORMALIZED" && -n "${KIMI_API_KEY:-${MOONSHOT_API_KEY:-}}" ]]; then
  PI_PROVIDER_NORMALIZED="kimi-coding"
fi
if [[ "$PI_PROVIDER_NORMALIZED" == "kimi-coding" ]]; then
  if [[ -z "${KIMI_API_KEY:-}" ]]; then
    if [[ -n "${MOONSHOT_API_KEY:-}" ]]; then
      export KIMI_API_KEY="${MOONSHOT_API_KEY}"
    else
      echo "缺少 Kimi Coding 配置：PI_PROVIDER=kimi-coding 时，请先设置 KIMI_API_KEY（或 MOONSHOT_API_KEY）。" >&2
      exit 1
    fi
  fi
  if [[ -z "${PI_PROVIDER:-}" ]]; then
    export PI_PROVIDER="kimi-coding"
  fi
  if [[ -z "${PI_MODEL:-}" ]]; then
    export PI_MODEL="k2p5"
  fi
else
  if [[ -z "${LLM_BASE_URL:-}" || -z "${LLM_MODEL:-}" ]]; then
    echo "缺少 LLM 配置：请先设置 LLM_BASE_URL 和 LLM_MODEL；若要走 Kimi Coding，请设置 PI_PROVIDER=kimi-coding 和 KIMI_API_KEY。" >&2
    exit 1
  fi
fi

RUN_STEM="$(basename "${INPUT_PATH%.*}")"
RUN_ID="${PI_RUN_ID:-$(date +%Y%m%d_%H%M%S)_${RUN_STEM}}"
OUTPUT_DIR="${PI_OUTPUT_DIR:-workdir/pi_runs/${RUN_ID}}"
OUTPUT_PATH="${OUTPUT_DIR}/test.summary.json"

mkdir -p "$OUTPUT_DIR"

echo ">>> PI 四步剪辑启动"
echo ">>> 输入: $INPUT_PATH"
echo ">>> 输出目录: $OUTPUT_DIR"
if [[ "$PI_PROVIDER_NORMALIZED" == "kimi-coding" ]]; then
  echo ">>> PI Provider: kimi-coding/${PI_MODEL}"
else
  echo ">>> PI Provider: vac-llm/${LLM_MODEL}"
fi

python -m video_auto_cut.pi_agent_runner \
  --task test \
  --input "$INPUT_PATH" \
  --output "$OUTPUT_PATH" \
  "$@"

echo ">>> 完成"
echo ">>> 汇总: $OUTPUT_PATH"
