import { isUnsupportedLocalVideoBrowser } from "./device";
import {
  inspectRenderSourceCompatibility,
  type RenderSourceCompatibility,
} from "./video-render-compatibility";
import { transcodeVideoToBrowserCompatibleMp4 } from "./video-transcode";

export type UploadSourcePreflightErrorCode =
  | "BROWSER_UNSUPPORTED"
  | "TRANSCODE_FAILED";

export class UploadSourcePreflightError extends Error {
  code: UploadSourcePreflightErrorCode;
  compatibility: RenderSourceCompatibility | null;
  causeMessage: string | null;

  constructor(
    code: UploadSourcePreflightErrorCode,
    message: string,
    options: {
      compatibility?: RenderSourceCompatibility | null;
      causeMessage?: string | null;
    } = {}
  ) {
    super(message);
    this.name = "UploadSourcePreflightError";
    this.code = code;
    this.compatibility = options.compatibility ?? null;
    this.causeMessage = options.causeMessage ?? null;
  }
}

export type UploadSourcePreflightStage = "checking" | "transcoding";

export type PrepareUploadSourceFileOptions = {
  onStageChange?: (
    stage: UploadSourcePreflightStage | null,
    compatibility: RenderSourceCompatibility | null
  ) => void;
  onTranscodeProgress?: (progress: number) => void;
};

export type PreparedUploadSourceFile = {
  file: File;
  transcoded: boolean;
  originalCompatibility: RenderSourceCompatibility;
  finalCompatibility: RenderSourceCompatibility;
};

export async function prepareUploadSourceFile(
  sourceFile: File,
  options: PrepareUploadSourceFileOptions = {}
): Promise<PreparedUploadSourceFile> {
  if (isUnsupportedLocalVideoBrowser()) {
    throw new UploadSourcePreflightError(
      "BROWSER_UNSUPPORTED",
      "当前浏览器暂不支持本地视频处理。请使用桌面版 Chrome，Edge 暂不支持。",
      { compatibility: null }
    );
  }

  options.onStageChange?.("checking", null);
  const originalCompatibility = await inspectRenderSourceCompatibility(sourceFile);

  if (originalCompatibility.status === "compatible") {
    options.onStageChange?.(null, originalCompatibility);
    return {
      file: sourceFile,
      transcoded: false,
      originalCompatibility,
      finalCompatibility: originalCompatibility,
    };
  }

  if (originalCompatibility.status === "blocked") {
    options.onStageChange?.(null, originalCompatibility);
    throw new UploadSourcePreflightError(
      "BROWSER_UNSUPPORTED",
      "当前浏览器不支持上传前视频兼容处理。请使用桌面版 Chrome，Edge 暂不支持。",
      { compatibility: originalCompatibility }
    );
  }

  if (originalCompatibility.status !== "incompatible") {
    options.onStageChange?.(null, originalCompatibility);
    return {
      file: sourceFile,
      transcoded: false,
      originalCompatibility,
      finalCompatibility: originalCompatibility,
    };
  }

  options.onStageChange?.("transcoding", originalCompatibility);

  try {
    const transcodedFile = await transcodeVideoToBrowserCompatibleMp4(sourceFile, {
      onProgress: options.onTranscodeProgress,
    });
    const finalCompatibility = await inspectRenderSourceCompatibility(transcodedFile);
    options.onStageChange?.(null, finalCompatibility);

    if (finalCompatibility.status !== "compatible") {
      throw new Error(finalCompatibility.message);
    }

    return {
      file: transcodedFile,
      transcoded: true,
      originalCompatibility,
      finalCompatibility,
    };
  } catch (error) {
    throw new UploadSourcePreflightError(
      "TRANSCODE_FAILED",
      "检测到当前视频格式或编码不兼容，已尝试前端转码但失败。可能是文件过大、浏览器内存不足或源文件异常。请改用桌面版 Chrome，或先转成 H.264/AAC 的 MP4 后再上传。",
      {
        compatibility: originalCompatibility,
        causeMessage: error instanceof Error ? error.message : null,
      }
    );
  }
}
