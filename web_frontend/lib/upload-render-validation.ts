import type {
  CanRenderIssue,
  CanRenderMediaOnWebOptions,
} from "@remotion/web-renderer";
import {
  getFriendlyBrowserAudioPipelineErrorMessage,
  isBrowserAudioPipelineCompatibilityError,
} from "./browser-audio-pipeline-error.ts";

type RenderValidationMetadata = {
  width: number;
  height: number;
};

type RenderValidationDeps = {
  loadMetadata?: (
    sourceFile: File,
    timeoutMs: number,
  ) => Promise<RenderValidationMetadata>;
  loadRenderer?: () => Promise<{
    canRenderMediaOnWeb: (
      options: CanRenderMediaOnWebOptions,
    ) => Promise<{
      canRender: boolean;
      issues: CanRenderIssue[];
    }>;
  }>;
  metadataTimeoutMs?: number;
  rendererImportTimeoutMs?: number;
  capabilityAttemptTimeoutMs?: number;
};

const METADATA_LOAD_TIMEOUT_MS = 15_000;
const RENDERER_IMPORT_TIMEOUT_MS = 10_000;
const CAPABILITY_ATTEMPT_TIMEOUT_MS = 10_000;

export class RenderCapabilityValidationTimeoutError extends Error {
  readonly label: string;
  readonly timeoutMs: number;

  constructor(label: string, timeoutMs: number) {
    super(`${label} timed out after ${timeoutMs}ms`);
    this.name = "RenderCapabilityValidationTimeoutError";
    this.label = label;
    this.timeoutMs = timeoutMs;
  }
}

function isTimeoutError(error: unknown): error is RenderCapabilityValidationTimeoutError {
  return error instanceof RenderCapabilityValidationTimeoutError;
}

function withTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
  label: string,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      reject(new RenderCapabilityValidationTimeoutError(label, timeoutMs));
    }, timeoutMs);

    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timer);
        reject(error);
      },
    );
  });
}

function cleanupMetadataProbe(video: HTMLVideoElement, sourceUrl: string): void {
  video.onloadedmetadata = null;
  video.onerror = null;
  try {
    video.pause();
  } catch {
    // ignore
  }
  try {
    video.removeAttribute("src");
    video.load();
  } catch {
    // ignore
  }
  URL.revokeObjectURL(sourceUrl);
}

async function loadSourceMetadata(
  sourceFile: File,
  timeoutMs = METADATA_LOAD_TIMEOUT_MS,
): Promise<RenderValidationMetadata> {
  const sourceUrl = URL.createObjectURL(sourceFile);
  return await new Promise<RenderValidationMetadata>((resolve, reject) => {
    const video = document.createElement("video");
    let settled = false;
    const settle = (handler: "resolve" | "reject", value: RenderValidationMetadata | Error) => {
      if (settled) {
        return;
      }
      settled = true;
      window.clearTimeout(timer);
      cleanupMetadataProbe(video, sourceUrl);
      if (handler === "resolve") {
        resolve(value as RenderValidationMetadata);
        return;
      }
      reject(value);
    };
    const timer = window.setTimeout(() => {
      settle(
        "reject",
        new RenderCapabilityValidationTimeoutError("load-source-metadata", timeoutMs),
      );
    }, timeoutMs);

    video.preload = "metadata";
    video.muted = true;
    video.playsInline = true;
    video.onloadedmetadata = () => {
      settle("resolve", {
        width: Math.max(1, video.videoWidth || 1280),
        height: Math.max(1, video.videoHeight || 720),
      });
    };
    video.onerror = () => {
      settle("reject", new Error("浏览器无法读取当前源视频的元数据。"));
    };
    video.src = sourceUrl;
  });
}

function isNonBlockingCapabilityProbeError(error: unknown): boolean {
  return isTimeoutError(error);
}

export function getFriendlyCanRenderIssueMessage(
  issues: CanRenderIssue[],
): string {
  if (!issues.length) {
    return "当前浏览器环境暂不支持视频导出。请使用最新版 Chrome，并通过 HTTPS 访问本站后重试。";
  }

  const types = new Set(issues.map((issue) => issue.type));

  if (types.has("webcodecs-unavailable")) {
    return "当前浏览器环境未启用 WebCodecs，无法在本地导出视频。请使用最新版 Chrome，并通过 HTTPS 访问本站后重试。";
  }

  if (types.has("webgl-unsupported")) {
    return "当前浏览器图形能力不足，无法在本地导出视频。请改用最新版 Chrome，或更换设备后重试。";
  }

  if (
    types.has("video-codec-unsupported") ||
    types.has("audio-codec-unsupported") ||
    types.has("container-codec-mismatch")
  ) {
    return "当前浏览器不支持本地导出所需的音视频编码组合。请使用最新版 Chrome，或先转成 H.264/AAC 的 MP4 后再试。";
  }

  if (types.has("invalid-dimensions")) {
    return "当前视频尺寸超出浏览器本地导出支持范围。请先压缩或转码后重试。";
  }

  const firstError =
    issues.find((issue) => issue.severity === "error") ?? issues[0];
  const detail = String(firstError?.message || "").trim();
  if (detail) {
    return `当前浏览器环境暂不支持本地导出：${detail}`;
  }

  return "当前浏览器环境暂不支持视频导出。请使用最新版 Chrome，并通过 HTTPS 访问本站后重试。";
}

