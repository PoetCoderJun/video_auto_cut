import type {RenderMeta, WebRenderConfig} from "./api";

const APP_EXPORTED_VIDEO_NAME_RE = /^job_[a-z0-9]+_export\.(mp4|webm)$/i;

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "00:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

function getExpectedSourceDuration(config: WebRenderConfig): number {
  return config.input_props.segments.reduce((max, segment) => {
    const end = Number(segment.end);
    if (!Number.isFinite(end) || end <= max) return max;
    return end;
  }, 0);
}

function getRenderedDuration(config: WebRenderConfig): number {
  return config.input_props.segments.reduce((sum, segment) => {
    const start = Number(segment.start);
    const end = Number(segment.end);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return sum;
    return sum + (end - start);
  }, 0);
}

export function isLikelyAppExportFileName(fileName: string | null | undefined): boolean {
  return APP_EXPORTED_VIDEO_NAME_RE.test(String(fileName || "").trim());
}

export function getLikelyAppExportFileMessage(fileName: string | null | undefined): string {
  const normalizedName = String(fileName || "当前视频").trim() || "当前视频";
  return `检测到文件「${normalizedName}」像是本系统之前导出的成片，它通常已经带有字幕、章节条或进度条。继续处理会再次叠加，导致你现在这种错位/重影。请改传原始素材。`;
}

export function getSourceVideoMismatchMessage(
  fileName: string | null | undefined,
  meta: RenderMeta,
  config: WebRenderConfig
): string | null {
  if (isLikelyAppExportFileName(fileName)) {
    return getLikelyAppExportFileMessage(fileName);
  }

  const sourceDuration = Number(meta.duration_sec);
  const expectedSourceDuration = getExpectedSourceDuration(config);
  if (!Number.isFinite(sourceDuration) || !Number.isFinite(expectedSourceDuration) || expectedSourceDuration <= 0) {
    return null;
  }

  const allowedGap = Math.max(1.2, expectedSourceDuration * 0.03);
  if (sourceDuration + allowedGap >= expectedSourceDuration) {
    return null;
  }

  const renderedDuration = getRenderedDuration(config);
  const looksLikeRenderedCut =
    Number.isFinite(renderedDuration) &&
    renderedDuration > 0 &&
    Math.abs(sourceDuration - renderedDuration) <= Math.max(1.2, renderedDuration * 0.08);

  if (looksLikeRenderedCut) {
    return `当前本地视频时长是 ${formatDuration(sourceDuration)}，但这个任务对应的原始时间轴至少到 ${formatDuration(expectedSourceDuration)}。它更像一份已经剪好的导出成片，而不是原始素材；继续导出会把字幕和条幅再叠一层。请重新上传原视频。`;
  }

  return `当前本地视频时长是 ${formatDuration(sourceDuration)}，但这个任务的原始时间轴至少到 ${formatDuration(expectedSourceDuration)}，两者不匹配。为避免导出出错，已阻止本次导出；请重新上传与该任务对应的原始视频。`;
}
