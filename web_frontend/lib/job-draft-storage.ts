import type {Chapter, Step1Line, SubtitleTheme} from "./api";
import {
  DEFAULT_OVERLAY_CONTROLS,
  normalizeOverlayScaleControls,
  type OverlayScaleControls,
  type ProgressLabelMode,
} from "./remotion/overlay-controls.ts";

const STEP1_DRAFT_PREFIX = "video_auto_cut_step1_draft:";
const EXPORT_PREFS_STORAGE_KEY = "video_auto_cut_export_preferences";
const DRAFT_SCHEMA_VERSION = 1;
const EXPORT_PREFS_SCHEMA_VERSION = 1;
const SUBTITLE_THEME_VALUES: readonly SubtitleTheme[] = [
  "text-black",
  "text-white",
  "box-white-on-black",
  "box-black-on-white",
];

const PROGRESS_LABEL_MODE_VALUES: readonly ProgressLabelMode[] = ["auto", "single", "double"];

type Step1DraftPayload = {
  version: number;
  updatedAt: number;
  lines: Step1Line[];
  chapters: Chapter[];
  documentRevision: string;
};

type ExportPreferencesPayload = {
  version: number;
  updatedAt: number;
  subtitleTheme: SubtitleTheme;
  overlayControls: Required<OverlayScaleControls>;
};

export type ExportPreferences = {
  subtitleTheme: SubtitleTheme;
  overlayControls: Required<OverlayScaleControls>;
};

export type Step1DraftDocument = {
  lines: Step1Line[];
  chapters: Chapter[];
  documentRevision: string;
};

function getStorage(): Storage | null {
  if (typeof window === "undefined" || !window.localStorage) {
    return null;
  }
  return window.localStorage;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  if (value < min) return min;
  if (value > max) return max;
  return value;
}

function isSubtitleTheme(value: unknown): value is SubtitleTheme {
  return SUBTITLE_THEME_VALUES.includes(value as SubtitleTheme);
}

function isProgressLabelMode(value: unknown): value is ProgressLabelMode {
  return PROGRESS_LABEL_MODE_VALUES.includes(value as ProgressLabelMode);
}

function normalizeOverlayControls(value: unknown): Required<OverlayScaleControls> {
  const source = value && typeof value === "object" ? (value as OverlayScaleControls) : {};
  return normalizeOverlayScaleControls(source);
}

function normalizeStep1Lines(value: unknown): Step1Line[] {
  if (!Array.isArray(value)) return [];
  const lines: Step1Line[] = [];
  for (const row of value) {
    if (!row || typeof row !== "object") continue;
    const line = row as Record<string, unknown>;
    if (
      !isFiniteNumber(line.line_id) ||
      !isFiniteNumber(line.start) ||
      !isFiniteNumber(line.end)
    ) {
      continue;
    }
    lines.push({
      line_id: Math.trunc(line.line_id),
      start: line.start,
      end: line.end,
      original_text: String(line.original_text ?? ""),
      optimized_text: String(line.optimized_text ?? ""),
      ai_suggest_remove: Boolean(line.ai_suggest_remove),
      user_final_remove: Boolean(line.user_final_remove),
    });
  }
  return lines.sort((left, right) => left.line_id - right.line_id);
}

function normalizeChapters(value: unknown): Chapter[] {
  if (!Array.isArray(value)) return [];
  const chapters: Chapter[] = [];
  for (const row of value) {
    if (!row || typeof row !== "object") continue;
    const chapter = row as Record<string, unknown>;
    if (
      !isFiniteNumber(chapter.chapter_id) ||
      !isFiniteNumber(chapter.start) ||
      !isFiniteNumber(chapter.end)
    ) {
      continue;
    }
    chapters.push({
      chapter_id: Math.trunc(chapter.chapter_id),
      title: String(chapter.title ?? ""),
      start: chapter.start,
      end: chapter.end,
      block_range: String(chapter.block_range ?? ""),
    });
  }
  return chapters.sort((left, right) => left.chapter_id - right.chapter_id);
}

function readJson<T>(key: string): T | null {
  const storage = getStorage();
  if (!storage) return null;
  const raw = storage.getItem(key);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    storage.removeItem(key);
    return null;
  }
}

function writeJson(key: string, value: object): void {
  const storage = getStorage();
  if (!storage) return;
  storage.setItem(key, JSON.stringify(value));
}

