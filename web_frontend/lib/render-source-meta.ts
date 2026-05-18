"use client";

import type {RenderMeta} from "./api.ts";
import {
  choosePreferredVideoDimensions,
  tryParseVideoMetadataWithMediaInfo,
} from "./media-metadata.ts";

const MEDIA_INFO_BEST_EFFORT_TIMEOUT_MS = 4_000;

function normalizePositiveNumber(value: unknown): number | null {
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
}

function normalizeOptionalPositiveNumber(value: unknown): number | undefined {
  const normalized = normalizePositiveNumber(value);
  return normalized ?? undefined;
}

export function coerceStoredRenderMeta(value: unknown): RenderMeta | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const candidate = value as Partial<RenderMeta>;
  const width = normalizePositiveNumber(candidate.width);
  const height = normalizePositiveNumber(candidate.height);
  const fps = normalizePositiveNumber(candidate.fps);

  if (width === null || height === null || fps === null) {
    return null;
  }

  return {
    width: Math.round(width),
    height: Math.round(height),
    fps: Math.round(fps * 1000) / 1000,
    duration_sec: normalizeOptionalPositiveNumber(candidate.duration_sec),
    source_overall_bitrate: normalizeOptionalPositiveNumber(candidate.source_overall_bitrate),
    source_video_bitrate: normalizeOptionalPositiveNumber(candidate.source_video_bitrate),
    source_audio_bitrate: normalizeOptionalPositiveNumber(candidate.source_audio_bitrate),
    source_video_codec: String(candidate.source_video_codec || "").trim() || undefined,
  };
}

export async function resolveRenderMetaFromFile(file: File): Promise<RenderMeta> {
  const url = URL.createObjectURL(file);
  try {
    const mediaInfoPromise = tryParseVideoMetadataWithMediaInfo(file);
    const meta = await new Promise<{
      width: number;
      height: number;
      duration: number;
    }>((resolve, reject) => {
      const video = document.createElement("video");
      video.preload = "metadata";
      video.muted = true;
      video.onloadedmetadata = () => {
        resolve({
          width: Math.round(video.videoWidth || 0),
          height: Math.round(video.videoHeight || 0),
          duration: video.duration,
        });
      };
      video.onerror = () =>
        reject(new Error("无法读取本地视频元数据，请重新选择文件。"));
      video.src = url;
    });

    const estimateFps = async (): Promise<number> => {
      const probeUrl = URL.createObjectURL(file);
      const video = document.createElement("video");
      video.muted = true;
      video.playsInline = true;
      video.preload = "auto";
      video.src = probeUrl;

      try {
        await video.play();
      } catch {
        URL.revokeObjectURL(probeUrl);
        return 30;
      }

      return await new Promise<number>((resolve) => {
        let firstMediaTime: number | null = null;
        let lastMediaTime: number | null = null;
        let frames = 0;
        const maxFrames = 45;
        const maxMs = 1200;
        const startAt = performance.now();

        const finish = () => {
          try {
            video.pause();
          } catch {
            // ignore
          }
          URL.revokeObjectURL(probeUrl);
          const dt =
            firstMediaTime !== null && lastMediaTime !== null
              ? lastMediaTime - firstMediaTime
              : 0;
          const fps = dt > 0 ? frames / dt : 0;
          if (Number.isFinite(fps) && fps > 1 && fps < 240) {
            resolve(Math.round(fps * 1000) / 1000);
          } else {
            resolve(30);
          }
        };

        const onFrame = (_now: number, frame: {mediaTime: number}) => {
          const time =
            typeof frame?.mediaTime === "number" ? frame.mediaTime : NaN;
          if (Number.isFinite(time)) {
            if (firstMediaTime === null) {
              firstMediaTime = time;
            }
            lastMediaTime = time;
            frames += 1;
          }

          if (frames >= maxFrames || performance.now() - startAt >= maxMs) {
            finish();
            return;
          }

          const requestCallback = (
            video as HTMLVideoElement & {
              requestVideoFrameCallback?: (
                callback: (now: number, frame: {mediaTime: number}) => void,
              ) => void;
            }
          ).requestVideoFrameCallback;
          if (typeof requestCallback === "function") {
            requestCallback.call(video, onFrame);
          } else {
            finish();
          }
        };

        const requestCallback = (
          video as HTMLVideoElement & {
            requestVideoFrameCallback?: (
              callback: (now: number, frame: {mediaTime: number}) => void,
            ) => void;
          }
        ).requestVideoFrameCallback;
        if (typeof requestCallback === "function") {
          requestCallback.call(video, onFrame);
        } else {
          finish();
        }
      });
    };

    const mediaInfoMeta = await Promise.race<
      Awaited<ReturnType<typeof tryParseVideoMetadataWithMediaInfo>> | null
    >([
      mediaInfoPromise.catch(() => null),
      new Promise<null>((resolve) => {
        window.setTimeout(() => resolve(null), MEDIA_INFO_BEST_EFFORT_TIMEOUT_MS);
      }),
    ]);
    const preferredDimensions = choosePreferredVideoDimensions({
      browserWidth: meta.width,
      browserHeight: meta.height,
      metadataWidth: Math.trunc(Number(mediaInfoMeta?.width ?? 0)),
      metadataHeight: Math.trunc(Number(mediaInfoMeta?.height ?? 0)),
    });
    const width = Math.trunc(Number(preferredDimensions.width ?? 0));
    const height = Math.trunc(Number(preferredDimensions.height ?? 0));
    const durationSec =
      typeof meta.duration === "number" &&
      Number.isFinite(meta.duration) &&
      meta.duration > 0
        ? meta.duration
        : typeof mediaInfoMeta?.durationSec === "number" &&
            Number.isFinite(mediaInfoMeta.durationSec) &&
            mediaInfoMeta.durationSec > 0
          ? mediaInfoMeta.durationSec
          : undefined;
    if (width <= 0 || height <= 0) {
      throw new Error("无法读取本地视频分辨率，请重新选择源文件后重试。");
    }
    const fps = mediaInfoMeta?.fps ?? (await estimateFps());
    return {
      width,
      height,
      duration_sec: durationSec,
      fps,
      source_overall_bitrate: mediaInfoMeta?.overallBitrate ?? undefined,
      source_video_bitrate: mediaInfoMeta?.videoBitrate ?? undefined,
      source_audio_bitrate: mediaInfoMeta?.audioBitrate ?? undefined,
      source_video_codec: mediaInfoMeta?.videoCodec ?? undefined,
    };
  } finally {
    URL.revokeObjectURL(url);
  }
}
