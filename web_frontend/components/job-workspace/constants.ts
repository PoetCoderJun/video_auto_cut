import type {Job} from "../../lib/api.ts";

export const STEPS = [
  {id: 1, label: "上传视频"},
  {id: 2, label: "编辑字幕"},
  {id: 3, label: "导出视频"},
] as const;

export const CHAPTER_BADGE_COLORS = [
  "bg-blue-500",
  "bg-emerald-500",
  "bg-amber-500",
  "bg-red-500",
  "bg-violet-500",
  "bg-pink-500",
];

export const SUPPORTED_UPLOAD_EXTENSIONS = [
  ".mp4",
  ".mov",
  ".mkv",
  ".webm",
  ".m4v",
  ".ts",
  ".m2ts",
  ".mts",
];

export const SUPPORTED_UPLOAD_ACCEPT = SUPPORTED_UPLOAD_EXTENSIONS.join(",");

export const JOB_LOAD_RETRY_DELAY_MS = 4000;
export const RENDER_COMPLETE_RETRY_BASE_MS = 3000;
export const RENDER_COMPLETE_RETRY_MAX_MS = 120000;

export const TEST_VISUAL_PROGRESS_BY_STAGE: Record<string, number> = {
  UPLOAD_COMPLETE: 8,
  TEST_QUEUED: 12,
  TRANSCRIBING_AUDIO: 34,
  OPTIMIZING_TEXT: 56,
  REMOVING_REDUNDANT_LINES: 56,
  POLISHING_EXPRESSION: 84,
  PREPARING_TEST_REVIEW: 92,
  GENERATING_CHAPTERS: 96,
  TEST_READY: 100,
};

export const ACTIVE_STEP_BY_STATUS: Partial<Record<Job["status"], number>> = {
  CREATED: 1,
  UPLOAD_READY: 1,
  TEST_RUNNING: 2,
  TEST_READY: 2,
  TEST_CONFIRMED: 3,
  SUCCEEDED: 3,
};
