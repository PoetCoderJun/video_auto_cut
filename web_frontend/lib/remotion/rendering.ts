export const WEB_RENDER_DELAY_RENDER_TIMEOUT_MS = 120_000;

const FRAME_EXTRACTION_DELAY_RENDER_RE =
  /delayRender.+Extracting frame at time/i;
const FRAME_EXTRACTION_TIMEOUT_RE = /Timeout while extracting frame at time/i;
const FLUSHING_ERROR_RE = /\bflushing error\b/i;
const WEB_CODEC_PIPELINE_ERROR_RE =
  /\b(video|audio)?\s?(encoder|decoder)\b|webcodec|mux|demux/i;

export function getFriendlyWebRenderErrorMessage(error: unknown): string {
  const message =
    error instanceof Error ? error.message : String(error || "").trim();

  if (
    FRAME_EXTRACTION_DELAY_RENDER_RE.test(message) ||
    FRAME_EXTRACTION_TIMEOUT_RE.test(message)
  ) {
    return "浏览器读取原视频帧超时。请保持当前页面在前台后重试；如果仍失败，请改用 Chrome / Edge，重新选择原始视频，或先将视频转成 H.264 MP4 后再导出。";
  }

  if (FLUSHING_ERROR_RE.test(message) || WEB_CODEC_PIPELINE_ERROR_RE.test(message)) {
    return "浏览器本地视频编码器初始化失败。请刷新页面后重试；如果仍失败，请改用最新版 Chrome，保持页面在前台，并优先使用 H.264/AAC 的 MP4 源视频。";
  }

  return message || "浏览器导出失败，请重试。";
}
