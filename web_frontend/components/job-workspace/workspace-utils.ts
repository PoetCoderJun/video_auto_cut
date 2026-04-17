"use client";

import type {RenderMeta, TestLine, WebRenderConfig} from "../../lib/api.ts";
import {
  choosePreferredVideoDimensions,
  tryParseVideoMetadataWithMediaInfo,
} from "../../lib/media-metadata.ts";
import {getRenderConfigTotalDuration} from "../../lib/remotion/utils.ts";
import {clamp} from "../../lib/utils.ts";
import {formatDuration} from "../../lib/source-video-guard.ts";

const PREVIEW_MAX_LONG_EDGE = 960;
const PREVIEW_MAX_PIXEL_COUNT = 960 * 540;
const PREVIEW_MAX_FPS = 10;

function ensureEvenDimension(value: number): number {
  const rounded = Math.max(2, Math.round(value));
  return rounded % 2 === 0 ? rounded : rounded - 1;
}


export function autoResize(target: HTMLTextAreaElement) {
  target.style.height = "auto";
  target.style.height = `${target.scrollHeight}px`;
}

export function triggerFileDownload(url: string, fileName: string) {
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export function clampPercent(value: number): number {
  return clamp(value, 0, 100);
}

export function withTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
  message: string,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      reject(new Error(message));
    }, timeoutMs);

    promise.then(
      (value) => {
        window.clearTimeout(timeoutId);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timeoutId);
        reject(error);
      },
    );
  });
}

export function getFriendlyError(err: unknown): string {
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return "网络异常，请稍后重试。";
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

    const mediaInfoMeta = await mediaInfoPromise;
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

export function buildPreviewRenderMeta(meta: RenderMeta): RenderMeta {
  const sourceWidth = Math.max(2, Math.round(Number(meta.width) || 0));
  const sourceHeight = Math.max(2, Math.round(Number(meta.height) || 0));
  const sourceFps = Number.isFinite(meta.fps) && meta.fps > 0 ? meta.fps : 30;

  const sourcePixels = sourceWidth * sourceHeight;
  const longEdgeScale = PREVIEW_MAX_LONG_EDGE / Math.max(sourceWidth, sourceHeight);
  const pixelScale = Math.sqrt(PREVIEW_MAX_PIXEL_COUNT / Math.max(1, sourcePixels));
  const scale = Math.min(1, longEdgeScale, pixelScale);

  return {
    ...meta,
    width: ensureEvenDimension(sourceWidth * scale),
    height: ensureEvenDimension(sourceHeight * scale),
    fps: Math.min(sourceFps, PREVIEW_MAX_FPS),
  };
}

export function isPreviewRenderMetaReduced(sourceMeta: RenderMeta, previewMeta: RenderMeta): boolean {
  return (
    previewMeta.width < sourceMeta.width ||
    previewMeta.height < sourceMeta.height ||
    previewMeta.fps < sourceMeta.fps
  );
}

export function getRandomPreviewTime(config: WebRenderConfig): number {
  const captionCandidates = config.input_props.captions
    .filter((caption) => caption.end > caption.start)
    .map((caption) => {
      const start = Number(caption.start);
      const end = Number(caption.end);
      return Math.max(
        start,
        Math.min(end - 0.08, start + (end - start) * 0.45),
      );
    })
    .filter((value) => Number.isFinite(value) && value >= 0);

  if (captionCandidates.length > 0) {
    const index = Math.floor(Math.random() * captionCandidates.length);
    return captionCandidates[index];
  }

  const topicCandidates = config.input_props.topics
    .filter((topic) => topic.end > topic.start)
    .map((topic) => topic.start)
    .filter((value) => Number.isFinite(value) && value >= 0);

  if (topicCandidates.length > 0) {
    const index = Math.floor(Math.random() * topicCandidates.length);
    return topicCandidates[index];
  }

  const totalDuration = getRenderConfigTotalDuration(config);
  return totalDuration * (0.25 + Math.random() * 0.5);
}

const TEST_PREVIEW_LINE_LIMIT = 14;

export function getTestPreviewLines(lines: TestLine[]): string[] {
  return lines
    .map((line) => {
      const removed = Boolean(line.user_final_remove);
      const text = String(line.optimized_text || line.original_text || "").trim();
      const resolvedText = text || (removed ? "<No Speech>" : "");
      if (!resolvedText) {
        return null;
      }
      return `【${formatDuration(line.start)}】${removed ? "<remove>" : ""}${resolvedText}`;
    })
    .filter((line): line is string => line !== null)
    .slice(0, TEST_PREVIEW_LINE_LIMIT);
}
