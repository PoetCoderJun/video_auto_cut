import type { RenderMeta } from "../api";

export type WebRenderVideoCodec = "h264" | "vp8" | "vp9" | "h265" | "av1";
export type WebRenderAudioCodec = "aac" | "opus";

type WebRenderQuality = "low" | "medium" | "high" | "very-high";

const AAC_VALID_BITRATES = [96_000, 128_000, 160_000, 192_000] as const;
const REFERENCE_PIXELS = 1920 * 1080;
const REFERENCE_BITRATE = 3_000_000;
const QUALITY_FACTORS: Record<WebRenderQuality, number> = {
  low: 0.6,
  medium: 1,
  high: 2,
  "very-high": 4,
};
const CODEC_EFFICIENCY_FACTORS: Record<WebRenderVideoCodec, number> = {
  h264: 1,
  h265: 0.6,
  vp8: 1.2,
  vp9: 0.6,
  av1: 0.4,
};

export type DynamicRenderBitratePlan = {
  videoBitrate: number;
  audioBitrate: number;
  fallbackVideoBitrate: number;
  usingSourceBitrate: boolean;
};

type NormalizeVideoBitrateOptions = {
  width: number;
  height: number;
  codec: WebRenderVideoCodec;
};

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function roundToNearestThousand(value: number): number {
  return Math.max(1_000, Math.round(value / 1_000) * 1_000);
}

function normalizeAacBitrate(target: number): number {
  return AAC_VALID_BITRATES.reduce((previous, current) =>
    Math.abs(current - target) < Math.abs(previous - target) ? current : previous
  );
}

function normalizeAudioBitrate(codec: WebRenderAudioCodec, target: number): number {
  const normalized = roundToNearestThousand(clamp(target, 32_000, 320_000));
  if (codec === "aac") {
    return normalizeAacBitrate(normalized);
  }
  return roundToNearestThousand(clamp(normalized, 64_000, 256_000));
}

export function estimateWebRenderVideoBitrate(
  width: number,
  height: number,
  codec: WebRenderVideoCodec,
  quality: WebRenderQuality
): number {
  const pixels = Math.max(1, Math.trunc(width)) * Math.max(1, Math.trunc(height));
  const scaleFactor = Math.pow(pixels / REFERENCE_PIXELS, 0.95);
  const baseBitrate = REFERENCE_BITRATE * scaleFactor;
  const codecAdjusted = baseBitrate * CODEC_EFFICIENCY_FACTORS[codec];
  return roundToNearestThousand(codecAdjusted * QUALITY_FACTORS[quality]);
}

function normalizeVideoBitrate(
  target: number,
  options: NormalizeVideoBitrateOptions
): number {
  const { width, height, codec } = options;
  const floor = estimateWebRenderVideoBitrate(width, height, codec, "low");
  const ceil = Math.max(
    estimateWebRenderVideoBitrate(width, height, codec, "very-high"),
    60_000_000
  );
  return roundToNearestThousand(clamp(target, floor, ceil));
}

function inferOverallBitrate(meta: RenderMeta, fileSizeBytes: number | null | undefined): number | null {
  const sourceOverall = Number(meta.source_overall_bitrate);
  if (Number.isFinite(sourceOverall) && sourceOverall > 0) {
    return sourceOverall;
  }

  const durationSec = Number(meta.duration_sec);
  const fileSize = Number(fileSizeBytes);
  if (Number.isFinite(durationSec) && durationSec > 0 && Number.isFinite(fileSize) && fileSize > 0) {
    return roundToNearestThousand((fileSize * 8) / durationSec);
  }

  return null;
}

function inferAudioBitrate(meta: RenderMeta, codec: WebRenderAudioCodec): number {
  const sourceAudio = Number(meta.source_audio_bitrate);
  if (Number.isFinite(sourceAudio) && sourceAudio > 0) {
    return normalizeAudioBitrate(codec, sourceAudio);
  }

  return codec === "aac" ? 128_000 : 96_000;
}

function inferVideoBitrate(meta: RenderMeta, audioBitrate: number, overallBitrate: number | null): number | null {
  const sourceVideo = Number(meta.source_video_bitrate);
  if (Number.isFinite(sourceVideo) && sourceVideo > 0) {
    return sourceVideo;
  }

  if (overallBitrate !== null) {
    return Math.max(250_000, overallBitrate - audioBitrate);
  }

  return null;
}

export function buildDynamicRenderBitratePlan(options: {
  meta: RenderMeta;
  fileSizeBytes?: number | null;
  videoCodec: WebRenderVideoCodec;
  audioCodec: WebRenderAudioCodec;
}): DynamicRenderBitratePlan {
  const { meta, fileSizeBytes, videoCodec, audioCodec } = options;
  const fallbackVideoBitrate = estimateWebRenderVideoBitrate(
    meta.width,
    meta.height,
    videoCodec,
    "high"
  );
  const audioBitrate = inferAudioBitrate(meta, audioCodec);
  const overallBitrate = inferOverallBitrate(meta, fileSizeBytes);
  const sourceVideoBitrate = inferVideoBitrate(meta, audioBitrate, overallBitrate);

  if (sourceVideoBitrate === null) {
    return {
      videoBitrate: fallbackVideoBitrate,
      audioBitrate,
      fallbackVideoBitrate,
      usingSourceBitrate: false,
    };
  }

  return {
    videoBitrate: normalizeVideoBitrate(sourceVideoBitrate, {
      width: meta.width,
      height: meta.height,
      codec: videoCodec,
    }),
    audioBitrate,
    fallbackVideoBitrate,
    usingSourceBitrate: true,
  };
}

export function buildVideoBitrateFallbacks(
  preferredBitrate: number,
  fallbackBitrate: number
): number[] {
  const candidates = [
    preferredBitrate,
    Math.round(preferredBitrate * 0.9),
    Math.round(preferredBitrate * 0.8),
    Math.round(preferredBitrate * 0.67),
    fallbackBitrate,
  ];
  const seen = new Set<number>();
  const result: number[] = [];
  for (const candidate of candidates) {
    const normalized = roundToNearestThousand(Math.max(250_000, candidate));
    if (seen.has(normalized)) continue;
    seen.add(normalized);
    result.push(normalized);
  }
  return result;
}