export function getFriendlyCanRenderThrownErrorMessage(error: unknown): string {
  const detail =
    error instanceof Error ? error.message.trim() : String(error ?? "").trim();

  if (isBrowserAudioPipelineCompatibilityError(detail)) {
    return getFriendlyBrowserAudioPipelineErrorMessage("upload");
  }

  if (detail) {
    return `当前浏览器环境暂不支持本地导出：${detail}`;
  }

  return "当前浏览器环境暂不支持视频导出。请使用最新版 Chrome，并通过 HTTPS 访问本站后重试。";
}

export async function validateBrowserRenderCapability(
  sourceFile: File,
  deps: RenderValidationDeps = {},
): Promise<void> {
  if (typeof window === "undefined") {
    return;
  }

  const metadataTimeoutMs = Math.max(
    1000,
    deps.metadataTimeoutMs ?? METADATA_LOAD_TIMEOUT_MS,
  );
  const rendererImportTimeoutMs = Math.max(
    1000,
    deps.rendererImportTimeoutMs ?? RENDERER_IMPORT_TIMEOUT_MS,
  );
  const capabilityAttemptTimeoutMs = Math.max(
    1000,
    deps.capabilityAttemptTimeoutMs ?? CAPABILITY_ATTEMPT_TIMEOUT_MS,
  );

  const metadataLoader = deps.loadMetadata ?? loadSourceMetadata;
  const rendererLoader = deps.loadRenderer ?? (async () => await import("@remotion/web-renderer"));

  let metadata: RenderValidationMetadata;
  try {
    metadata = await metadataLoader(sourceFile, metadataTimeoutMs);
  } catch (error) {
    if (isNonBlockingCapabilityProbeError(error)) {
      console.warn("[upload-render-validation] metadata probe timed out, continuing upload", {
        error,
      });
      return;
    }
    throw error;
  }

  let canRenderMediaOnWeb: (
    options: CanRenderMediaOnWebOptions,
  ) => Promise<{
    canRender: boolean;
    issues: CanRenderIssue[];
  }>;
  try {
    ({ canRenderMediaOnWeb } = await withTimeout(
      rendererLoader(),
      rendererImportTimeoutMs,
      "load-renderer",
    ));
  } catch (error) {
    if (isNonBlockingCapabilityProbeError(error)) {
      console.warn("[upload-render-validation] renderer import timed out, continuing upload", {
        error,
      });
      return;
    }
    throw error;
  }

  const validationAttempts: Array<{
    label: string;
    options: CanRenderMediaOnWebOptions;
  }> = [
    {
      label: "mp4-aac",
      options: {
        width: metadata.width,
        height: metadata.height,
        container: "mp4",
        videoCodec: "h264",
        audioCodec: "aac",
      },
    },
    {
      label: "webm-opus",
      options: {
        width: metadata.width,
        height: metadata.height,
        container: "webm",
        videoCodec: "vp8",
        audioCodec: "opus",
      },
    },
  ];

  let lastIssues: CanRenderIssue[] = [];
  let lastThrownError: unknown = null;
  for (const attempt of validationAttempts) {
    try {
      const result = await withTimeout(
        canRenderMediaOnWeb(attempt.options),
        capabilityAttemptTimeoutMs,
        `capability-check-${attempt.label}`,
      );
      if (result.canRender) {
        return;
      }
      lastThrownError = null;
      lastIssues = result.issues;
      console.warn("[upload-render-validation] capability check failed", {
        attempt: attempt.label,
        issues: result.issues,
      });
    } catch (error) {
      lastIssues = [];
      lastThrownError = error;
      if (isNonBlockingCapabilityProbeError(error)) {
        console.warn("[upload-render-validation] capability check timed out, continuing upload", {
          attempt: attempt.label,
          error,
        });
        return;
      }
      console.warn("[upload-render-validation] capability check threw", {
        attempt: attempt.label,
        error,
      });
    }
  }

  if (lastThrownError) {
    throw new Error(getFriendlyCanRenderThrownErrorMessage(lastThrownError));
  }

  throw new Error(getFriendlyCanRenderIssueMessage(lastIssues));
}
