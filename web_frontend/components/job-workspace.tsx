"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from "react";
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
  getRenderCompletionPending,
  clearRenderCompletionPending,
  setRenderCompletionPending,
  markRenderSucceeded,
  runStep1,
  runStep2,
  uploadAudioDirectToOss,
} from "../lib/api";
import { extractAudioForAsr } from "../lib/audio-extract";
import { isUnsupportedMobileUploadDevice } from "../lib/device";
import { tryParseVideoMetadataWithMediaInfo } from "../lib/media-metadata";
import {
  loadCachedJobSourceVideo,
  saveCachedJobSourceVideo,
} from "../lib/video-cache";
import {
  getLikelyAppExportFileMessage,
  getSourceVideoMismatchMessage,
  isLikelyAppExportFileName,
} from "../lib/source-video-guard";
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
  DEFAULT_OVERLAY_CONTROLS,
  OVERLAY_POSITION_LIMITS,
  OVERLAY_SCALE_LIMITS,
  type OverlayScaleControls,
  type ProgressLabelMode,
} from "../lib/remotion/overlay-controls";
import ExportFramePreview from "./export-frame-preview";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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

function OverlayToggleTile({
  label,
  checked,
  disabled = false,
  onCheckedChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 transition-colors",
        checked
          ? "bg-slate-900 text-white"
          : "bg-slate-100 text-slate-700 hover:bg-slate-200/70",
        disabled && "cursor-not-allowed opacity-60"
      )}
    >
      <span className="text-[12px] font-medium">{label}</span>
      <Checkbox
        checked={checked}
        onCheckedChange={(value) => onCheckedChange(value !== false)}
        disabled={disabled}
        className={cn(
          checked
            ? "h-4 w-4 border-white/70 data-[state=checked]:border-white data-[state=checked]:bg-white data-[state=checked]:text-slate-900"
            : "h-4 w-4 border-slate-300 bg-white"
        )}
      />
    </label>
  );
}

function OverlaySliderField({
  label,
  valueText,
  min,
  max,
  step,
  value,
  disabled = false,
  onChange,
}: {
  label: string;
  valueText: string;
  min: number;
  max: number;
  step: number;
  value: number;
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <label className="text-[12px] font-medium text-slate-800">{label}</label>
        <span className="font-mono text-[12px] text-slate-500">{valueText}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.currentTarget.value))}
        disabled={disabled}
        className="h-2 w-full cursor-ew-resize accent-slate-900 disabled:cursor-not-allowed"
      />
    </div>
  );
}

const MAX_VIDEO_DURATION_SEC = 10 * 60;
const JOB_LOAD_RETRY_DELAY_MS = 4000;
const STEP_DRAFT_RETRY_DELAY_MS = 3000;
const RENDER_COMPLETE_RETRY_BASE_MS = 3000;
const RENDER_COMPLETE_RETRY_MAX_MS = 120000;
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

function withTimeout<T>(
  promise: Promise<T>,
  timeoutMs: number,
  message: string
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      reject(new Error(message));
    }, timeoutMs);

    promise.then(
      (value) => {
        window.clearTimeout(timeoutId);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timeoutId);
        reject(error);
      }
    );
  });
}

function formatDuration(seconds: number): string {
  if (!seconds || Number.isNaN(seconds)) return "00:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function getFriendlyError(err: unknown): string {
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return "网络异常，请稍后重试。";
}

