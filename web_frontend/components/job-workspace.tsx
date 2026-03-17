"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiClientError,
  Chapter,
  createJob,
  Job,
  RenderMeta,
  Step1Line,
  WebRenderConfig,
  confirmStep1,
  confirmStep2,
  getJob,
  getStep1,
  getStep2,
  getWebRenderConfigWithMeta,
  markRenderSucceeded,
  runStep1,
  runStep2,
  uploadAudioDirectToOss,
} from "../lib/api";
import { extractAudioForAsr } from "../lib/audio-extract";
import { isUnsupportedMobileUploadDevice } from "../lib/device";
import { tryParseFpsWithMediaInfo } from "../lib/media-metadata";
import {
  loadCachedJobSourceVideo,
  saveCachedJobSourceVideo,
} from "../lib/video-cache";
import {
  mergeJobSnapshot,
  mergeJobStatus,
  shouldPollJobStatus,
} from "../lib/job-status";
import { STATUS } from "../lib/workflow";
import {
  StitchVideoWeb,
  type SubtitleTheme,
} from "../lib/remotion/stitch-video-web";
import {
  OVERLAY_SCALE_LIMITS,
  type OverlayScaleControls,
  type ProgressLabelMode,
} from "../lib/remotion/overlay-controls";
import ExportFramePreview from "./export-frame-preview";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  Loader2,
  UploadCloud,
  CheckCircle2,
  ArrowRight,
  Download,
  FileVideo,
  GripVertical,
  X,
} from "lucide-react";

function autoResize(target: HTMLTextAreaElement) {
  target.style.height = "auto";
  target.style.height = `${target.scrollHeight}px`;
}

