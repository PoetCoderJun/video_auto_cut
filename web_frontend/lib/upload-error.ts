import {
  getFriendlyBrowserAudioPipelineErrorMessage,
  isBrowserAudioPipelineCompatibilityError,
} from "./browser-audio-pipeline-error.ts";
import { ApiClientError } from "./api.ts";

const FLUSHING_ERROR_RE = /\bflushing error\b/i;
const BROWSER_PIPELINE_ERROR_RE =
  /\b(video|audio)?\s?(encoder|decoder)\b|webcodec|mux|demux/i;
const NETWORK_FETCH_ERROR_RE =
  /\bfailed to fetch\b|\bload failed\b|\bnetworkerror\b|\bnetwork request failed\b/i;
const ASCII_TECHNICAL_ERROR_RE = /^[\x00-\x7f\s.,:;!?()[\]{}'"`\\/_+-]+$/;

function isNamedError(error: unknown, name: string): error is Error {
  return error instanceof Error && error.name === name;
}

function unwrapUploadIssueError(error: unknown): unknown {
  if (
    error instanceof Error &&
    error.name === "UploadPipelineError" &&
    "cause" in error &&
    (error as Error & { cause?: unknown }).cause
  ) {
    return (error as Error & { cause?: unknown }).cause;
  }
  return error;
}

export function getUploadIssueErrorName(error: unknown): string {
  const unwrapped = unwrapUploadIssueError(error);
  return unwrapped instanceof Error ? unwrapped.name : typeof unwrapped;
}

export function getUploadIssueErrorMessage(error: unknown): string {
  const unwrapped = unwrapUploadIssueError(error);
  if (unwrapped instanceof ApiClientError) {
    return unwrapped.details ? `${unwrapped.message} [${unwrapped.details}]` : unwrapped.message;
  }
  return unwrapped instanceof Error ? unwrapped.message : String(unwrapped ?? "");
}

export function getFriendlyUploadErrorMessage(error: unknown): string {
  if (isNamedError(error, "UploadSourcePreflightError")) {
    return error.message;
  }
  if (isNamedError(error, "AudioExtractError")) {
    return error.message;
  }
  if (error instanceof Error && error.message) {
    const message = error.message.trim();
    if (!message) {
      return "上传失败，请稍后重试。";
    }
    if (NETWORK_FETCH_ERROR_RE.test(message)) {
      return "无法连接登录或上传服务。请确认页面当前地址可正常访问，并检查前后端服务是否已启动后重试。";
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
