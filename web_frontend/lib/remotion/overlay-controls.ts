import type {OverlayTypography} from "./typography";

export type ProgressLabelMode = "auto" | "single" | "double";

export type OverlayScaleControls = {
  subtitleScale?: number;
  subtitleYPercent?: number;
  progressScale?: number;
  progressYPercent?: number;
  chapterScale?: number;
  showSubtitles?: boolean;
  showProgress?: boolean;
  showChapter?: boolean;
  progressLabelMode?: ProgressLabelMode;
};

export const OVERLAY_SCALE_LIMITS = {
  subtitle: {min: 0.7, max: 1.45, step: 0.01, defaultValue: 1},
  progress: {min: 0.7, max: 1.6, step: 0.01, defaultValue: 1},
  chapter: {min: 0.7, max: 1.45, step: 0.01, defaultValue: 1},
} as const;

export const OVERLAY_POSITION_LIMITS = {
  subtitleY: {min: 0, max: 100, step: 1, defaultValue: 90},
  progressY: {min: 0, max: 100, step: 1, defaultValue: 97},
} as const;

export const DEFAULT_OVERLAY_CONTROLS: Required<OverlayScaleControls> = {
  subtitleScale: OVERLAY_SCALE_LIMITS.subtitle.defaultValue,
  subtitleYPercent: OVERLAY_POSITION_LIMITS.subtitleY.defaultValue,
  progressScale: OVERLAY_SCALE_LIMITS.progress.defaultValue,
  progressYPercent: OVERLAY_POSITION_LIMITS.progressY.defaultValue,
  chapterScale: OVERLAY_SCALE_LIMITS.chapter.defaultValue,
  showSubtitles: true,
  showProgress: true,
  showChapter: true,
  progressLabelMode: "auto",
};

const PROGRESS_LABEL_MODE_VALUES: readonly ProgressLabelMode[] = ["auto", "single", "double"];

function isFiniteOverlayNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isProgressLabelMode(value: unknown): value is ProgressLabelMode {
  return PROGRESS_LABEL_MODE_VALUES.includes(value as ProgressLabelMode);
}

export function normalizeOverlayControlNumber(
  value: unknown,
  defaultValue: number,
  limits: {min: number; max: number}
): number {
  const resolvedValue = isFiniteOverlayNumber(value) ? value : defaultValue;
  if (resolvedValue < limits.min) return limits.min;
  if (resolvedValue > limits.max) return limits.max;
  return resolvedValue;
}

const roundToStep = (value: number, step = 1): number => {
  const resolvedStep = Number.isFinite(step) && step > 0 ? step : 1;
  return Math.round(value / resolvedStep) * resolvedStep;
};

const emphasizeScale = (factor: number, strength: number, min: number, max: number): number =>
  normalizeOverlayControlNumber(1 + (factor - 1) * strength, min, {min, max});

const scaleDimension = (
  value: number,
  factor: number,
  minimum: number,
  precisionStep = 1
): number => Math.max(minimum, roundToStep(value * factor, precisionStep));

export const normalizeOverlayScaleControls = (
  controls: OverlayScaleControls
): Required<OverlayScaleControls> => ({
  subtitleScale: normalizeOverlayControlNumber(
    controls.subtitleScale,
    DEFAULT_OVERLAY_CONTROLS.subtitleScale,
    OVERLAY_SCALE_LIMITS.subtitle
  ),
  subtitleYPercent: normalizeOverlayControlNumber(
    controls.subtitleYPercent,
    DEFAULT_OVERLAY_CONTROLS.subtitleYPercent,
    OVERLAY_POSITION_LIMITS.subtitleY
  ),
  progressScale: normalizeOverlayControlNumber(
    controls.progressScale,
    DEFAULT_OVERLAY_CONTROLS.progressScale,
    OVERLAY_SCALE_LIMITS.progress
  ),
  progressYPercent: normalizeOverlayControlNumber(
    controls.progressYPercent,
    DEFAULT_OVERLAY_CONTROLS.progressYPercent,
    OVERLAY_POSITION_LIMITS.progressY
  ),
  chapterScale: normalizeOverlayControlNumber(
    controls.chapterScale,
    DEFAULT_OVERLAY_CONTROLS.chapterScale,
    OVERLAY_SCALE_LIMITS.chapter
  ),
  showSubtitles:
    typeof controls.showSubtitles === "boolean"
      ? controls.showSubtitles
      : DEFAULT_OVERLAY_CONTROLS.showSubtitles,
  showProgress:
    typeof controls.showProgress === "boolean"
      ? controls.showProgress
      : DEFAULT_OVERLAY_CONTROLS.showProgress,
  showChapter:
    typeof controls.showChapter === "boolean"
      ? controls.showChapter
      : DEFAULT_OVERLAY_CONTROLS.showChapter,
  progressLabelMode: isProgressLabelMode(controls.progressLabelMode)
    ? controls.progressLabelMode
    : DEFAULT_OVERLAY_CONTROLS.progressLabelMode,
});

