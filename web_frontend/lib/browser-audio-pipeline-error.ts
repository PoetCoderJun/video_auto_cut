export type BrowserAudioPipelineErrorContext = "upload" | "render";

const BROWSER_AUDIO_PIPELINE_COMPATIBILITY_RE =
  /(?:AudioData.*copyTo|copyTo.*AudioData|AudioData currently only supports copy conversion to f32-planar|No audio codec can be encoded)/i;

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error ?? "");
}

export function isBrowserAudioPipelineCompatibilityError(
  error: unknown,
): boolean {
  const message = getErrorMessage(error).trim();
  return Boolean(message) && BROWSER_AUDIO_PIPELINE_COMPATIBILITY_RE.test(message);
}

export function getFriendlyBrowserAudioPipelineErrorMessage(
  context: BrowserAudioPipelineErrorContext,
): string {
  if (context === "upload") {
    return "当前浏览器本地音频处理失败。请刷新页面后重试；如果仍失败，请改用最新版 Chrome，或先转成 H.264/AAC 的 MP4 后再上传。";
  }

  return "当前浏览器本地音频处理失败。请刷新页面后重试；如果仍失败，请改用最新版 Chrome，或先将源视频转成 H.264/AAC 的 MP4 后再导出。";
}
