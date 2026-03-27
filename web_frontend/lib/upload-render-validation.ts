import type {
  CanRenderIssue,
  CanRenderMediaOnWebOptions,
} from "@remotion/web-renderer";

type RenderValidationMetadata = {
  width: number;
  height: number;
};

type RenderValidationAttempt = {
  options: CanRenderMediaOnWebOptions;
  label: string;
};

async function loadSourceMetadata(
  sourceFile: File,
): Promise<RenderValidationMetadata> {
  const sourceUrl = URL.createObjectURL(sourceFile);
  try {
    return await new Promise<RenderValidationMetadata>((resolve, reject) => {
      const video = document.createElement("video");
      video.preload = "metadata";
      video.onloadedmetadata = () => {
        resolve({
          width: Math.max(1, video.videoWidth || 1280),
          height: Math.max(1, video.videoHeight || 720),
        });
      };
      video.onerror = () => {
        reject(new Error("浏览器无法读取当前源视频的元数据。"));
      };
      video.src = sourceUrl;
    });
  } finally {
    URL.revokeObjectURL(sourceUrl);
  }
}

function buildValidationAttempts(
  metadata: RenderValidationMetadata,
): RenderValidationAttempt[] {
  return [
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
    {
      label: "mp4-muted",
      options: {
        width: metadata.width,
        height: metadata.height,
        container: "mp4",
        videoCodec: "h264",
        audioCodec: null,
        muted: true,
      },
    },
  ];
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

export async function validateBrowserRenderCapability(
  sourceFile: File,
): Promise<void> {
  if (typeof window === "undefined") {
    return;
  }

  const metadata = await loadSourceMetadata(sourceFile);
  const { canRenderMediaOnWeb } = await import("@remotion/web-renderer");

  let lastIssues: CanRenderIssue[] = [];
  for (const attempt of buildValidationAttempts(metadata)) {
    const result = await canRenderMediaOnWeb(attempt.options);
    if (result.canRender) {
      return;
    }
    lastIssues = result.issues;
    console.warn("[upload-render-validation] capability check failed", {
      attempt: attempt.label,
      issues: result.issues,
    });
  }

  throw new Error(getFriendlyCanRenderIssueMessage(lastIssues));
}
