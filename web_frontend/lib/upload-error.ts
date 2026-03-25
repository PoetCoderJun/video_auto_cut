import { AudioExtractError } from "./audio-extract";
import { UploadSourcePreflightError } from "./upload-source-preflight";

export function getFriendlyUploadErrorMessage(error: unknown): string {
  if (error instanceof UploadSourcePreflightError) {
    return error.message;
  }
  if (error instanceof AudioExtractError) {
    return error.message;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "上传失败，请稍后重试。";
}