export const resolveOverlayAnchorBottom = ({
  frameHeight,
  baselineBottom,
  currentPercent,
  defaultPercent,
}: {
  frameHeight: number;
  baselineBottom: number;
  currentPercent: number;
  defaultPercent: number;
}): number => {
  const resolvedHeight = Math.max(1, frameHeight);
  const deltaPercent = defaultPercent - currentPercent;
  return Math.max(0, roundToStep(baselineBottom + (resolvedHeight * deltaPercent) / 100, 0.25));
};

export const applyOverlayScaleToTypography = (
  typography: OverlayTypography,
  controls: OverlayScaleControls
): OverlayTypography => {
  const normalized = normalizeOverlayScaleControls(controls);
  const progressVisualScale = emphasizeScale(normalized.progressScale, 1.35, 0.55, 2.05);
  const progressTypeScale = emphasizeScale(normalized.progressScale, 1.65, 0.5, 2.15);
  const progressInsetScale = normalizeOverlayControlNumber(
    1 - (progressVisualScale - 1) * 0.28,
    0.72,
    {min: 0.72, max: 1.18}
  );
  const subtitleFontSize = scaleDimension(typography.subtitleFontSize, normalized.subtitleScale, 16);
  const progressLabelFontSize = scaleDimension(
    typography.progressLabelFontSize,
    progressTypeScale,
    10,
    0.25
  );
  const chapterTitleFontSize = scaleDimension(
    typography.chapterTitleFontSize,
    normalized.chapterScale,
    16,
    0.25
  );
  const progressHeight = Math.max(
    scaleDimension(typography.progressHeight, progressVisualScale, 18, 0.25),
    Math.round(progressLabelFontSize * 2.4)
  );

  return {
    ...typography,
    subtitleFontSize,
    subtitlePaddingX: scaleDimension(typography.subtitlePaddingX, normalized.subtitleScale, 8),
    subtitlePaddingY: scaleDimension(typography.subtitlePaddingY, normalized.subtitleScale, 6),
    subtitleRadius: scaleDimension(typography.subtitleRadius, normalized.subtitleScale, 6),
    chapterGap: scaleDimension(typography.chapterGap, normalized.chapterScale, 4.5, 0.25),
    chapterCardMinWidth: scaleDimension(
      typography.chapterCardMinWidth,
      normalized.chapterScale,
      120,
      0.5
    ),
    chapterCardPaddingX: scaleDimension(
      typography.chapterCardPaddingX,
      normalized.chapterScale,
      9,
      0.25
    ),
    chapterCardPaddingY: scaleDimension(
      typography.chapterCardPaddingY,
      normalized.chapterScale,
      7.5,
      0.25
    ),
    chapterCardRadius: scaleDimension(
      typography.chapterCardRadius,
      normalized.chapterScale,
      8.5,
      0.25
    ),
    chapterMetaFontSize: scaleDimension(
      typography.chapterMetaFontSize,
      normalized.chapterScale,
      12,
      0.25
    ),
    chapterTitleFontSize,
    progressInsetX: scaleDimension(typography.progressInsetX, progressInsetScale, 12, 0.25),
    progressBottom: scaleDimension(typography.progressBottom, progressVisualScale, 8, 0.25),
    progressHeight,
    progressRadius: scaleDimension(typography.progressRadius, progressVisualScale, 8, 0.25),
    progressLabelPaddingX: scaleDimension(
      typography.progressLabelPaddingX,
      emphasizeScale(normalized.progressScale, 0.6, 0.72, 1.4),
      2,
      0.25
    ),
    progressLabelFontSize,
  };
};