function triggerFileDownload(url: string, fileName: string) {
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

const STEPS = [
  { id: 1, label: "上传视频" },
  { id: 2, label: "剪辑字幕" },
  { id: 3, label: "确认章节" },
  { id: 4, label: "导出视频" },
];

const CHAPTER_COLORS = [
  "border-l-blue-500 bg-blue-50/50",
  "border-l-emerald-500 bg-emerald-50/50",
  "border-l-amber-500 bg-amber-50/50",
  "border-l-red-500 bg-red-50/50",
  "border-l-violet-500 bg-violet-50/50",
  "border-l-pink-500 bg-pink-50/50",
];

const CHAPTER_BADGE_COLORS = [
  "bg-blue-500",
  "bg-emerald-500",
  "bg-amber-500",
  "bg-red-500",
  "bg-violet-500",
  "bg-pink-500",
];

const SUPPORTED_UPLOAD_EXTENSIONS = [
  ".mp4",
  ".mov",
  ".mkv",
  ".webm",
  ".m4v",
  ".ts",
  ".m2ts",
  ".mts",
];
const SUPPORTED_UPLOAD_ACCEPT = SUPPORTED_UPLOAD_EXTENSIONS.join(",");
const SUBTITLE_THEME_OPTIONS: Array<{ value: SubtitleTheme; label: string }> = [
  { value: "box-white-on-black", label: "黑底白字" },
  { value: "box-black-on-white", label: "白底黑字" },
  { value: "text-white", label: "白色" },
  { value: "text-black", label: "黑色" },
];
const PROGRESS_LABEL_MODE_OPTIONS: Array<{ value: ProgressLabelMode; label: string }> = [
  { value: "auto", label: "自动" },
  { value: "double", label: "双行" },
  { value: "single", label: "单行" },
];
const MAX_VIDEO_DURATION_SEC = 10 * 60;
const MIN_STEP2_LINES_PER_CHAPTER = 3;
const STEP1_VISUAL_PROGRESS_BY_STAGE: Record<string, number> = {
  UPLOAD_COMPLETE: 8,
  STEP1_QUEUED: 12,
  TRANSCRIBING_AUDIO: 34,
  OPTIMIZING_TEXT: 56,
  REMOVING_REDUNDANT_LINES: 56,
  MERGING_SHORT_LINES: 72,
  POLISHING_EXPRESSION: 84,
  PREPARING_STEP1_REVIEW: 92,
  STEP1_READY: 100,
};

function getActiveStep(status: Job["status"]): number {
  switch (status) {
    case STATUS.CREATED:
    case STATUS.UPLOAD_READY:
      return 1;
    case STATUS.STEP1_RUNNING:
    case STATUS.STEP1_READY:
      return 2;
    case STATUS.STEP1_CONFIRMED:
    case STATUS.STEP2_RUNNING:
    case STATUS.STEP2_READY:
      return 3;
    case STATUS.STEP2_CONFIRMED:
    case STATUS.SUCCEEDED:
      return 4;
    default:
      return 1;
  }
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function formatDuration(seconds: number): string {
  if (!seconds || Number.isNaN(seconds)) return "00:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

async function resolveRenderMetaFromFile(file: File): Promise<RenderMeta> {
  const url = URL.createObjectURL(file);
  try {
    const meta = await new Promise<{
      width: number;
      height: number;
      duration: number;
    }>((resolve, reject) => {
      const video = document.createElement("video");
      video.preload = "metadata";
      video.muted = true;
      video.onloadedmetadata = () => {
        resolve({
          width: video.videoWidth,
          height: video.videoHeight,
          duration: video.duration,
        });
      };
      video.onerror = () =>
        reject(new Error("无法读取本地视频元数据，请重新选择文件。"));
      video.src = url;
    });

    const estimateFps = async (): Promise<number> => {
      const probeUrl = URL.createObjectURL(file);
      const video = document.createElement("video");
      video.muted = true;
      video.playsInline = true;
      video.preload = "auto";
      video.src = probeUrl;

      try {
        await video.play();
      } catch {
        URL.revokeObjectURL(probeUrl);
        return 30;
      }

      return await new Promise<number>((resolve) => {
        let firstMediaTime: number | null = null;
        let lastMediaTime: number | null = null;
        let frames = 0;
        const maxFrames = 45;
        const maxMs = 1200;
        const startAt = performance.now();

        const finish = () => {
          try {
            video.pause();
          } catch {
            // ignore
          }
          URL.revokeObjectURL(probeUrl);
          const dt =
            firstMediaTime !== null && lastMediaTime !== null
              ? lastMediaTime - firstMediaTime
              : 0;
          const fps = dt > 0 ? frames / dt : 0;
          if (Number.isFinite(fps) && fps > 1 && fps < 240) {
            resolve(Math.round(fps * 1000) / 1000);
          } else {
            resolve(30);
          }
        };

        const onFrame = (_now: number, frame: { mediaTime: number }) => {
          const t = typeof frame?.mediaTime === "number" ? frame.mediaTime : NaN;
          if (Number.isFinite(t)) {
            if (firstMediaTime === null) firstMediaTime = t;
            lastMediaTime = t;
            frames += 1;
          }

          if (frames >= maxFrames || performance.now() - startAt >= maxMs) {
            finish();
            return;
          }
          const requestCb = (video as any).requestVideoFrameCallback;
          if (typeof requestCb === "function") requestCb.call(video, onFrame);
          else finish();
        };

        const requestCb = (video as any).requestVideoFrameCallback;
        if (typeof requestCb === "function") requestCb.call(video, onFrame);
        else finish();
      });
    };

    const fps = (await tryParseFpsWithMediaInfo(file)) ?? (await estimateFps());
    return {
      width: meta.width,
      height: meta.height,
      duration_sec:
        typeof meta.duration === "number" && Number.isFinite(meta.duration)
          ? meta.duration
          : undefined,
      fps,
    };
  } finally {
    URL.revokeObjectURL(url);
  }
}

function getRandomPreviewTime(config: WebRenderConfig): number {
  const captionCandidates = config.input_props.captions
    .filter((caption) => caption.end > caption.start)
    .map((caption) => {
      const start = Number(caption.start);
      const end = Number(caption.end);
      return Math.max(start, Math.min(end - 0.08, start + (end - start) * 0.45));
    })
    .filter((value) => Number.isFinite(value) && value >= 0);

  if (captionCandidates.length > 0) {
    const index = Math.floor(Math.random() * captionCandidates.length);
    return captionCandidates[index];
  }

  const topicCandidates = config.input_props.topics
    .filter((topic) => topic.end > topic.start)
    .map((topic) => topic.start)
    .filter((value) => Number.isFinite(value) && value >= 0);

  if (topicCandidates.length > 0) {
    const index = Math.floor(Math.random() * topicCandidates.length);
    return topicCandidates[index];
  }

  const totalDuration = Math.max(
    1,
    config.input_props.captions.reduce((max, item) => Math.max(max, item.end), 0),
    config.input_props.topics.reduce((max, item) => Math.max(max, item.end), 0),
    config.input_props.segments.reduce(
      (sum, item) => sum + Math.max(0, item.end - item.start),
      0
    )
  );
  return totalDuration * (0.25 + Math.random() * 0.5);
}

function getOriginalDurationFromLines(lines: Step1Line[]): number {
  return lines.reduce((max, line) => {
    const end = Number(line.end);
    if (!Number.isFinite(end) || end <= max) return max;
    return end;
  }, 0);
}

function getEstimatedDurationFromLines(lines: Step1Line[]): number {
  const intervals = lines
    .filter((line) => !line.user_final_remove)
    .filter((line) => String(line.optimized_text || "").trim().length > 0)
    .map((line) => ({
      start: Number(line.start),
      end: Number(line.end),
    }))
    .filter(
      (line) =>
        Number.isFinite(line.start) &&
        Number.isFinite(line.end) &&
        line.end > line.start
    )
    .sort((a, b) => a.start - b.start);

  if (intervals.length === 0) {
    return 0;
  }

  let total = 0;
  let currentStart = intervals[0].start;
  let currentEnd = intervals[0].end;

  for (let idx = 1; idx < intervals.length; idx += 1) {
    const item = intervals[idx];
    if (item.start <= currentEnd) {
      currentEnd = Math.max(currentEnd, item.end);
      continue;
    }
    total += currentEnd - currentStart;
    currentStart = item.start;
    currentEnd = item.end;
  }

  total += currentEnd - currentStart;
  return Math.max(0, total);
}

function areStep1LinesEqual(left: Step1Line[], right: Step1Line[]): boolean {
  if (left === right) return true;
  if (left.length !== right.length) return false;
  for (let index = 0; index < left.length; index += 1) {
    const a = left[index];
    const b = right[index];
    if (
      a.line_id !== b.line_id ||
      a.start !== b.start ||
      a.end !== b.end ||
      a.original_text !== b.original_text ||
      a.optimized_text !== b.optimized_text ||
      a.ai_suggest_remove !== b.ai_suggest_remove ||
      a.user_final_remove !== b.user_final_remove
    ) {
      return false;
    }
  }
  return true;
}

function getStep1PreviewLines(
  lines: Step1Line[]
): Array<{ time: string; text: string; removed: boolean }> {
  const visible = lines
    .map((line) => {
      const removed = Boolean(line.user_final_remove);
      const text = String(line.optimized_text || line.original_text || "").trim();
      const resolvedText = text || (removed ? "<No Speech>" : "");
      return {
        time: formatDuration(line.start),
        text: resolvedText,
        removed,
      };
    })
    .filter((line) => line.text.length > 0);

  const previewCount: number = 14;
  if (visible.length <= previewCount) {
    return visible;
  }

  const lastIndex = visible.length - 1;
  const sampledIndexes = new Set<number>();
  for (let index = 0; index < visible.length; index += 1) {
    if (visible[index].removed) {
      sampledIndexes.add(index);
      if (sampledIndexes.size >= previewCount) {
        break;
      }
    }
  }
  for (let index = 0; index < previewCount; index += 1) {
    const ratio = previewCount === 1 ? 0 : index / (previewCount - 1);
    sampledIndexes.add(Math.round(ratio * lastIndex));
    if (sampledIndexes.size >= previewCount) {
      break;
    }
  }

  return Array.from(sampledIndexes)
    .sort((left, right) => left - right)
    .map((index) => visible[index]);
}

function getKeptStep1Lines(lines: Step1Line[]): Step1Line[] {
  return lines
    .filter((line) => !line.user_final_remove)
    .sort((a, b) => a.line_id - b.line_id);
}

function parseBlockRange(value: string): { start: number; end: number } | null {
  const raw = String(value || "").trim();
  if (!raw) return null;
  if (!raw.includes("-")) {
    const normalized = Number.parseInt(raw, 10);
    if (!Number.isFinite(normalized) || normalized < 1) return null;
    return { start: normalized, end: normalized };
  }
  const [startRaw, endRaw] = raw.split("-", 2);
  const start = Number.parseInt(startRaw.trim(), 10);
  const end = Number.parseInt(endRaw.trim(), 10);
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 1 || end < start) {
    return null;
  }
  return { start, end };
}

function formatBlockRange(start: number, end: number): string {
  return start === end ? String(start) : `${start}-${end}`;
}

function countBlockRangeLines(range: { start: number; end: number }): number {
  return range.end - range.start + 1;
}

function getChapterLinesFromRange(chapter: Chapter, keptLines: Step1Line[]): Step1Line[] {
  const parsed = parseBlockRange(chapter.block_range);
  if (!parsed) return [];
  return keptLines.slice(parsed.start - 1, parsed.end);
}

function findChapterIndexByPosition(chapters: Chapter[], position: number): number {
  return chapters.findIndex((chapter) => {
    const parsed = parseBlockRange(chapter.block_range);
    return Boolean(parsed && parsed.start <= position && position <= parsed.end);
  });
}

function moveAdjacentChapterRange(
  chapters: Chapter[],
  draggedPosition: number,
  targetChapterId: number
): { chapters: Chapter[]; error: string | null } {
  const sourceIndex = findChapterIndexByPosition(chapters, draggedPosition);
  const targetIndex = chapters.findIndex((chapter) => chapter.chapter_id === targetChapterId);
  if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) {
    return { chapters, error: null };
  }
  if (Math.abs(sourceIndex - targetIndex) !== 1) {
    return {
      chapters,
      error: "当前 block_range 模式只支持拖到相邻章节，以保持章节连续。",
    };
  }

  const sourceRange = parseBlockRange(chapters[sourceIndex].block_range);
  const targetRange = parseBlockRange(chapters[targetIndex].block_range);
  if (!sourceRange || !targetRange) {
    return { chapters, error: "章节范围无效，请刷新后重试。" };
  }
  if (countBlockRangeLines(sourceRange) <= MIN_STEP2_LINES_PER_CHAPTER) {
    return {
      chapters,
      error: `每个章节至少要保留 ${MIN_STEP2_LINES_PER_CHAPTER} 句字幕。`,
    };
  }

  const next = chapters.map((chapter) => ({ ...chapter }));
  if (sourceIndex < targetIndex) {
    if (draggedPosition < sourceRange.start || draggedPosition > sourceRange.end) {
      return { chapters, error: "拖拽位置无效，请重试。" };
    }
    next[sourceIndex].block_range = formatBlockRange(sourceRange.start, draggedPosition - 1);
    next[targetIndex].block_range = formatBlockRange(draggedPosition, targetRange.end);
    return { chapters: next, error: null };
  }

  if (draggedPosition < sourceRange.start || draggedPosition > sourceRange.end) {
    return { chapters, error: "拖拽位置无效，请重试。" };
  }
  next[targetIndex].block_range = formatBlockRange(targetRange.start, draggedPosition);
  next[sourceIndex].block_range = formatBlockRange(draggedPosition + 1, sourceRange.end);
  return { chapters: next, error: null };
}

function getStep1VisualProgress(job: Job): number {
  if (job.status === STATUS.STEP1_READY) {
    return 100;
  }

  const stageCode = String(job.stage?.code || "").trim();
  const stageProgress = STEP1_VISUAL_PROGRESS_BY_STAGE[stageCode];
  if (typeof stageProgress === "number") {
    return stageProgress;
  }

  if (
    job.status === STATUS.UPLOAD_READY ||
    job.status === STATUS.STEP1_RUNNING
  ) {
    const normalized = ((Math.max(30, Math.min(35, job.progress)) - 30) / 5) * 100;
    return clampPercent(
      Math.max(normalized, job.status === STATUS.UPLOAD_READY ? 8 : 24)
    );
  }

  return clampPercent(job.progress);
}

function shouldShowStep1SubtitlePreview(stageCode: string | null | undefined): boolean {
  switch (String(stageCode || "").trim()) {
    case "OPTIMIZING_TEXT":
    case "REMOVING_REDUNDANT_LINES":
    case "MERGING_SHORT_LINES":
    case "POLISHING_EXPRESSION":
    case "PREPARING_STEP1_REVIEW":
    case "STEP1_READY":
      return true;
    default:
      return false;
  }
}

function getStep1ProcessingNote(stageCode: string | null | undefined): string {
  switch (String(stageCode || "").trim()) {
    case "TRANSCRIBING_AUDIO":
      return "先生成初版字幕，完成后会继续自动处理。";
    case "OPTIMIZING_TEXT":
    case "REMOVING_REDUNDANT_LINES":
      return "正在筛掉口误、重复句和回头修正。";
    case "MERGING_SHORT_LINES":
      return "正在把相邻短句合成更完整的句子。";
    case "POLISHING_EXPRESSION":
      return "正在按上下文润色字幕，让表达更自然。";
    case "PREPARING_STEP1_REVIEW":
      return "正在整理成可编辑字幕。";
    case "STEP1_READY":
      return "字幕已经整理完成，正在进入确认页面。";
    default:
      return "任务已启动，正在进入字幕处理流程。";
  }
}

function Step1ProcessingState({
  job,
  lines,
  busy,
  autoStep1Triggered,
  onRetry,
}: {
  job: Job;
  lines: Step1Line[];
  busy: boolean;
  autoStep1Triggered: boolean;
  onRetry: () => void;
}) {
  const visualProgress = getStep1VisualProgress(job);
  const previewLines = useMemo(() => getStep1PreviewLines(lines), [lines]);
  const showSubtitlePreview =
    shouldShowStep1SubtitlePreview(job.stage?.code) && previewLines.length > 0;

  return (
    <div className="mx-auto max-w-5xl py-6 md:py-10">
      <div className="relative min-h-[560px] overflow-hidden rounded-[30px] border border-slate-200/80 bg-white shadow-[0_24px_80px_-40px_rgba(15,23,42,0.28)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.28),_rgba(248,250,252,0.06)_48%,_rgba(241,245,249,0.16))]" />
        <div className="absolute inset-0 px-6 py-6 md:px-10 md:py-8">
          {showSubtitlePreview ? (
            <div className="mx-auto flex max-w-4xl flex-col gap-4 opacity-[0.96] blur-[0.2px]">
              {previewLines.map((line, index) => (
                <div
                  key={`${line.time}-${index}`}
                  className="flex items-start gap-3"
                >
                  <span className="mt-[2px] w-16 shrink-0 select-none font-mono text-[12px] leading-[1.7] text-[#94a3b8]">
                    {line.time}
                  </span>
                  <div
                    className={cn(
                      "min-w-0 flex-1 text-[15px] leading-[1.7]",
                      line.removed
                        ? "text-[#94a3b8] line-through"
                        : "text-[#334155]"
                    )}
                  >
                    {line.text}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mx-auto flex h-full max-w-4xl flex-col justify-center gap-5 opacity-70">
              {[0, 1, 2, 3, 4, 5].map((index) => (
                <div
                  key={index}
                  className="h-8 rounded-2xl bg-[linear-gradient(90deg,rgba(226,232,240,0.6),rgba(241,245,249,0.92),rgba(226,232,240,0.5))]"
                />
              ))}
            </div>
          )}
        </div>
        <div className="absolute inset-0 bg-white/8 backdrop-blur-[0.5px]" />

        <div className="relative z-10 flex min-h-[560px] items-center justify-center p-6">
          <div className="relative w-full max-w-[340px] overflow-hidden rounded-[22px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.88),rgba(244,248,255,0.92))] px-4 py-5 text-center shadow-[0_20px_45px_-28px_rgba(37,99,235,0.28)] backdrop-blur-2xl md:max-w-[360px]">
            <div className="pointer-events-none absolute inset-x-8 top-0 h-12 rounded-full bg-[rgba(125,170,255,0.18)] blur-xl" />
            <div className="pointer-events-none absolute inset-x-10 bottom-0 h-10 rounded-full bg-[rgba(56,189,248,0.08)] blur-xl" />
            <div className="relative mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-[rgba(148,163,184,0.24)] bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(239,246,255,0.96))] text-[#0f172a] shadow-[0_10px_24px_-18px_rgba(37,99,235,0.38)]">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>

            <h2 className="relative mt-3 text-[17px] font-semibold tracking-tight text-slate-900 md:text-[19px]">
              {job.stage?.message || "正在提取字幕"}
            </h2>
            <p className="relative mx-auto mt-1.5 max-w-[240px] text-[12px] leading-5 text-slate-500">
              {getStep1ProcessingNote(job.stage?.code)}
            </p>

            <Progress
              value={visualProgress}
              className="relative mx-auto mt-3 h-1 w-20 bg-slate-200/80"
              indicatorClassName="bg-gradient-to-r from-[#60a5fa] via-[#2563eb] to-[#0f172a]"
            />

            {job.status === STATUS.UPLOAD_READY && !busy && autoStep1Triggered && (
              <Button
                type="button"
                variant="outline"
                className="relative mt-4 h-8 rounded-full px-3 text-xs"
                onClick={onRetry}
              >
                重新尝试启动字幕任务
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function JobWorkspace({
  jobId,
  onBackHome,
  onSwitchJob,
}: {
  jobId: string;
  onBackHome?: () => void;
  onSwitchJob?: (jobId: string) => void;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [lines, setLines] = useState<Step1Line[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const keptLines = useMemo(() => getKeptStep1Lines(lines), [lines]);
  const keptLinePositionById = useMemo(
    () => new Map(keptLines.map((line, index) => [line.line_id, index + 1] as const)),
    [keptLines]
  );
  const [error, setError] = useState("");
  const [renderNote, setRenderNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [renderBusy, setRenderBusy] = useState(false);
  const [renderProgress, setRenderProgress] = useState(0);
  const [renderDownloadUrl, setRenderDownloadUrl] = useState<string | null>(
    null
  );
  const [renderFileName, setRenderFileName] = useState("output.mp4");
  const [renderConfig, setRenderConfig] = useState<WebRenderConfig | null>(null);
  const [renderConfigBusy, setRenderConfigBusy] = useState(false);
  const [renderSetupError, setRenderSetupError] = useState("");
  const [previewTimeSec, setPreviewTimeSec] = useState(0);
  const [subtitleTheme, setSubtitleTheme] = useState<SubtitleTheme>(
    "box-white-on-black"
  );
  const [overlayControls, setOverlayControls] = useState<OverlayScaleControls>({
    subtitleScale: OVERLAY_SCALE_LIMITS.subtitle.defaultValue,
    progressScale: OVERLAY_SCALE_LIMITS.progress.defaultValue,
    chapterScale: OVERLAY_SCALE_LIMITS.chapter.defaultValue,
    progressLabelMode: "auto",
  });
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [draggedLineId, setDraggedLineId] = useState<number | null>(null);
  const [uploadStageMessage, setUploadStageMessage] = useState("");
  const [autoStep1Triggered, setAutoStep1Triggered] = useState(false);
  const [autoStep2Triggered, setAutoStep2Triggered] = useState(false);
  const [step1ReadyHandoffActive, setStep1ReadyHandoffActive] = useState(false);
  const [step1ReadyLinesLoaded, setStep1ReadyLinesLoaded] = useState(false);
  const [mobileUploadBlocked, setMobileUploadBlocked] = useState(false);

  useEffect(() => {
    setMobileUploadBlocked(isUnsupportedMobileUploadDevice());
  }, []);

  const showMobileUploadError = useCallback(() => {
    setError("移动端暂不支持上传视频，请在电脑浏览器使用（建议 Chrome）。");
  }, []);

  const refreshJob = useCallback(async () => {
    try {
      const next = await getJob(jobId);
      setJob((previous) => mergeJobSnapshot(previous, next));
      return next;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const isJobMissing =
        (err instanceof ApiClientError && err.code === "NOT_FOUND") ||
        message.includes("job not found");

      if (isJobMissing) {
        onBackHome?.();
      }
      throw err;
    }
  }, [jobId, onBackHome]);

  useEffect(() => {
    let active = true;
    refreshJob()
      .then(() => {
        if (!active) return;
        setError((prev) => (prev.startsWith("无法连接 API") ? "" : prev));
      })
      .catch((err) => {
        if (!active) return;
        const message = err instanceof Error ? err.message : String(err);
        if (
          (err instanceof ApiClientError && err.code === "NOT_FOUND") ||
          message.includes("job not found")
        ) {
          setError("项目不存在或已被清理，已返回首页。");
          return;
        }
        if (
          (err instanceof ApiClientError && err.code === "UNAUTHORIZED") ||
          message.includes("请先登录") ||
          message.includes("登录状态无效")
        ) {
          setError("登录状态已失效，请重新登录。");
          return;
        }
        setError(message.includes("无法连接 API") ? message : "无法连接 API，请确认后端服务正在运行。");
      });
    return () => {
      active = false;
    };
  }, [refreshJob]);

  useEffect(() => {
    if (!job) return;
    if (
      job.status === STATUS.STEP1_READY ||
      job.status === STATUS.STEP2_READY
    ) {
      getStep1(jobId)
        .then((nextLines) => {
          setLines((previous) =>
            areStep1LinesEqual(previous, nextLines) ? previous : nextLines
          );
          if (job.status === STATUS.STEP1_READY) {
            setStep1ReadyLinesLoaded(true);
          }
        })
        .catch(() => undefined);
    }
  }, [job?.status, jobId]);

  useEffect(() => {
    if (!job || job.status !== STATUS.STEP1_RUNNING) {
      return;
    }

    let cancelled = false;
    const pollStep1Lines = () => {
      getStep1(jobId)
        .then((nextLines) => {
          if (cancelled || nextLines.length === 0) return;
          setLines((previous) =>
            areStep1LinesEqual(previous, nextLines) ? previous : nextLines
          );
        })
        .catch(() => undefined);
    };

    pollStep1Lines();
    const intervalId = window.setInterval(pollStep1Lines, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [job?.status, job?.stage?.code, jobId]);

  useEffect(() => {
    if (!job || job.status !== STATUS.STEP1_READY) {
      setStep1ReadyHandoffActive(false);
      setStep1ReadyLinesLoaded(false);
      return;
    }
    setStep1ReadyHandoffActive(true);
    setStep1ReadyLinesLoaded(false);
  }, [job?.status, jobId]);

  useEffect(() => {
    if (
      !job ||
      job.status !== STATUS.STEP1_READY ||
      !step1ReadyHandoffActive ||
      !step1ReadyLinesLoaded
    ) {
      return;
    }

    const timerId = window.setTimeout(() => {
      setStep1ReadyHandoffActive(false);
    }, 900);
    return () => {
      window.clearTimeout(timerId);
    };
  }, [job?.status, step1ReadyHandoffActive, step1ReadyLinesLoaded]);

  useEffect(() => {
    if (!job) return;
    if (job.status === STATUS.STEP2_READY) {
      if (chapters.length === 0) {
        getStep2(jobId).then(setChapters).catch(() => undefined);
      }
    }
  }, [job, chapters.length, jobId]);

  useEffect(() => {
    return () => {
      if (renderDownloadUrl) {
        URL.revokeObjectURL(renderDownloadUrl);
      }
    };
  }, [renderDownloadUrl]);

  useEffect(() => {
    setRenderBusy(false);
    setRenderProgress(0);
    setRenderConfig(null);
    setRenderConfigBusy(false);
    setRenderSetupError("");
    setPreviewTimeSec(0);
    setJob(null);
    setLines([]);
    setChapters([]);
    setError("");
    setRenderNote("");
    setAutoStep1Triggered(false);
    setAutoStep2Triggered(false);
    setDraggedLineId(null);
    setRenderDownloadUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return null;
    });
    setRenderFileName("output.mp4");
    setSubtitleTheme("box-white-on-black");
    setOverlayControls({
      subtitleScale: OVERLAY_SCALE_LIMITS.subtitle.defaultValue,
      progressScale: OVERLAY_SCALE_LIMITS.progress.defaultValue,
      chapterScale: OVERLAY_SCALE_LIMITS.chapter.defaultValue,
      progressLabelMode: "auto",
    });
    setUploadStageMessage("");
  }, [jobId]);

  useEffect(() => {
    let active = true;
    loadCachedJobSourceVideo(jobId)
      .then((file) => {
        if (!active || !file) return;
        setSelectedFile((previous) => previous ?? file);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [jobId]);

  useEffect(() => {
    const exportReady =
      job?.status === STATUS.STEP2_CONFIRMED || job?.status === STATUS.SUCCEEDED;
    if (!exportReady) return;

    let cancelled = false;

    const prepareRenderPreview = async () => {
      setRenderConfigBusy(true);
      setRenderSetupError("");
      try {
        let sourceFile = selectedFile;
        if (!sourceFile) {
          sourceFile = await loadCachedJobSourceVideo(jobId);
          if (sourceFile && !cancelled) {
            setSelectedFile(sourceFile);
          }
        }
        if (!sourceFile) {
          throw new Error("当前会话缺少本地原始视频，请先重新上传后再导出。");
        }

        const meta = await resolveRenderMetaFromFile(sourceFile);
        if (cancelled) return;
        const config = await getWebRenderConfigWithMeta(jobId, meta);
        if (cancelled) return;
        setRenderConfig(config);
        setPreviewTimeSec((previous) => {
          const totalDuration = Math.max(
            1,
            config.input_props.captions.reduce((max, item) => Math.max(max, item.end), 0),
            config.input_props.topics.reduce((max, item) => Math.max(max, item.end), 0),
            config.input_props.segments.reduce(
              (sum, item) => sum + Math.max(0, item.end - item.start),
              0
            )
          );
          if (previous > 0 && previous < totalDuration) {
            return previous;
          }
          return getRandomPreviewTime(config);
        });
      } catch (err) {
        if (cancelled) return;
        setRenderConfig(null);
        setRenderSetupError(
          err instanceof Error ? err.message : "导出预览初始化失败，请重试。"
        );
      } finally {
        if (!cancelled) {
          setRenderConfigBusy(false);
        }
      }
    };

    void prepareRenderPreview();
    return () => {
      cancelled = true;
    };
  }, [job?.status, jobId, selectedFile]);

  const handleUpload = useCallback(
    async (file: File) => {
      if (mobileUploadBlocked) {
        showMobileUploadError();
        return;
      }
      setError("");
      const lowerName = file.name.toLowerCase();
      const hasSupportedExt = SUPPORTED_UPLOAD_EXTENSIONS.some((ext) =>
        lowerName.endsWith(ext)
      );
      if (!hasSupportedExt) {
        setError(
          "这个文件格式暂不支持。请上传 MP4、MOV、MKV、WebM、M4V、TS、M2TS 或 MTS 视频。"
        );
        return;
      }
      const durationSec = await new Promise<number>((resolve) => {
        const url = URL.createObjectURL(file);
        const video = document.createElement("video");
        video.preload = "metadata";
        video.onloadedmetadata = () => {
          URL.revokeObjectURL(url);
          resolve(video.duration);
        };
        video.onerror = () => {
          URL.revokeObjectURL(url);
          resolve(0);
        };
        video.src = url;
      });
      if (durationSec >= MAX_VIDEO_DURATION_SEC) {
        const mins = Math.floor(durationSec / 60);
        const secs = Math.round(durationSec % 60);
        setError(
          `视频时长 ${mins} 分 ${secs} 秒，已达到 10 分钟限制，请上传更短的视频。`
        );
        return;
      }
      setBusy(true);
      try {
        setUploadStageMessage("正在提取音频...");
        const nextJob = await createJob();
        const audioFile = await extractAudioForAsr(file);
        setUploadStageMessage("正在上传音频...");
        const uploadedJob = await uploadAudioDirectToOss(nextJob.job_id, audioFile);
        await saveCachedJobSourceVideo(nextJob.job_id, file).catch(() => undefined);
        onSwitchJob?.(nextJob.job_id);
        setJob((previous) => mergeJobSnapshot(previous, uploadedJob));
      } catch (err) {
        setError(err instanceof Error ? err.message : "音频提取或上传失败，请重试。");
      } finally {
        setUploadStageMessage("");
        setBusy(false);
      }
    },
    [mobileUploadBlocked, onSwitchJob, showMobileUploadError]
  );

  useEffect(() => {
    if (
      !job ||
      job.status !== STATUS.UPLOAD_READY ||
      autoStep1Triggered ||
      busy
    )
      return;

    let cancelled = false;
    setAutoStep1Triggered(true);
    setError("");
    setBusy(true);
    runStep1(jobId)
      .then((step1Result) => {
        if (cancelled) return;
        setJob((previous) => mergeJobSnapshot(previous, step1Result.job));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "字幕提取失败，请重试。");
      })
      .finally(() => {
        setBusy(false);
      });

    return () => {
      cancelled = true;
    };
  }, [job, autoStep1Triggered, jobId, busy]);

  const handleRetryStep1AutoRun = useCallback(() => {
    if (!job || job.status !== STATUS.UPLOAD_READY || busy) return;
    setError("");
    setAutoStep1Triggered(false);
  }, [job, busy]);

  useEffect(() => {
    if (
      !job ||
      job.status !== STATUS.STEP1_CONFIRMED ||
      autoStep2Triggered ||
      busy
    )
      return;

    let cancelled = false;
    setAutoStep2Triggered(true);
    setError("");
    setBusy(true);
    runStep2(jobId)
      .then((step2Result) => {
        if (cancelled) return;
        setJob((previous) => mergeJobSnapshot(previous, step2Result.job));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "章节生成失败，请重试。");
      })
      .finally(() => {
        setBusy(false);
      });

    return () => {
      cancelled = true;
    };
  }, [job, autoStep2Triggered, jobId, busy]);

  const handleRetryStep2AutoRun = useCallback(() => {
    if (!job || job.status !== STATUS.STEP1_CONFIRMED || busy) return;
    setError("");
    setAutoStep2Triggered(false);
  }, [job, busy]);

  useEffect(() => {
    if (!job) return;
    if (!shouldPollJobStatus(job.status)) return;

    const timer = setInterval(() => {
      refreshJob().catch(() => undefined);
    }, 2500);
    return () => {
      clearInterval(timer);
    };
  }, [job?.status, refreshJob]);

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (file) {
      if (mobileUploadBlocked) {
        showMobileUploadError();
        return;
      }
      setSelectedFile(file);
      void handleUpload(file);
    }
  };

  const handleConfirmStep1 = async () => {
    setError("");
    setBusy(true);
    try {
      const status = await confirmStep1(jobId, lines);
      setJob((previous) => mergeJobStatus(previous, status));
      const step2Result = await runStep2(jobId);
      setJob((previous) => mergeJobSnapshot(previous, step2Result.job));
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败，请重试。");
    } finally {
      setBusy(false);
    }
  };

  const handleConfirmStep2 = useCallback(async () => {
    if (chapters.length === 0) return;
    setError("");
    setBusy(true);
    try {
      await confirmStep1(jobId, lines);
      const normalizedChapters = chapters.map((chapter, index) => {
        const parsed = parseBlockRange(chapter.block_range);
        if (!parsed) {
          throw new Error(`第 ${index + 1} 章范围无效，请重新调整。`);
        }
        const chapterLines = keptLines.slice(parsed.start - 1, parsed.end);

        if (chapterLines.length === 0) {
          throw new Error(`第 ${index + 1} 章为空，请先拖入至少一句字幕。`);
        }
        if (keptLines.length >= MIN_STEP2_LINES_PER_CHAPTER && chapterLines.length < MIN_STEP2_LINES_PER_CHAPTER) {
          throw new Error(
            `第 ${index + 1} 章只有 ${chapterLines.length} 句，请至少保留 ${MIN_STEP2_LINES_PER_CHAPTER} 句字幕。`
          );
        }

        return {
          chapter_id: index + 1,
          title: String(chapter.title || "").trim() || `章节${index + 1}`,
          start: chapterLines[0].start,
          end: chapterLines[chapterLines.length - 1].end,
          block_range: formatBlockRange(parsed.start, parsed.end),
        };
      });

      const status = await confirmStep2(jobId, normalizedChapters);
      setJob((previous) => mergeJobStatus(previous, status));
    } catch (err) {
      setError(err instanceof Error ? err.message : "章节保存失败，请重试。");
    } finally {
      setBusy(false);
    }
  }, [chapters, jobId, keptLines, lines]);

  const updateChapter = useCallback((chapterId: number, patch: Partial<Chapter>) => {
    setChapters((previous) =>
      previous.map((chapter) =>
        chapter.chapter_id === chapterId ? { ...chapter, ...patch } : chapter
      )
    );
  }, []);

  const handleDragStart = useCallback((event: React.DragEvent, lineId: number) => {
    event.dataTransfer.setData("text/plain", lineId.toString());
    event.dataTransfer.effectAllowed = "move";
    setDraggedLineId(lineId);
  }, []);

  const handleDragEnd = useCallback(() => {
    setDraggedLineId(null);
  }, []);

  const handleDropOnLine = useCallback(
    (event: React.DragEvent, targetChapterId: number) => {
      event.preventDefault();
      setDraggedLineId(null);

      const lineIdStr = event.dataTransfer.getData("text/plain");
      if (!lineIdStr) return;
      const draggedId = parseInt(lineIdStr, 10);
      const draggedPosition = keptLinePositionById.get(draggedId);
      if (!draggedPosition) return;

      setChapters((previous) => {
        const moved = moveAdjacentChapterRange(previous, draggedPosition, targetChapterId);
        if (moved.error) {
          setError(moved.error);
          return previous;
        }
        return moved.chapters;
      });
    },
    [keptLinePositionById]
  );

  const handleStartRender = useCallback(async () => {
    setError("");
    setRenderNote("");
    setRenderSetupError("");
    setRenderBusy(true);
    setRenderProgress(0);
    setRenderDownloadUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return null;
    });
    let sourceObjectUrl: string | null = null;
    try {
      let sourceFile = selectedFile;
      if (!sourceFile) {
        sourceFile = await loadCachedJobSourceVideo(jobId);
        if (sourceFile) setSelectedFile(sourceFile);
      }
      if (!sourceFile) {
        throw new Error("当前会话缺少本地原始视频，请先重新上传后再导出。");
      }
      const config =
        renderConfig ??
        (await getWebRenderConfigWithMeta(
          jobId,
          await resolveRenderMetaFromFile(sourceFile)
        ));
      setRenderConfig((previous) => previous ?? config);
      sourceObjectUrl = URL.createObjectURL(sourceFile);
      const inputProps = {
        ...config.input_props,
        src: sourceObjectUrl,
        subtitleTheme,
        subtitleScale: overlayControls.subtitleScale,
        progressScale: overlayControls.progressScale,
        chapterScale: overlayControls.chapterScale,
        progressLabelMode: overlayControls.progressLabelMode,
      };
      const composition = {
        ...config.composition,
        component: StitchVideoWeb,
        defaultProps: inputProps,
      };

      if (!window.isSecureContext) {
        throw new Error(
          "当前页面不在安全上下文中（需要 HTTPS 或 localhost），浏览器禁用了视频解码器 (VideoDecoder)，无法导出视频。请通过 HTTPS 访问本站，或联系管理员配置 SSL 证书。"
        );
      }

      const { renderMediaOnWeb, getEncodableAudioCodecs } = await import("@remotion/web-renderer");

      // Determine the best available container+codec for this browser.
      // On non-cross-origin-isolated pages (missing COOP/COEP headers), audio
      // encoders are restricted by the browser. We probe MP4 first, then WebM,
      // and as a last resort render muted (no audio) inside MP4 so the export
      // never hard-crashes.
      const mp4AudioCodecs = await getEncodableAudioCodecs("mp4");
      const webmAudioCodecs = await getEncodableAudioCodecs("webm");
      const hasMp4Audio = mp4AudioCodecs.length > 0;
      const hasWebmAudio = webmAudioCodecs.length > 0;

      type WebRendererVideoCodec = "h264" | "vp8" | "vp9" | "h265" | "av1";
      let container: "mp4" | "webm" = "mp4";
      let videoCodec: WebRendererVideoCodec = "h264";
      let muted = false;

      if (hasMp4Audio) {
        container = "mp4";
        videoCodec = "h264";
      } else if (hasWebmAudio) {
        container = "webm";
        videoCodec = "vp8";
      } else {
        // Neither container can encode audio — render muted and warn the user.
        // The proper fix is to deploy COOP/COEP response headers so the page
        // becomes cross-origin isolated (window.crossOriginIsolated === true).
        container = "mp4";
        videoCodec = "h264";
        muted = true;
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const renderOptions: Parameters<typeof renderMediaOnWeb>[0] = {
        composition: composition as any,
        inputProps,
        container,
        videoCodec,
        videoBitrate: "high",
        ...(muted ? { muted: true } : {}),
        onProgress: (progress) => {
          const totalFrames = Math.max(
            1,
            Number(config.composition.durationInFrames) || 1
          );
          const doneFrames =
            typeof progress.encodedFrames === "number" &&
            Number.isFinite(progress.encodedFrames)
              ? progress.encodedFrames
              : progress.renderedFrames;
          setRenderProgress((previous) =>
            Math.max(previous, clampPercent((doneFrames / totalFrames) * 100))
          );
        },
      };

      // Try the probed container first; if rendering itself reports no audio
      // codec (browser capability detection can lag behind actual support),
      // retry once with muted=true so the user always gets a file.
      let result: Awaited<ReturnType<typeof renderMediaOnWeb>>;
      try {
        result = await renderMediaOnWeb(renderOptions);
      } catch (renderErr) {
        const msg = renderErr instanceof Error ? renderErr.message : String(renderErr);
        if (msg.includes("No audio codec can be encoded")) {
          result = await renderMediaOnWeb({ ...renderOptions, muted: true });
          muted = true;
        } else {
          throw renderErr;
        }
      }

      const baseName = (config.output_name || "output").replace(/\.(mp4|webm)$/i, "");
      const outputName = `${baseName}.${container}`;
      if (muted) {
        setRenderNote("导出成功，但当前浏览器环境不支持音频编码，导出文件无声音。建议使用 Chrome / Edge 浏览器，或联系管理员确认服务器已配置 COOP/COEP 响应头。");
      }
      setRenderFileName(outputName);
      const blob = await result.getBlob();
      const objectUrl = URL.createObjectURL(blob);
      setRenderDownloadUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return objectUrl;
      });
      triggerFileDownload(objectUrl, outputName);
      setRenderProgress(100);
      try {
        const completion = await markRenderSucceeded(jobId);
        setJob((previous) => mergeJobSnapshot(previous, completion.job));
      } catch (syncErr) {
        const message =
          syncErr instanceof Error ? syncErr.message : "服务端确认失败，请刷新后重试。";
        setError(`视频已导出，但服务端确认失败：${message}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "浏览器导出失败，请重试。");
    } finally {
      if (sourceObjectUrl) {
        URL.revokeObjectURL(sourceObjectUrl);
      }
      setRenderBusy(false);
    }
  }, [
    jobId,
    overlayControls.progressLabelMode,
    overlayControls.progressScale,
    overlayControls.chapterScale,
    overlayControls.subtitleScale,
    renderConfig,
    selectedFile,
    subtitleTheme,
  ]);

  useEffect(() => {
    if (renderBusy) return;
    setRenderDownloadUrl((previous) => {
      if (!previous) return previous;
      URL.revokeObjectURL(previous);
      return null;
    });
    setRenderProgress(0);
  }, [
    overlayControls.progressLabelMode,
    overlayControls.progressScale,
    overlayControls.chapterScale,
    overlayControls.subtitleScale,
    subtitleTheme,
  ]);

  const updateLine = (lineId: number, patch: Partial<Step1Line>) => {
    setLines((prev) =>
      prev.map((line) => (line.line_id === lineId ? { ...line, ...patch } : line))
    );
  };

  const { originalDuration, estimatedDuration } = useMemo(() => {
    return {
      originalDuration: getOriginalDurationFromLines(lines),
      estimatedDuration: getEstimatedDurationFromLines(lines),
    };
  }, [lines]);

  if (!job) {
    return (
      <main className="container mx-auto flex h-[50vh] flex-col items-center justify-center gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-muted-foreground">正在加载项目数据...</p>
      </main>
    );
  }

  const activeStep = getActiveStep(job.status);
  return (
    <main className="container mx-auto max-w-6xl px-4 py-8">
      {/* Stepper */}
      <div className="mb-12 border-b pb-8">
        <div className="flex flex-wrap items-center justify-center gap-4 md:justify-between">
          <div className="flex flex-wrap items-center gap-2 md:gap-4">
            {STEPS.map((step, idx) => {
              const isCompleted =
                step.id < activeStep ||
                (step.id === 4 && job.status === STATUS.SUCCEEDED);
              const isActive =
                step.id === activeStep && job.status !== STATUS.SUCCEEDED;
              return (
                <div key={step.id} className="flex items-center gap-2 md:gap-4">
                  <div
                    className={cn(
                      "flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-primary text-primary-foreground"
                        : isCompleted
                        ? "bg-muted text-foreground"
                        : "text-muted-foreground opacity-50"
                    )}
                  >
                    <div
                      className={cn(
                        "flex h-5 w-5 items-center justify-center rounded-full border text-[10px]",
                        isActive
                          ? "border-primary-foreground"
                          : "border-current"
                      )}
                    >
                      {isCompleted ? <CheckCircle2 className="h-3 w-3" /> : step.id}
                    </div>
                    <span className="hidden sm:inline">{step.label}</span>
                  </div>
                  {idx < STEPS.length - 1 && (
                    <div className="text-muted-foreground/30">›</div>
                  )}
                </div>
              );
            })}
          </div>
          {onBackHome && (
            <Button type="button" variant="ghost" size="sm" onClick={onBackHome}>
              重新上传
            </Button>
          )}
        </div>
      </div>

      {(job.error || error) && (
        <div className="mb-6 rounded-md bg-destructive/10 p-4 text-sm font-medium text-destructive border border-destructive/20">
          {job.error?.message || error}
        </div>
      )}

      {renderNote && (
        <div className="mb-6 rounded-md bg-amber-50 p-4 text-sm font-medium text-amber-800 border border-amber-200">
          {renderNote}
        </div>
      )}

      {/* Step 1: Upload */}
      {job.status === STATUS.CREATED && (
        <Card className="mx-auto max-w-xl text-center">
          <CardHeader>
            <CardTitle>上传原始视频</CardTitle>
            <CardDescription>
              请选择您要剪辑的视频文件。支持 MP4, MOV, MKV 等格式。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div
              onClick={() => {
                if (mobileUploadBlocked) showMobileUploadError();
              }}
              className={cn(
                "relative group w-full rounded-xl border-2 border-dashed border-muted-foreground/25 bg-muted/50 p-10 transition-all hover:border-primary/50 hover:bg-muted",
                selectedFile && "border-primary bg-primary/5",
                busy || mobileUploadBlocked
                  ? "opacity-70 cursor-not-allowed"
                  : "cursor-pointer"
              )}
            >
              <input
                type="file"
                accept={SUPPORTED_UPLOAD_ACCEPT}
                onChange={onFileChange}
                disabled={busy || mobileUploadBlocked}
                className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
              />
              <div className="flex flex-col items-center justify-center gap-4">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-background shadow-sm">
                  {busy ? (
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                  ) : (
                    <UploadCloud className="h-8 w-8 text-primary" />
                  )}
                </div>
                <div className="space-y-1">
                  <h3 className="font-semibold text-lg text-foreground">
                    {busy
                      ? uploadStageMessage || "正在上传..."
                      : mobileUploadBlocked
                      ? "移动端暂不支持上传"
                      : selectedFile
                      ? selectedFile.name
                      : "点击或拖拽上传视频"}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {mobileUploadBlocked
                      ? "请在电脑浏览器使用，建议 Chrome"
                      : busy
                      ? "请保持页面开启，我们会自动继续处理。"
                      : "AI 将自动提取字幕并进行智能分析"}
                  </p>
                </div>
              </div>
            </div>
            {mobileUploadBlocked && (
              <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm font-medium text-amber-800">
                移动端暂不支持上传视频，请在电脑浏览器使用（建议 Chrome）。
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Loading States */}
      {(job.status === STATUS.UPLOAD_READY ||
        job.status === STATUS.STEP1_RUNNING ||
        (job.status === STATUS.STEP1_READY && step1ReadyHandoffActive)) && (
        <Step1ProcessingState
          job={job}
          lines={lines}
          busy={busy}
          autoStep1Triggered={autoStep1Triggered}
          onRetry={handleRetryStep1AutoRun}
        />
      )}

      {(job.status === STATUS.STEP1_CONFIRMED ||
        job.status === STATUS.STEP2_RUNNING) && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Loader2 className="mb-4 h-12 w-12 animate-spin text-primary" />
          <h2 className="text-xl font-semibold">
            {job.stage?.message || "正在生成章节"}
          </h2>
          <p className="text-muted-foreground">
            AI 正在整理章节标题和边界，完成后会进入可编辑的章节确认页。
          </p>
          {job.status === STATUS.STEP1_CONFIRMED && !busy && autoStep2Triggered && (
            <Button
              type="button"
              variant="outline"
              className="mt-4"
              onClick={handleRetryStep2AutoRun}
            >
              重新尝试启动章节任务
            </Button>
          )}
        </div>
      )}

      {/* Step 2: Edit Subtitles */}
      {job.status === STATUS.STEP1_READY && !step1ReadyHandoffActive && (
        <div className="space-y-8">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold tracking-tight">用字幕编辑视频</h2>
              <p className="text-muted-foreground">
                直接修改字幕，点击句尾“×”可剔除该句。
              </p>
            </div>
            <div className="hidden md:block">
              <Badge variant="outline" className="text-sm">
                共 {lines.length} 行字幕
              </Badge>
            </div>
          </div>

          <div className="relative min-h-[500px] w-full rounded-md bg-white border border-[#e2e8f0] shadow-sm py-12 px-8 md:px-16 overflow-hidden mt-6">
            <div className="max-w-3xl mx-auto flex flex-col gap-[6px]">
              {lines.map((line) => {
                const isRemoved = line.user_final_remove;
                const isNoSpeech = !line.optimized_text || line.optimized_text.trim() === "";
                const lineTime = formatDuration(Number(line.start) || 0);
                
                return (
                  <div 
                    key={line.line_id} 
                    className="group relative flex items-start gap-3"
                  >
                    <span className="mt-[2px] select-none font-mono text-[12px] leading-[1.7] text-[#94a3b8]">
                      {lineTime}
                    </span>
                    <div className="flex-1 min-w-0">
                      {isRemoved ? (
                        <div
                          className="text-[12px] text-[#94a3b8] line-through cursor-pointer select-none py-[2px]"
                          onClick={() => updateLine(line.line_id, { user_final_remove: false })}
                          title="点击恢复此行"
                        >
                          {isNoSpeech ? "<No Speech>" : line.optimized_text}
                        </div>
                      ) : (
                        <Textarea
                          value={line.optimized_text}
                          onChange={(e) =>
                            updateLine(line.line_id, {
                              optimized_text: e.target.value,
                            })
                          }
                          rows={1}
                          onInput={(e) =>
                            autoResize(e.target as HTMLTextAreaElement)
                          }
                          ref={(el) => {
                            if (el) autoResize(el);
                          }}
                          className="min-h-0 block w-full resize-none border-0 bg-transparent p-0 text-[15px] text-[#334155] leading-[1.7] shadow-none focus-visible:ring-0 rounded-none m-0 overflow-hidden placeholder:text-[#cbd5e1]"
                          placeholder={isNoSpeech ? "<No Speech>" : ""}
                        />
                      )}
                    </div>
                    {!isRemoved && (
                      <div
                        className="opacity-0 group-hover:opacity-100 shrink-0 ml-2 text-[#cbd5e1] hover:text-[#ef4444] cursor-pointer flex items-center h-6 px-1 transition-opacity"
                        onClick={() => updateLine(line.line_id, { user_final_remove: true })}
                        title="剔除此行"
                      >
                        <X className="h-4 w-4" />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="sticky bottom-6 z-10 mx-auto max-w-2xl">
            <Card className="border-t-4 border-t-primary shadow-xl">
              <CardContent className="flex items-center justify-between p-6">
                <div className="flex items-center gap-8">
                  <div>
                    <div className="text-sm font-medium text-muted-foreground">
                      原始时长
                    </div>
                    <div className="text-2xl font-bold font-mono">
                      {formatDuration(originalDuration)}
                    </div>
                  </div>
                  <ArrowRight className="h-6 w-6 text-muted-foreground/50" />
                  <div>
                    <div className="text-sm font-medium text-muted-foreground">
                      预计时长
                    </div>
                    <div className="text-2xl font-bold font-mono text-emerald-600">
                      {formatDuration(estimatedDuration)}
                    </div>
                  </div>
                </div>
                <Button
                  size="lg"
                  onClick={handleConfirmStep1}
                  disabled={lines.length === 0 || busy}
                >
                  {busy ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      正在保存字幕...
                    </>
                  ) : (
                    "确认字幕，生成章节"
                  )}
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* Step 3: Review Chapters */}
      {job.status === STATUS.STEP2_READY && (
        <div className="space-y-8">
          <div>
            <h2 className="text-2xl font-bold tracking-tight">确认视频章节</h2>
            <p className="text-muted-foreground">
              拖拽字幕行到相邻章节可调整连续边界，点击标题可编辑，字幕文字也可以在这里继续微调；每个章节至少保留 3 句字幕。
            </p>
          </div>

          {(chapters.length === 0 || keptLines.length === 0) && (
            <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-slate-200 bg-white py-16 text-center shadow-sm">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
              <div>
                <p className="font-medium text-slate-900">正在载入章节草稿...</p>
                <p className="text-sm text-slate-500">
                  章节和字幕准备好后，这里会自动显示可编辑内容。
                </p>
              </div>
            </div>
          )}

          {chapters.length > 0 && keptLines.length > 0 && (
            <div className="space-y-6">
              {chapters.map((chapter, chapterIdx) => {
                const badgeColorClass =
                  CHAPTER_BADGE_COLORS[chapterIdx % CHAPTER_BADGE_COLORS.length];
                const borderClass =
                  CHAPTER_COLORS[chapterIdx % CHAPTER_COLORS.length];
                const chapterLines = getChapterLinesFromRange(chapter, keptLines);

                return (
                  <div
                    key={chapter.chapter_id}
                    className={cn(
                      "relative overflow-hidden rounded-lg border bg-card text-card-foreground shadow-sm transition-all",
                      borderClass
                    )}
                  >
                    <div className="flex items-center gap-4 border-b bg-muted/30 p-4">
                      <Badge
                        className={cn(
                          "h-6 w-6 shrink-0 items-center justify-center rounded-full p-0 text-white hover:bg-opacity-90",
                          badgeColorClass
                        )}
                      >
                        {chapterIdx + 1}
                      </Badge>
                      <input
                        type="text"
                        value={chapter.title}
                        placeholder="章节标题"
                        onChange={(event) =>
                          updateChapter(chapter.chapter_id, {
                            title: event.target.value,
                          })
                        }
                        className="flex-1 bg-transparent text-lg font-semibold outline-none placeholder:text-muted-foreground"
                      />
                      <Badge variant="outline" className="ml-auto">
                        {chapterLines.length} 句
                      </Badge>
                    </div>

                    <div
                      className="min-h-[60px] divide-y divide-border/50"
                      onDragOver={(event) => {
                        event.preventDefault();
                        event.dataTransfer.dropEffect = "move";
                      }}
                      onDrop={(event) => {
                        event.preventDefault();
                        setDraggedLineId(null);
                        const lineId = parseInt(
                          event.dataTransfer.getData("text/plain"),
                          10
                        );
                        if (Number.isNaN(lineId)) return;
                        const draggedPosition = keptLinePositionById.get(lineId);
                        if (!draggedPosition) return;
                        setChapters((previous) => {
                          const moved = moveAdjacentChapterRange(
                            previous,
                            draggedPosition,
                            chapter.chapter_id
                          );
                          if (moved.error) {
                            setError(moved.error);
                            return previous;
                          }
                          return moved.chapters;
                        });
                      }}
                    >
                      {chapterLines.map((line) => {
                        const isDragged = draggedLineId === line.line_id;
                        return (
                          <div
                            key={line.line_id}
                            onDragOver={(event) => {
                              event.preventDefault();
                              event.dataTransfer.dropEffect = "move";
                            }}
                            onDrop={(event) =>
                              handleDropOnLine(
                                event,
                                chapter.chapter_id
                              )
                            }
                            className={cn(
                              "flex items-start gap-3 p-3 text-sm transition-colors",
                              isDragged
                                ? "bg-muted opacity-40"
                                : "hover:bg-muted/40"
                            )}
                          >
                            <div
                              draggable
                              onDragStart={(event) => handleDragStart(event, line.line_id)}
                              onDragEnd={handleDragEnd}
                              className="mt-1 flex cursor-grab select-none items-center text-muted-foreground active:cursor-grabbing"
                              title="拖拽到其他章节"
                            >
                              <GripVertical className="h-4 w-4" />
                            </div>
                            <span className="mt-2 select-none font-mono text-xs text-muted-foreground">
                              {formatDuration(line.start)}
                            </span>
                            <Textarea
                              value={line.optimized_text}
                              onChange={(event) =>
                                updateLine(line.line_id, {
                                  optimized_text: event.target.value,
                                })
                              }
                              rows={1}
                              onInput={(event) =>
                                autoResize(event.target as HTMLTextAreaElement)
                              }
                              ref={(element) => {
                                if (element) autoResize(element);
                              }}
                              className="min-h-0 flex-1 resize-none border-0 bg-transparent p-0 leading-relaxed shadow-none focus-visible:ring-0"
                              placeholder="<No Speech>"
                            />
                          </div>
                        );
                      })}
                      {chapterLines.length === 0 && (
                        <div className="m-4 flex h-20 items-center justify-center rounded-md border-2 border-dashed border-muted text-sm text-muted-foreground">
                          拖拽字幕行到此章节
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          <div className="flex justify-center pt-8">
            <Button
              size="lg"
              className="w-full max-w-sm"
              onClick={() => void handleConfirmStep2()}
              disabled={chapters.length === 0 || busy}
            >
              {busy ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在保存...
                </>
              ) : (
                "确认章节，进入导出"
              )}
            </Button>
          </div>
        </div>
      )}

      {/* Step 4: Export */}
      {(job.status === STATUS.STEP2_CONFIRMED || job.status === STATUS.SUCCEEDED) && (
        <div className="space-y-4">
          <div className="mx-auto grid max-w-[980px] gap-3 xl:grid-cols-[minmax(0,560px)_320px] xl:items-stretch">
            <Card className="border-slate-200/80 xl:h-[min(70vh,760px)]">
              <CardContent className="flex h-full flex-col justify-center gap-3 p-3">
                <ExportFramePreview
                  config={renderConfig}
                  sourceFile={selectedFile}
                  subtitleTheme={subtitleTheme}
                  previewTimeSec={previewTimeSec}
                  overlayControls={overlayControls}
                />
                {renderConfigBusy && (
                  <div className="flex items-center gap-2 text-sm text-slate-500">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    正在生成预览配置...
                  </div>
                )}
                {renderSetupError && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                    {renderSetupError}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card className="xl:h-[min(70vh,760px)]">
              <CardContent className="flex h-full flex-col gap-4 p-3">
                <div className="flex items-center justify-between gap-3">
                  <label className="text-sm font-medium">标题行数</label>
                  <Select
                    value={(overlayControls.progressLabelMode ?? "auto") as ProgressLabelMode}
                    onValueChange={(value) =>
                      setOverlayControls((previous) => ({
                        ...previous,
                        progressLabelMode: value as ProgressLabelMode,
                      }))
                    }
                    disabled={renderBusy}
                  >
                    <SelectTrigger className="w-[152px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {PROGRESS_LABEL_MODE_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex items-center justify-between gap-3">
                  <label className="text-sm font-medium">字幕样式</label>
                  <Select
                    value={subtitleTheme}
                    onValueChange={(v) => setSubtitleTheme(v as SubtitleTheme)}
                    disabled={renderBusy}
                  >
                    <SelectTrigger className="w-[152px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SUBTITLE_THEME_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <label className="font-medium">字幕大小</label>
                    <span className="font-mono text-slate-500">
                      {Math.round((overlayControls.subtitleScale ?? 1) * 100)}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min={OVERLAY_SCALE_LIMITS.subtitle.min}
                    max={OVERLAY_SCALE_LIMITS.subtitle.max}
                    step={OVERLAY_SCALE_LIMITS.subtitle.step}
                    value={overlayControls.subtitleScale ?? OVERLAY_SCALE_LIMITS.subtitle.defaultValue}
                    onChange={(event) => {
                      const nextSubtitleScale = Math.max(
                        Number(event.currentTarget.value),
                        OVERLAY_SCALE_LIMITS.subtitle.min
                      );
                      const boundedSubtitleScale = Math.min(
                        nextSubtitleScale,
                        OVERLAY_SCALE_LIMITS.subtitle.max
                      );
                      setOverlayControls((previous) => ({
                        ...previous,
                        subtitleScale: boundedSubtitleScale,
                      }));
                    }}
                    disabled={renderBusy}
                    className="h-2 w-full cursor-ew-resize accent-slate-900 disabled:cursor-not-allowed"
                  />
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <label className="font-medium">进度条大小</label>
                    <span className="font-mono text-slate-500">
                      {Math.round((overlayControls.progressScale ?? 1) * 100)}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min={OVERLAY_SCALE_LIMITS.progress.min}
                    max={OVERLAY_SCALE_LIMITS.progress.max}
                    step={OVERLAY_SCALE_LIMITS.progress.step}
                    value={overlayControls.progressScale ?? OVERLAY_SCALE_LIMITS.progress.defaultValue}
                    onChange={(event) => {
                      const nextProgressScale = Math.max(
                        Number(event.currentTarget.value),
                        OVERLAY_SCALE_LIMITS.progress.min
                      );
                      const boundedProgressScale = Math.min(
                        nextProgressScale,
                        OVERLAY_SCALE_LIMITS.progress.max
                      );
                      setOverlayControls((previous) => ({
                        ...previous,
                        progressScale: boundedProgressScale,
                      }));
                    }}
                    disabled={renderBusy}
                    className="h-2 w-full cursor-ew-resize accent-slate-900 disabled:cursor-not-allowed"
                  />
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <label className="font-medium">章节块大小</label>
                    <span className="font-mono text-slate-500">
                      {Math.round((overlayControls.chapterScale ?? 1) * 100)}%
                    </span>
                  </div>
                  <input
                    type="range"
                    min={OVERLAY_SCALE_LIMITS.chapter.min}
                    max={OVERLAY_SCALE_LIMITS.chapter.max}
                    step={OVERLAY_SCALE_LIMITS.chapter.step}
                    value={overlayControls.chapterScale ?? OVERLAY_SCALE_LIMITS.chapter.defaultValue}
                    onChange={(event) => {
                      const nextChapterScale = Math.max(
                        Number(event.currentTarget.value),
                        OVERLAY_SCALE_LIMITS.chapter.min
                      );
                      const boundedChapterScale = Math.min(
                        nextChapterScale,
                        OVERLAY_SCALE_LIMITS.chapter.max
                      );
                      setOverlayControls((previous) => ({
                        ...previous,
                        chapterScale: boundedChapterScale,
                      }));
                    }}
                    disabled={renderBusy}
                    className="h-2 w-full cursor-ew-resize accent-slate-900 disabled:cursor-not-allowed"
                  />
                </div>

                {renderBusy && (
                  <div className="space-y-2 border-t border-slate-200 pt-3">
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>导出进度</span>
                      <span>{Math.round(renderProgress)}%</span>
                    </div>
                    <Progress value={renderProgress} className="h-2" />
                  </div>
                )}

                <div className="mt-auto flex flex-col gap-2 border-t border-slate-200 pt-3">
                  <Button
                    size="lg"
                    className="w-full"
                    onClick={() => {
                      if (renderDownloadUrl) {
                        triggerFileDownload(renderDownloadUrl, renderFileName);
                        return;
                      }
                      void handleStartRender();
                    }}
                    disabled={renderBusy || busy || renderConfigBusy || Boolean(renderSetupError)}
                  >
                    {renderBusy ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 正在导出
                      </>
                    ) : renderDownloadUrl ? (
                      <>
                        <Download className="mr-2 h-4 w-4" /> 再次下载
                      </>
                    ) : (
                      <>
                        <FileVideo className="mr-2 h-4 w-4" /> 导出视频
                      </>
                    )}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

    </main>
  );
}
