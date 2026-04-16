import type {Job} from "../../lib/api.ts";
import {STATUS} from "../../lib/workflow.ts";
import {clamp} from "../../lib/utils.ts";

import {
  ACTIVE_STEP_BY_STATUS,
  TEST_VISUAL_PROGRESS_BY_STAGE,
} from "./constants.ts";

export type JobWorkspaceView =
  | "upload"
  | "processing"
  | "editor"
  | "export";

function clampPercent(value: number): number {
  return clamp(value, 0, 100);
}

export function getActiveStep(status: Job["status"]): number {
  return ACTIVE_STEP_BY_STATUS[status] ?? 1;
}

export function getJobWorkspaceView(
  status: Job["status"],
  testReadyHandoffActive: boolean,
): JobWorkspaceView {
  if (status === STATUS.CREATED) {
    return "upload";
  }

  if (
    status === STATUS.UPLOAD_READY ||
    status === STATUS.TEST_RUNNING ||
    (status === STATUS.TEST_READY && testReadyHandoffActive)
  ) {
    return "processing";
  }

  if (status === STATUS.TEST_READY) {
    return "editor";
  }

  return "export";
}

export function getTestVisualProgress(job: Job): number {
  if (job.status === STATUS.TEST_READY) {
    return 100;
  }

  const stageCode = String(job.stage?.code || "").trim();
  const stageProgress = TEST_VISUAL_PROGRESS_BY_STAGE[stageCode];
  if (typeof stageProgress === "number") {
    return stageProgress;
  }

  if (job.status === STATUS.UPLOAD_READY || job.status === STATUS.TEST_RUNNING) {
    const normalized =
      ((Math.max(30, Math.min(35, job.progress)) - 30) / 5) * 100;
    return clampPercent(
      Math.max(normalized, job.status === STATUS.UPLOAD_READY ? 8 : 24),
    );
  }

  return clampPercent(job.progress);
}

export function shouldShowTestSubtitlePreview(
  stageCode: string | null | undefined,
): boolean {
  switch (String(stageCode || "").trim()) {
    case "OPTIMIZING_TEXT":
    case "REMOVING_REDUNDANT_LINES":
    case "POLISHING_EXPRESSION":
    case "PREPARING_TEST_REVIEW":
    case "GENERATING_CHAPTERS":
    case "TEST_READY":
      return true;
    default:
      return false;
  }
}

export function getTestProcessingNote(
  stageCode: string | null | undefined,
): string {
  switch (String(stageCode || "").trim()) {
    case "TEST_QUEUED":
      return "任务已入队，马上开始识别语音并整理字幕。";
    case "TRANSCRIBING_AUDIO":
      return "先生成初版字幕，完成后会继续自动处理。";
    case "OPTIMIZING_TEXT":
    case "REMOVING_REDUNDANT_LINES":
      return "正在筛掉口误、重复句和回头修正。";
    case "POLISHING_EXPRESSION":
      return "正在按上下文润色字幕，让表达更自然。";
    case "PREPARING_TEST_REVIEW":
      return "正在整理成可编辑字幕。";
    case "GENERATING_CHAPTERS":
      return "正在把章节整理成时间线分隔符。";
    case "TEST_READY":
      return "字幕和章节已经整理完成，正在进入编辑页面。";
    default:
      return "任务已启动，正在进入字幕处理流程。";
  }
}

export function getTestProcessingTitle(
  stageCode: string | null | undefined,
  stageMessage: string | null | undefined,
): string {
  const trimmedMessage = String(stageMessage || "").trim();
  switch (String(stageCode || "").trim()) {
    case "TEST_QUEUED":
      return "正在启动字幕任务";
    case "TRANSCRIBING_AUDIO":
      return "正在识别语音";
    case "OPTIMIZING_TEXT":
    case "REMOVING_REDUNDANT_LINES":
      return "正在筛除冗余字幕";
    case "POLISHING_EXPRESSION":
      return "正在润色字幕";
    case "PREPARING_TEST_REVIEW":
      return "正在整理字幕结果";
    case "GENERATING_CHAPTERS":
      return "正在生成章节分隔";
    case "TEST_READY":
      return "正在进入编辑页";
    default:
      return trimmedMessage || "正在提取字幕";
  }
}
