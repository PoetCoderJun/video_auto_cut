import { isUnsupportedLocalVideoBrowser } from "./device.ts";
import {
  inspectRenderSourceCompatibility,
  type RenderSourceCompatibility,
} from "./video-render-compatibility.ts";

export type UploadSourcePreflightErrorCode =
  | "BROWSER_UNSUPPORTED"
  | "SOURCE_INCOMPATIBLE";

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

export type UploadSourcePreflightStage = "checking";

export type PrepareUploadSourceFileOptions = {
  onStageChange?: (
    stage: UploadSourcePreflightStage | null,
    compatibility: RenderSourceCompatibility | null
  ) => void;
};

export type PreparedUploadSourceFile = {
  file: File;
  transcoded: false;
  originalCompatibility: RenderSourceCompatibility;
  finalCompatibility: RenderSourceCompatibility;
};

export function getUploadSourcePreflightError(
  compatibility: RenderSourceCompatibility
): UploadSourcePreflightError | null {
  if (compatibility.status === "blocked") {
    return new UploadSourcePreflightError(
      "BROWSER_UNSUPPORTED",
      "当前浏览器不支持上传前视频兼容处理。请使用桌面版 Chrome，Edge 暂不支持。",
      { compatibility }
    );
  }

  if (compatibility.status === "incompatible") {
    return new UploadSourcePreflightError(
      "SOURCE_INCOMPATIBLE",
      compatibility.message,
      {
        compatibility,
        causeMessage: compatibility.message,
      }
    );
  }

  return null;
}

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
  options.onStageChange?.(null, originalCompatibility);

  const preflightError = getUploadSourcePreflightError(originalCompatibility);
  if (preflightError) {
    throw preflightError;
  }

  return {
    file: sourceFile,
    transcoded: false,
    originalCompatibility,
    finalCompatibility: originalCompatibility,
  };
}