function removeKey(key: string): void {
  const storage = getStorage();
  if (!storage) return;
  storage.removeItem(key);
}

function exportPrefsKey(): string {
  return EXPORT_PREFS_STORAGE_KEY;
}

function step1Key(jobId: string): string {
  return `${STEP1_DRAFT_PREFIX}${jobId}`;
}

export function saveStep1Draft(jobId: string, document: Step1DraftDocument): void {
  if (!jobId || document.lines.length === 0) return;
  writeJson(step1Key(jobId), {
    version: DRAFT_SCHEMA_VERSION,
    updatedAt: Date.now(),
    lines: document.lines,
    chapters: document.chapters,
    documentRevision: String(document.documentRevision || ""),
  } satisfies Step1DraftPayload);
}

export function loadStep1Draft(jobId: string): Step1DraftDocument | null {
  if (!jobId) return null;
  const payload = readJson<Step1DraftPayload>(step1Key(jobId));
  if (!payload || payload.version !== DRAFT_SCHEMA_VERSION) return null;
  const lines = normalizeStep1Lines(payload.lines);
  if (lines.length === 0) return null;
  return {
    lines,
    chapters: normalizeChapters(payload.chapters),
    documentRevision: String(payload.documentRevision || ""),
  };
}

export function clearStep1Draft(jobId: string): void {
  if (!jobId) return;
  removeKey(step1Key(jobId));
}

export function saveExportPreferences(
  preferences: Pick<ExportPreferences, "subtitleTheme"> & {overlayControls: OverlayScaleControls}
): void {
  writeJson(exportPrefsKey(), {
    version: EXPORT_PREFS_SCHEMA_VERSION,
    updatedAt: Date.now(),
    subtitleTheme: isSubtitleTheme(preferences.subtitleTheme)
      ? preferences.subtitleTheme
      : "box-white-on-black",
    overlayControls: normalizeOverlayControls(preferences.overlayControls),
  } satisfies ExportPreferencesPayload);
}

export function loadExportPreferences(): ExportPreferences | null {
  const payload = readJson<ExportPreferencesPayload>(exportPrefsKey());
  if (!payload || payload.version !== EXPORT_PREFS_SCHEMA_VERSION) return null;

  return {
    subtitleTheme: isSubtitleTheme(payload.subtitleTheme)
      ? payload.subtitleTheme
      : "box-white-on-black",
    overlayControls: normalizeOverlayControls(payload.overlayControls),
  };
}

export function clearExportPreferences(): void {
  removeKey(exportPrefsKey());
}

export function mergeStep1Draft(
  serverDocument: Step1DraftDocument,
  draftDocument: Step1DraftDocument | null
): Step1DraftDocument {
  if (!draftDocument || draftDocument.lines.length === 0) return serverDocument;
  const byId = new Map(draftDocument.lines.map((line) => [line.line_id, line] as const));
  let linesChanged = false;
  const mergedLines = serverDocument.lines.map((line) => {
    const draft = byId.get(line.line_id);
    if (!draft) return line;
    if (
      draft.optimized_text === line.optimized_text &&
      draft.user_final_remove === line.user_final_remove
    ) {
      return line;
    }
    linesChanged = true;
    return {
      ...line,
      optimized_text: draft.optimized_text,
      user_final_remove: draft.user_final_remove,
    };
  });
  const draftChapters = normalizeChapters(draftDocument.chapters);
  const byChapterId = new Map(draftChapters.map((chapter) => [chapter.chapter_id, chapter] as const));
  let chaptersChanged = false;
  const mergedChapters = serverDocument.chapters.map((chapter) => {
    const draft = byChapterId.get(chapter.chapter_id);
    if (!draft) return chapter;
    if (draft.title === chapter.title && draft.block_range === chapter.block_range) {
      return chapter;
    }
    chaptersChanged = true;
    return {
      ...chapter,
      title: draft.title,
      block_range: draft.block_range,
    };
  });
  if (
    !linesChanged &&
    !chaptersChanged &&
    draftDocument.documentRevision === serverDocument.documentRevision
  ) {
    return serverDocument;
  }
  return {
    lines: linesChanged ? mergedLines : serverDocument.lines,
    chapters: chaptersChanged ? mergedChapters : serverDocument.chapters,
    documentRevision:
      draftDocument.documentRevision || serverDocument.documentRevision,
  };
}
