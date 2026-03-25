#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT_DIR/web_frontend/public/generated-format-samples"

mkdir -p "$OUT_DIR"

ffmpeg -y \
  -f lavfi -i testsrc2=size=360x640:rate=30 \
  -f lavfi -i sine=frequency=880:sample_rate=48000 \
  -t 1.6 \
  -c:v libx264 -pix_fmt yuv420p \
  -c:a aac -b:a 96k \
  -movflags +faststart \
  "$OUT_DIR/small_h264_aac_mp4.mp4"

ffmpeg -y \
  -f lavfi -i testsrc2=size=360x640:rate=30 \
  -f lavfi -i sine=frequency=660:sample_rate=48000 \
  -t 1.6 \
  -c:v libx265 -tag:v hvc1 -pix_fmt yuv420p \
  -c:a aac -b:a 96k \
  -movflags +faststart \
  "$OUT_DIR/small_hevc_aac_mp4.mp4"

ffmpeg -y \
  -f lavfi -i testsrc2=size=360x640:rate=30 \
  -f lavfi -i sine=frequency=550:sample_rate=48000 \
  -t 1.6 \
  -c:v libx265 -tag:v hvc1 -pix_fmt yuv420p \
  -c:a aac -b:a 96k \
  "$OUT_DIR/small_hevc_aac_mov.mov"

ffmpeg -y \
  -f lavfi -i testsrc2=size=360x640:rate=30 \
  -f lavfi -i sine=frequency=440:sample_rate=48000 \
  -t 1.6 \
  -c:v libvpx-vp9 -b:v 0 -crf 34 -pix_fmt yuv420p \
  -c:a libopus -b:a 64k \
  "$OUT_DIR/small_vp9_opus_webm.webm"
