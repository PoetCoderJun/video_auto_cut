import type {RenderCaption, WebRenderConfig} from "../../lib/api";

function normalizeSrtTimeComponent(value: number): [seconds: number, milliseconds: number] {
  const wholeSeconds = Math.trunc(value);
  let milliseconds = Math.round((value - wholeSeconds) * 1000);
  let seconds = wholeSeconds;
  if (milliseconds >= 1000) {
    seconds += 1;
    milliseconds -= 1000;
  }
  return [seconds, milliseconds];
}

export function formatSrtTimestamp(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "00:00:00,000";
  }
  const [normalizedSeconds, milliseconds] = normalizeSrtTimeComponent(seconds);
  const hours = Math.floor(normalizedSeconds / 3600);
  const minutes = Math.floor((normalizedSeconds % 3600) / 60);
  const secs = normalizedSeconds % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")},${String(milliseconds).padStart(3, "0")}`;
}

export function buildSrtFromRenderCaptions(captions: RenderCaption[]): string {
  const blocks: string[] = [];
  let index = 1;

  for (const caption of captions) {
    const start = Number(caption.start);
    const end = Number(caption.end);
    const text = String(caption.text || "")
      .replace(/\r\n/g, "\n")
      .trim();

    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || !text) {
      continue;
    }

    blocks.push(
      `${index}\n${formatSrtTimestamp(start)} --> ${formatSrtTimestamp(end)}\n${text}`,
    );
    index += 1;
  }

  return blocks.length > 0 ? `${blocks.join("\n\n")}\n` : "";
}

export function getSubtitleExportFileName(outputName: string): string {
  const baseName = String(outputName || "output")
    .trim()
    .replace(/\.(mp4|webm)$/i, "");
  return `${baseName || "output"}.txt`;
}

export function buildSrtDownloadFromRenderConfig(config: WebRenderConfig): {
  content: string;
  fileName: string;
} {
  const captions = Array.isArray(config.input_props?.captions)
    ? config.input_props.captions
    : [];
  const content = buildSrtFromRenderCaptions(captions);
  if (!content) {
    throw new Error("当前任务暂无可导出的最终字幕，请稍后重试。");
  }
  return {
    content,
    fileName: getSubtitleExportFileName(config.output_name),
  };
}