async function resolveRenderMetaFromFile(file: File): Promise<RenderMeta> {
  const url = URL.createObjectURL(file);
  try {
    const mediaInfoPromise = tryParseVideoMetadataWithMediaInfo(file);
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
          width: Math.round(video.videoWidth || 0),
          height: Math.round(video.videoHeight || 0),
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

    const mediaInfoMeta = await mediaInfoPromise;
    const width =
      meta.width > 0 ? meta.width : Math.trunc(Number(mediaInfoMeta?.width ?? 0));
    const height =
      meta.height > 0 ? meta.height : Math.trunc(Number(mediaInfoMeta?.height ?? 0));
    const durationSec =
      typeof meta.duration === "number" && Number.isFinite(meta.duration) && meta.duration > 0
        ? meta.duration
        : typeof mediaInfoMeta?.durationSec === "number" &&
            Number.isFinite(mediaInfoMeta.durationSec) &&
            mediaInfoMeta.durationSec > 0
          ? mediaInfoMeta.durationSec
          : undefined;
    if (width <= 0 || height <= 0) {
      throw new Error("无法读取本地视频分辨率，请重新选择源文件后重试。");
    }
    const fps = mediaInfoMeta?.fps ?? (await estimateFps());
    return {
      width,
      height,
      duration_sec: durationSec,
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
    case "STEP1_QUEUED":
      return "任务已入队，马上开始识别语音并整理字幕。";
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

function getStep1ProcessingTitle(
  stageCode: string | null | undefined,
  stageMessage: string | null | undefined
): string {
  const trimmedMessage = String(stageMessage || "").trim();
  switch (String(stageCode || "").trim()) {
    case "STEP1_QUEUED":
      return "正在启动字幕任务";
    case "TRANSCRIBING_AUDIO":
      return "正在识别语音";
    case "OPTIMIZING_TEXT":
    case "REMOVING_REDUNDANT_LINES":
      return "正在筛除冗余字幕";
    case "MERGING_SHORT_LINES":
      return "正在合并短句";
    case "POLISHING_EXPRESSION":
      return "正在润色字幕";
    case "PREPARING_STEP1_REVIEW":
      return "正在整理字幕结果";
    case "STEP1_READY":
      return "正在进入字幕确认";
    default:
      return trimmedMessage || "正在提取字幕";
  }
}

function Step1ProcessingState({
  job,
  lines,
  busy,
  autoStep1Triggered,
  draftError,
  onRetry,
  onRetryDraft,
}: {
  job: Job;
  lines: Step1Line[];
  busy: boolean;
  autoStep1Triggered: boolean;
  draftError: string;
  onRetry: () => void;
  onRetryDraft: () => void;
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
              {getStep1ProcessingTitle(job.stage?.code, job.stage?.message)}
            </h2>
            <p className="relative mx-auto mt-1.5 max-w-[240px] text-[12px] leading-5 text-slate-500">
            {getStep1ProcessingNote(job.stage?.code)}
          </p>
          {draftError && (
            <p className="relative mt-2 max-w-[260px] text-[12px] leading-5 text-red-600">
              {draftError}
            </p>
          )}

          <Progress
            value={visualProgress}
            className="relative mx-auto mt-3 h-1 w-20 bg-slate-200/80"
            indicatorClassName="bg-gradient-to-r from-[#60a5fa] via-[#2563eb] to-[#0f172a]"
          />

          {draftError && (
            <Button
              type="button"
              variant="outline"
              className="relative mt-4 h-8 rounded-full px-3 text-xs"
              onClick={onRetryDraft}
            >
              重新加载字幕草稿
            </Button>
          )}

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
  const [jobLoadError, setJobLoadError] = useState("");
  const [isLoadingJob, setIsLoadingJob] = useState(true);
  const [step1DraftError, setStep1DraftError] = useState("");
  const [step2DraftError, setStep2DraftError] = useState("");
  const [step2DraftLoaded, setStep2DraftLoaded] = useState(false);
  const [renderCompletionMarkerMessage, setRenderCompletionMarkerMessage] = useState("");
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
    ...DEFAULT_OVERLAY_CONTROLS,
  });
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [draggedLineId, setDraggedLineId] = useState<number | null>(null);
  const [uploadStageMessage, setUploadStageMessage] = useState("");
  const [autoStep1Triggered, setAutoStep1Triggered] = useState(false);
  const [autoStep2Triggered, setAutoStep2Triggered] = useState(false);
  const [step1ReadyHandoffActive, setStep1ReadyHandoffActive] = useState(false);
  const [step1ReadyLinesLoaded, setStep1ReadyLinesLoaded] = useState(false);
  const [step2ReadyLinesLoaded, setStep2ReadyLinesLoaded] = useState(false);
  const [mobileUploadBlocked, setMobileUploadBlocked] = useState(false);
  const renderSourceInputRef = useRef<HTMLInputElement>(null);
  const isMountedRef = useRef(true);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    setMobileUploadBlocked(isUnsupportedMobileUploadDevice());
  }, []);

  const showMobileUploadError = useCallback(() => {
    setError("移动端暂不支持上传视频，请在电脑浏览器使用（建议 Chrome）。");
  }, []);

  const loadRenderConfigWithMeta = useCallback(
    async (
      sourceFile: File,
      meta: RenderMeta,
      { timeoutMs }: { timeoutMs?: { config?: number } } = {}
    ): Promise<WebRenderConfig> => {
      const configRequest = getWebRenderConfigWithMeta(jobId, meta);
      const config =
        typeof timeoutMs?.config === "number"
          ? await withTimeout(
              configRequest,
              timeoutMs.config,
              "生成预览配置超时，请重试。"
            )
          : await configRequest;
      const sourceMismatchMessage = getSourceVideoMismatchMessage(
        sourceFile.name,
        meta,
        config
      );
      if (sourceMismatchMessage) {
        throw new Error(sourceMismatchMessage);
      }
      return config;
    },
    [jobId]
  );

  const loadRenderSourceFile = useCallback(async (): Promise<File | null> => {
    let sourceFile = selectedFile;
    if (!sourceFile) {
      sourceFile = await loadCachedJobSourceVideo(jobId);
      if (sourceFile) {
        setSelectedFile(sourceFile);
      }
    }
    return sourceFile ?? null;
  }, [jobId, selectedFile]);

  const prepareRenderPreview = useCallback(async (): Promise<WebRenderConfig | null> => {
    if (renderBusy) return null;

    setRenderConfigBusy(true);
    setRenderSetupError("");
    try {
      const sourceFile = await loadRenderSourceFile();
      if (!sourceFile) {
        throw new Error(
          "当前会话缺少本地原始视频，请先重新选择当前任务对应的源文件。"
        );
      }

      const meta = await withTimeout(
        resolveRenderMetaFromFile(sourceFile),
        10000,
        "读取本地视频元数据超时，请刷新页面后重试。"
      );
      const config = await loadRenderConfigWithMeta(sourceFile, meta, {
        timeoutMs: { config: 15000 },
      });
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
      return config;
    } catch (err) {
      setRenderConfig(null);
      setRenderSetupError(
        err instanceof Error ? err.message : "导出预览初始化失败，请重试。"
      );
      return null;
    } finally {
      setRenderConfigBusy(false);
    }
  }, [jobId, loadRenderConfigWithMeta, renderBusy, selectedFile]);

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

  const loadJob = useCallback(
    async (opts: { background?: boolean } = {}) => {
      const isBackground = Boolean(opts.background);
      if (!isBackground) {
        if (isMountedRef.current) {
          setIsLoadingJob(true);
          setJobLoadError("");
        }
      }

      try {
        const next = await refreshJob();
        if (isMountedRef.current) {
          setJobLoadError("");
          setError((previous) =>
            previous.includes("正在重试") || previous.includes("无法连接 API")
              ? ""
              : previous
          );
        }
        return next;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        if (isBackground) {
          if (isMountedRef.current) {
            setError(
              message.includes("无法连接 API")
                ? `${message}，正在重试。`
                : `项目状态刷新失败：${message}，正在重试。`
            );
          }
          return;
        }

        const isJobMissing =
          (err instanceof ApiClientError && err.code === "NOT_FOUND") ||
          message.includes("job not found");
        if (isJobMissing) {
          if (isMountedRef.current) {
            setJobLoadError("项目不存在或已被清理，已返回首页。");
          }
          return;
        }

        const isUnauthorized =
          (err instanceof ApiClientError && err.code === "UNAUTHORIZED") ||
          message.includes("请先登录") ||
          message.includes("登录状态无效");
        if (isUnauthorized) {
          if (isMountedRef.current) {
            setJobLoadError("登录状态已失效，请重新登录。");
          }
          return;
        }

        if (isMountedRef.current) {
          setJobLoadError(
            message.includes("无法连接 API")
              ? message
              : "无法连接 API，请确认后端服务正在运行。"
          );
        }
      } finally {
        if (!isBackground) {
          if (isMountedRef.current) {
            setIsLoadingJob(false);
          }
        }
      }
    },
    [refreshJob]
  );

  const handleRetryLoadJob = useCallback(() => {
    void loadJob();
  }, [loadJob]);

  useEffect(() => {
    void loadJob();
  }, [loadJob]);

  useEffect(() => {
    if (job || !jobLoadError || isLoadingJob) {
      return;
    }

    const timer = window.setTimeout(() => {
      if (isMountedRef.current) {
        void loadJob();
      }
    }, JOB_LOAD_RETRY_DELAY_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [isLoadingJob, job, jobLoadError, loadJob]);

  useEffect(() => {
    if (!job || job.status !== STATUS.STEP1_READY) {
      setStep1ReadyHandoffActive(false);
      setStep1ReadyLinesLoaded(false);
      setStep1DraftError("");
      return;
    }
    if (step1ReadyLinesLoaded) {
      return;
    }

    setStep1ReadyHandoffActive(true);
    let cancelled = false;
    const pollStep1Lines = () => {
      getStep1(jobId)
        .then((nextLines) => {
          if (cancelled) return;
          setStep1DraftError("");
          setLines((previous) =>
            areStep1LinesEqual(previous, nextLines) ? previous : nextLines
          );
          setStep1ReadyLinesLoaded(nextLines.length > 0);
        })
        .catch((err) => {
          if (cancelled) return;
          setStep1DraftError(
            `字幕草稿加载失败：${getFriendlyError(err)}，已自动重试。`
          );
        });
    };

    pollStep1Lines();
    const intervalId = window.setInterval(pollStep1Lines, STEP_DRAFT_RETRY_DELAY_MS);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [job?.status, jobId, step1ReadyLinesLoaded]);

  useEffect(() => {
    if (!job || job.status !== STATUS.STEP1_RUNNING) {
      return;
    }

    let cancelled = false;
    const pollStep1Lines = () => {
      getStep1(jobId)
        .then((nextLines) => {
          if (cancelled) return;
          if (nextLines.length === 0) return;
          setStep1DraftError("");
          setLines((previous) =>
            areStep1LinesEqual(previous, nextLines) ? previous : nextLines
          );
        })
        .catch((err) => {
          if (cancelled) return;
          setStep1DraftError(
            `字幕草稿加载失败：${getFriendlyError(err)}，已自动重试。`
          );
        });
    };

    pollStep1Lines();
    const intervalId = window.setInterval(pollStep1Lines, STEP_DRAFT_RETRY_DELAY_MS);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [job?.status, job?.stage?.code, jobId]);

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
    if (!job || job.status !== STATUS.STEP2_READY) {
      setStep2ReadyLinesLoaded(false);
      setStep2DraftLoaded(false);
      setStep2DraftError("");
      return;
    }
    if (step2DraftLoaded) {
      return;
    }

    let cancelled = false;
    const pollChapters = () => {
      getStep2(jobId)
        .then((nextChapters) => {
          if (cancelled) return;
          if (!nextChapters || nextChapters.length === 0) return;
          setStep2DraftError("");
          setChapters((previous) => (previous.length ? previous : nextChapters));
          setStep2DraftLoaded(true);
        })
        .catch((err) => {
          if (cancelled) return;
          setStep2DraftError(
            `章节草稿加载失败：${getFriendlyError(err)}，已自动重试。`
          );
        });
    };

    pollChapters();
    const intervalId = window.setInterval(pollChapters, STEP_DRAFT_RETRY_DELAY_MS);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [job?.status, jobId, step2DraftLoaded]);

  useEffect(() => {
    if (!job || job.status !== STATUS.STEP2_READY) {
      return;
    }
    if (step2ReadyLinesLoaded) {
      return;
    }

    let cancelled = false;
    const pollStep2Lines = () => {
      getStep1(jobId)
        .then((nextLines) => {
          if (cancelled) return;
          if (nextLines.length === 0) return;
          setStep2DraftError("");
          setLines((previous) =>
            areStep1LinesEqual(previous, nextLines) ? previous : nextLines
          );
          setStep2ReadyLinesLoaded(true);
        })
        .catch((err) => {
          if (cancelled) return;
          setStep2DraftError(
            `章节页字幕加载失败：${getFriendlyError(err)}，已自动重试。`
          );
        });
    };

    pollStep2Lines();
    const intervalId = window.setInterval(pollStep2Lines, STEP_DRAFT_RETRY_DELAY_MS);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [job?.status, jobId, step2ReadyLinesLoaded]);

  const handleRetryStep1DraftLoad = useCallback(() => {
    if (!job || job.status !== STATUS.STEP1_READY) return;
    setStep1DraftError("");
    setStep1ReadyLinesLoaded(false);
  }, [job?.status]);

  const handleRetryStep2DraftLoad = useCallback(() => {
    if (!job || job.status !== STATUS.STEP2_READY) return;
    setStep2ReadyLinesLoaded(false);
    setStep2DraftLoaded(false);
    setStep2DraftError("");
  }, [job?.status]);

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
    setRenderCompletionMarkerMessage("");
    setPreviewTimeSec(0);
    setJob(null);
    setLines([]);
    setChapters([]);
    setStep2DraftLoaded(false);
    setStep1ReadyLinesLoaded(false);
    setStep2ReadyLinesLoaded(false);
    setStep1DraftError("");
    setStep2DraftError("");
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
      ...DEFAULT_OVERLAY_CONTROLS,
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

  const handleSourceFileChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const input = event.currentTarget;
      const file = input.files?.[0];
      input.value = "";
      if (!file) return;

      const lowerName = file.name.toLowerCase();
      const hasSupportedExt = SUPPORTED_UPLOAD_EXTENSIONS.some((ext) =>
        lowerName.endsWith(ext)
      );
      if (!hasSupportedExt) {
        setRenderSetupError(
          "这个文件格式暂不支持。请上传 MP4、MOV、MKV、WebM、M4V、TS、M2TS 或 MTS 视频。"
        );
        return;
      }

      setSelectedFile(file);
      setRenderSetupError("");
      setRenderCompletionMarkerMessage("");
      setStep1DraftError("");
      setStep2DraftError("");
      if (selectedFile?.name !== file.name || selectedFile?.size !== file.size) {
        setRenderFileName("output.mp4");
      }
      void saveCachedJobSourceVideo(jobId, file).catch(() => undefined);
      void prepareRenderPreview();
    },
    [jobId, prepareRenderPreview, selectedFile]
  );

  useEffect(() => {
    if (!job) return;
    if (job.status === STATUS.SUCCEEDED) {
      setRenderCompletionMarkerMessage("");
      clearRenderCompletionPending(jobId);
      return;
    }
    if (job.status !== STATUS.STEP2_CONFIRMED) {
      return;
    }

    const marker = getRenderCompletionPending(jobId);
    if (!marker) return;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | number | null = null;

    const retry = async () => {
      if (cancelled) return;
      const latestMarker = getRenderCompletionPending(jobId);
      if (!latestMarker) return;
      try {
        const completion = await markRenderSucceeded(jobId, {keepalive: true});
        if (cancelled) return;
        clearRenderCompletionPending(jobId);
        setRenderCompletionMarkerMessage("");
        setJob((previous) => mergeJobSnapshot(previous, completion.job));
      } catch (err) {
        if (cancelled) return;
        const message = getFriendlyError(err);
        const nextMarker = setRenderCompletionPending(jobId, message);
        const delay = Math.min(
          RENDER_COMPLETE_RETRY_MAX_MS,
          RENDER_COMPLETE_RETRY_BASE_MS * 2 ** Math.max((nextMarker?.attempts || 1) - 1, 0)
        );
        setRenderCompletionMarkerMessage(
          `导出确认未完成：${message}，约 ${Math.ceil(delay / 1000)} 秒后将自动重试。`
        );
        timer = window.setTimeout(retry, delay);
      }
    };

    void retry();

    return () => {
      cancelled = true;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [job?.status, jobId]);

  useEffect(() => {
    const exportReady =
      job?.status === STATUS.STEP2_CONFIRMED || job?.status === STATUS.SUCCEEDED;
    if (!exportReady) return;
    if (renderConfig) return;
    if (renderConfigBusy || renderSetupError) return;
    void prepareRenderPreview();
  }, [job?.status, prepareRenderPreview, renderConfig, renderConfigBusy, renderSetupError]);

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
      if (isLikelyAppExportFileName(file.name)) {
        setError(getLikelyAppExportFileMessage(file.name));
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
      loadJob({background: true}).catch(() => undefined);
    }, 2500);
    return () => {
      clearInterval(timer);
    };
  }, [job?.status, loadJob]);

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
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

  const handleDragStart = useCallback((event: DragEvent, lineId: number) => {
    event.dataTransfer.setData("text/plain", lineId.toString());
    event.dataTransfer.effectAllowed = "move";
    setDraggedLineId(lineId);
  }, []);

  const triggerRenderSourceFileInput = useCallback(() => {
    renderSourceInputRef.current?.click();
  }, []);

  const handleDragEnd = useCallback(() => {
    setDraggedLineId(null);
  }, []);

  const handleDropOnLine = useCallback(
    (event: DragEvent, targetChapterId: number) => {
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
    let sourceObjectUrl: string | null = null;
    try {
      const sourceFile = await loadRenderSourceFile();
      if (!sourceFile) {
        throw new Error(
          "当前会话缺少本地原始视频，请先选择对应的源文件后再导出。"
        );
      }
      const sourceMeta = await resolveRenderMetaFromFile(sourceFile);
      const config =
        renderConfig ?? (await loadRenderConfigWithMeta(sourceFile, sourceMeta));
      setRenderConfig((previous) => previous ?? config);
      sourceObjectUrl = URL.createObjectURL(sourceFile);
      const inputProps = {
        ...config.input_props,
        src: sourceObjectUrl,
        subtitleTheme,
        subtitleScale: overlayControls.subtitleScale,
        subtitleYPercent: overlayControls.subtitleYPercent,
        progressScale: overlayControls.progressScale,
        progressYPercent: overlayControls.progressYPercent,
        chapterScale: overlayControls.chapterScale,
        showSubtitles: overlayControls.showSubtitles,
        showProgress: overlayControls.showProgress,
        showChapter: overlayControls.showChapter,
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

      if (typeof document !== "undefined" && "fonts" in document) {
        try {
          await document.fonts.ready;
        } catch {
          // Ignore font readiness failures and let the renderer proceed.
        }
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
      setRenderCompletionPending(jobId);
      triggerFileDownload(objectUrl, outputName);
      setRenderProgress(100);
      try {
        const completion = await markRenderSucceeded(jobId, {keepalive: true});
        setJob((previous) => mergeJobSnapshot(previous, completion.job));
        clearRenderCompletionPending(jobId);
        setRenderCompletionMarkerMessage("");
      } catch (syncErr) {
        const message = getFriendlyError(syncErr);
        setRenderCompletionMarkerMessage(
          `视频已导出，但服务端确认失败：${message}。页面刷新后会自动继续重试确认。`
        );
        setRenderCompletionPending(jobId, message);
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
    loadRenderConfigWithMeta,
    overlayControls.progressLabelMode,
    overlayControls.progressScale,
    overlayControls.progressYPercent,
    overlayControls.chapterScale,
    overlayControls.subtitleScale,
    overlayControls.subtitleYPercent,
    overlayControls.showSubtitles,
    overlayControls.showProgress,
    overlayControls.showChapter,
    loadRenderSourceFile,
    renderConfig,
    subtitleTheme,
  ]);

  useEffect(() => {
    if (renderBusy) return;
    setRenderProgress(0);
  }, [
    overlayControls.progressLabelMode,
    overlayControls.progressScale,
    overlayControls.progressYPercent,
    overlayControls.chapterScale,
    overlayControls.subtitleScale,
    overlayControls.subtitleYPercent,
    overlayControls.showSubtitles,
    overlayControls.showProgress,
    overlayControls.showChapter,
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
        {isLoadingJob ? (
          <>
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-muted-foreground">正在加载项目数据...</p>
          </>
        ) : jobLoadError ? (
          <div className="w-full max-w-md space-y-4 rounded-md bg-destructive/10 p-4 text-sm text-destructive border border-destructive/20">
            <p>{jobLoadError}</p>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" onClick={handleRetryLoadJob}>
                重新加载项目
              </Button>
              {onBackHome && (
                <Button size="sm" variant="outline" onClick={onBackHome}>
                  返回首页
                </Button>
              )}
            </div>
          </div>
        ) : (
          <>
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-muted-foreground">正在加载项目数据...</p>
          </>
        )}
      </main>
    );
  }

  const activeStep = getActiveStep(job.status);
  const hasRenderSource = Boolean(selectedFile);
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

      {renderCompletionMarkerMessage && (
        <div className="mb-6 rounded-md bg-amber-50 p-4 text-sm font-medium text-amber-800 border border-amber-200">
          {renderCompletionMarkerMessage}
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
            draftError={step1DraftError}
            onRetry={handleRetryStep1AutoRun}
            onRetryDraft={handleRetryStep1DraftLoad}
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
          {lines.length === 0 ? (
            <div className="space-y-3 rounded-2xl border border-slate-200 bg-white py-16 text-center shadow-sm">
              <Loader2 className="mx-auto h-8 w-8 animate-spin text-primary" />
              <p className="font-medium text-slate-900">正在载入字幕草稿...</p>
              <p className="text-sm text-slate-500">
                字幕整理完成后，这里会显示可编辑内容。
              </p>
              {step1DraftError && (
                <p className="mx-auto max-w-md text-sm text-red-600">{step1DraftError}</p>
              )}
              {step1DraftError && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleRetryStep1DraftLoad}
                  className="mx-auto"
                >
                  重新加载字幕草稿
                </Button>
              )}
            </div>
          ) : (
            <>
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
            </>
          )}
        </div>
      )}

      {/* Step 3: Review Chapters */}
      {job.status === STATUS.STEP2_READY && (
        <div className="space-y-8">
          <div>
            <h2 className="text-2xl font-bold tracking-tight">确认视频章节</h2>
            <p className="text-muted-foreground">
              拖拽字幕行到相邻章节可调整连续边界，点击标题可编辑，字幕文字也可以在这里继续微调。
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
              {step2DraftError && (
                <p className="max-w-md text-sm text-red-600">{step2DraftError}</p>
              )}
              {step2DraftError && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleRetryStep2DraftLoad}
                >
                  重新加载章节草稿
                </Button>
              )}
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
          <div className="mx-auto grid max-w-[1400px] gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(420px,0.92fr)] xl:items-start 2xl:max-w-[1520px] 2xl:grid-cols-[minmax(0,1.72fr)_minmax(456px,0.94fr)]">
            <Card className="border-slate-200/80 xl:h-[min(70vh,760px)]">
              <CardContent className="flex h-full min-h-0 flex-col justify-center gap-3 p-3">
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

            <Card className="overflow-hidden xl:self-start">
              <CardContent className="flex flex-col p-0">
                <input
                  ref={renderSourceInputRef}
                  type="file"
                  accept={SUPPORTED_UPLOAD_ACCEPT}
                  className="hidden"
                  onChange={handleSourceFileChange}
                  disabled={renderBusy || busy}
                />

                <div className="border-b border-slate-200 bg-slate-50/60 px-3 py-2">
                  <div className="text-sm font-semibold text-slate-900">导出设置</div>
                  <div className="mt-0.5 text-[11px] text-slate-500">预览与最终导出同步生效</div>
                </div>

                <div className="px-3 py-2.5">
                  <div className="space-y-2">
                    {!hasRenderSource ? (
                      <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                        <p>尚未读取到当前项目的本地源视频缓存，导出前请重新选择源文件。</p>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="mt-2"
                          onClick={triggerRenderSourceFileInput}
                          disabled={renderBusy || busy}
                        >
                          重新选择源文件
                        </Button>
                      </div>
                    ) : null}

                    <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
                      <div className="space-y-1">
                        <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                          标题行数
                        </label>
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
                          <SelectTrigger className="h-9 w-full">
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

                      <div className="space-y-1">
                        <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                          字幕样式
                        </label>
                        <Select
                          value={subtitleTheme}
                          onValueChange={(v) => setSubtitleTheme(v as SubtitleTheme)}
                          disabled={renderBusy}
                        >
                          <SelectTrigger className="h-9 w-full">
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
                    </div>

                    <section className="space-y-1 pt-1">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                        显示内容
                      </div>
                      <div className="grid grid-cols-3 gap-1.5">
                        <OverlayToggleTile
                          label="字幕"
                          checked={overlayControls.showSubtitles ?? DEFAULT_OVERLAY_CONTROLS.showSubtitles}
                          disabled={renderBusy}
                          onCheckedChange={(checked) =>
                            setOverlayControls((previous) => ({
                              ...previous,
                              showSubtitles: checked,
                            }))
                          }
                        />
                        <OverlayToggleTile
                          label="进度条"
                          checked={overlayControls.showProgress ?? DEFAULT_OVERLAY_CONTROLS.showProgress}
                          disabled={renderBusy}
                          onCheckedChange={(checked) =>
                            setOverlayControls((previous) => ({
                              ...previous,
                              showProgress: checked,
                            }))
                          }
                        />
                        <OverlayToggleTile
                          label="章节"
                          checked={overlayControls.showChapter ?? DEFAULT_OVERLAY_CONTROLS.showChapter}
                          disabled={renderBusy}
                          onCheckedChange={(checked) =>
                            setOverlayControls((previous) => ({
                              ...previous,
                              showChapter: checked,
                            }))
                          }
                        />
                      </div>
                    </section>

                    <section className="space-y-1 border-t border-slate-100 pt-1.5">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                        字幕
                      </div>
                      <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                        <OverlaySliderField
                          label="大小"
                          valueText={`${Math.round((overlayControls.subtitleScale ?? 1) * 100)}%`}
                          min={OVERLAY_SCALE_LIMITS.subtitle.min}
                          max={OVERLAY_SCALE_LIMITS.subtitle.max}
                          step={OVERLAY_SCALE_LIMITS.subtitle.step}
                          value={
                            overlayControls.subtitleScale ?? OVERLAY_SCALE_LIMITS.subtitle.defaultValue
                          }
                          disabled={renderBusy}
                          onChange={(value) =>
                            setOverlayControls((previous) => ({
                              ...previous,
                              subtitleScale: Math.min(
                                Math.max(value, OVERLAY_SCALE_LIMITS.subtitle.min),
                                OVERLAY_SCALE_LIMITS.subtitle.max
                              ),
                            }))
                          }
                        />
                        <OverlaySliderField
                          label="位置"
                          valueText={`Y ${Math.round(
                            overlayControls.subtitleYPercent ?? DEFAULT_OVERLAY_CONTROLS.subtitleYPercent
                          )}%`}
                          min={OVERLAY_POSITION_LIMITS.subtitleY.min}
                          max={OVERLAY_POSITION_LIMITS.subtitleY.max}
                          step={OVERLAY_POSITION_LIMITS.subtitleY.step}
                          value={
                            overlayControls.subtitleYPercent ??
                            OVERLAY_POSITION_LIMITS.subtitleY.defaultValue
                          }
                          disabled={renderBusy}
                          onChange={(value) =>
                            setOverlayControls((previous) => ({
                              ...previous,
                              subtitleYPercent: clampPercent(value),
                            }))
                          }
                        />
                      </div>
                    </section>

                    <section className="space-y-1 border-t border-slate-100 pt-1.5">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                        进度条
                      </div>
                      <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                        <OverlaySliderField
                          label="大小"
                          valueText={`${Math.round((overlayControls.progressScale ?? 1) * 100)}%`}
                          min={OVERLAY_SCALE_LIMITS.progress.min}
                          max={OVERLAY_SCALE_LIMITS.progress.max}
                          step={OVERLAY_SCALE_LIMITS.progress.step}
                          value={
                            overlayControls.progressScale ?? OVERLAY_SCALE_LIMITS.progress.defaultValue
                          }
                          disabled={renderBusy}
                          onChange={(value) =>
                            setOverlayControls((previous) => ({
                              ...previous,
                              progressScale: Math.min(
                                Math.max(value, OVERLAY_SCALE_LIMITS.progress.min),
                                OVERLAY_SCALE_LIMITS.progress.max
                              ),
                            }))
                          }
                        />
                        <OverlaySliderField
                          label="位置"
                          valueText={`Y ${Math.round(
                            overlayControls.progressYPercent ?? DEFAULT_OVERLAY_CONTROLS.progressYPercent
                          )}%`}
                          min={OVERLAY_POSITION_LIMITS.progressY.min}
                          max={OVERLAY_POSITION_LIMITS.progressY.max}
                          step={OVERLAY_POSITION_LIMITS.progressY.step}
                          value={
                            overlayControls.progressYPercent ??
                            OVERLAY_POSITION_LIMITS.progressY.defaultValue
                          }
                          disabled={renderBusy}
                          onChange={(value) =>
                            setOverlayControls((previous) => ({
                              ...previous,
                              progressYPercent: clampPercent(value),
                            }))
                          }
                        />
                      </div>
                    </section>

                    <section className="space-y-1 border-t border-slate-100 pt-1.5">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                        章节
                      </div>
                      <OverlaySliderField
                        label="章节块大小"
                        valueText={`${Math.round((overlayControls.chapterScale ?? 1) * 100)}%`}
                        min={OVERLAY_SCALE_LIMITS.chapter.min}
                        max={OVERLAY_SCALE_LIMITS.chapter.max}
                        step={OVERLAY_SCALE_LIMITS.chapter.step}
                        value={overlayControls.chapterScale ?? OVERLAY_SCALE_LIMITS.chapter.defaultValue}
                        disabled={renderBusy}
                        onChange={(value) =>
                          setOverlayControls((previous) => ({
                            ...previous,
                            chapterScale: Math.min(
                              Math.max(value, OVERLAY_SCALE_LIMITS.chapter.min),
                              OVERLAY_SCALE_LIMITS.chapter.max
                            ),
                          }))
                        }
                      />
                    </section>
                  </div>
                </div>

                <div className="border-t border-slate-200 bg-white px-3 py-2.5">
                  {renderBusy && (
                    <div className="mb-2.5 space-y-1.5">
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>导出进度</span>
                        <span>{Math.round(renderProgress)}%</span>
                      </div>
                      <Progress value={renderProgress} className="h-2" />
                    </div>
                  )}

                  <div className="grid gap-1.5">
                    <Button
                      type="button"
                      variant="outline"
                      className="w-full"
                      onClick={() => void prepareRenderPreview()}
                      disabled={busy || renderBusy || renderConfigBusy}
                    >
                      {renderConfigBusy ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 正在生成预览
                        </>
                      ) : (
                        "刷新预览"
                      )}
                    </Button>
                    <Button
                      type="button"
                      className="w-full"
                      onClick={() => void handleStartRender()}
                      disabled={renderBusy || busy || !hasRenderSource}
                    >
                      {renderBusy ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 正在导出
                        </>
                      ) : (
                        <>
                          <FileVideo className="mr-2 h-4 w-4" /> 导出视频
                        </>
                      )}
                    </Button>
                    {renderDownloadUrl && (
                    <Button
                      type="button"
                      variant="outline"
                      className="w-full"
                      onClick={() => triggerFileDownload(renderDownloadUrl, renderFileName)}
                    >
                        <Download className="mr-2 h-4 w-4" /> 下载上次导出
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

    </main>
  );
}
