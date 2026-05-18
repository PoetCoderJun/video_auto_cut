"use client";

import type {RenderMeta, TestLine, WebRenderConfig} from "../../lib/api.ts";
export {resolveRenderMetaFromFile} from "../../lib/render-source-meta.ts";
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


const AUTO_RESIZE_MAX_HEIGHT_PX = 320;

export function autoResize(target: HTMLTextAreaElement) {
  target.style.height = "auto";
  target.style.height = `${Math.min(target.scrollHeight, AUTO_RESIZE_MAX_HEIGHT_PX)}px`;
}

export function observeTextAreaResize(
  element: HTMLTextAreaElement,
  callback: () => void,
): () => void {
  const handleResize = () => callback();
  window.addEventListener("resize", handleResize);
  return () => window.removeEventListener("resize", handleResize);
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
