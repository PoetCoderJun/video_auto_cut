import test from "node:test";
import assert from "node:assert/strict";

import {
  buildDynamicRenderBitratePlan,
  buildVideoBitrateFallbacks,
  estimateWebRenderVideoBitrate,
} from "./export-bitrate.ts";

test("buildDynamicRenderBitratePlan prefers source bitrates when available", () => {
  const plan = buildDynamicRenderBitratePlan({
    meta: {
      width: 1920,
      height: 1080,
      fps: 30,
      duration_sec: 60,
      source_overall_bitrate: 10_500_000,
      source_video_bitrate: 10_000_000,
      source_audio_bitrate: 192_000,
      source_video_codec: "HEVC",
    },
    fileSizeBytes: 78_750_000,
    videoCodec: "h264",
    audioCodec: "aac",
  });

  assert.equal(plan.videoBitrate, 10_000_000);
  assert.equal(plan.audioBitrate, 192_000);
  assert.equal(plan.usingSourceBitrate, true);
});

test("buildDynamicRenderBitratePlan falls back to file size and duration when stream bitrate is absent", () => {
  const plan = buildDynamicRenderBitratePlan({
    meta: {
      width: 1920,
      height: 1080,
      fps: 30,
      duration_sec: 80,
    },
    fileSizeBytes: 96_000_000,
    videoCodec: "h264",
    audioCodec: "aac",
  });

  assert.equal(plan.audioBitrate, 128_000);
  assert.ok(plan.videoBitrate >= 9_000_000, `expected derived video bitrate >= 9 Mbps, got ${plan.videoBitrate}`);
  assert.equal(plan.usingSourceBitrate, true);
});

test("buildDynamicRenderBitratePlan uses quality fallback when source bitrate is unavailable", () => {
  const fallbackHigh = estimateWebRenderVideoBitrate(1920, 1080, "h264", "high");
  const plan = buildDynamicRenderBitratePlan({
    meta: {
      width: 1920,
      height: 1080,
      fps: 30,
    },
    videoCodec: "h264",
    audioCodec: "aac",
  });

  assert.equal(plan.videoBitrate, fallbackHigh);
  assert.equal(plan.fallbackVideoBitrate, fallbackHigh);
  assert.equal(plan.usingSourceBitrate, false);
});

test("buildVideoBitrateFallbacks returns descending unique bitrate ladder", () => {
  assert.deepEqual(buildVideoBitrateFallbacks(10_000_000, 6_000_000), [
    10_000_000,
    9_000_000,
    8_000_000,
    6_700_000,
    6_000_000,
  ]);
});
