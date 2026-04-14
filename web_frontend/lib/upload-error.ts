import { AudioExtractError } from "./audio-extract";
import {
  getFriendlyBrowserAudioPipelineErrorMessage,
  isBrowserAudioPipelineCompatibilityError,
} from "./browser-audio-pipeline-error.ts";
import { UploadSourcePreflightError } from "./upload-source-preflight";

const FLUSHING_ERROR_RE = /\bflushing error\b/i;
const BROWSER_PIPELINE_ERROR_RE =
  /\b(video|audio)?\s?(encoder|decoder)\b|webcodec|mux|demux/i;
const ASCII_TECHNICAL_ERROR_RE = /^[\x00-\x7f\s.,:;!?()[\]{}'"`\\/_+-]+$/;

export function getFriendlyUploadErrorMessage(error: unknown): string {
  if (error instanceof UploadSourcePreflightError) {
    return error.message;
  }
  if (error instanceof AudioExtractError) {
    return error.message;
  }
  if (error instanceof Error && error.message) {
    const message = error.message.trim();
    if (!message) {
      return "上传失败，请稍后重试。";
    }
    if (isBrowserAudioPipelineCompatibilityError(message)) {
      return getFriendlyBrowserAudioPipelineErrorMessage("upload");
    }
    if (FLUSHING_ERROR_RE.test(message) || BROWSER_PIPELINE_ERROR_RE.test(message)) {
      return "浏览器本地视频编码器初始化失败。请刷新页面后重试；如果仍失败，请改用最新版 Chrome，或先转成 H.264/AAC 的 MP4 后再上传。";
    }
    if (ASCII_TECHNICAL_ERROR_RE.test(message) && !/https?:\/\//i.test(message)) {
      return "上传前浏览器本地处理失败。请刷新页面后重试；如果仍失败，请改用最新版 Chrome，或先转成 H.264/AAC 的 MP4 后再上传。";
    }
    return message;
  }
  return "上传失败，请稍后重试。";
}
