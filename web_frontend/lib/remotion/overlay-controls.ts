import type {OverlayTypography} from "./typography";

export type ProgressLabelMode = "auto" | "single" | "double";

export type OverlayScaleControls = {
  subtitleScale?: number;
  progressScale?: number;
  chapterScale?: number;
  progressLabelMode?: ProgressLabelMode;
};

export const OVERLAY_SCALE_LIMITS = {
  subtitle: {min: 0.7, max: 1.45, step: 0.01, defaultValue: 1},
  progress: {min: 0.7, max: 1.6, step: 0.01, defaultValue: 1},
  chapter: {min: 0.7, max: 1.45, step: 0.01, defaultValue: 1},
} as const;

const clamp = (value: number, min: number, max: number): number => {
  if (!Number.isFinite(value)) return min;
  if (value < min) return min;
  if (value > max) return max;
  return value;
};

const roundToStep = (value: number, step = 1): number => {
  const resolvedStep = Number.isFinite(step) && step > 0 ? step : 1;
  return Math.round(value / resolvedStep) * resolvedStep;
};

const emphasizeScale = (factor: number, strength: number, min: number, max: number): number =>
  clamp(1 + (factor - 1) * strength, min, max);

const scaleDimension = (
  value: number,
  factor: number,
  minimum: number,
  precisionStep = 1
): number => Math.max(minimum, roundToStep(value * factor, precisionStep));

export const normalizeOverlayScaleControls = (
  controls: OverlayScaleControls
): {subtitleScale: number; progressScale: number; chapterScale: number} => ({
  subtitleScale: clamp(
    controls.subtitleScale ?? OVERLAY_SCALE_LIMITS.subtitle.defaultValue,
    OVERLAY_SCALE_LIMITS.subtitle.min,
    OVERLAY_SCALE_LIMITS.subtitle.max
  ),
  progressScale: clamp(
    controls.progressScale ?? OVERLAY_SCALE_LIMITS.progress.defaultValue,
    OVERLAY_SCALE_LIMITS.progress.min,
    OVERLAY_SCALE_LIMITS.progress.max
  ),
  chapterScale: clamp(
    controls.chapterScale ?? OVERLAY_SCALE_LIMITS.chapter.defaultValue,
    OVERLAY_SCALE_LIMITS.chapter.min,
    OVERLAY_SCALE_LIMITS.chapter.max
  ),
});

export const applyOverlayScaleToTypography = (
  typography: OverlayTypography,
  controls: OverlayScaleControls
): OverlayTypography => {
  const normalized = normalizeOverlayScaleControls(controls);
  const progressVisualScale = emphasizeScale(normalized.progressScale, 1.35, 0.55, 2.05);
  const progressTypeScale = emphasizeScale(normalized.progressScale, 1.65, 0.5, 2.15);
  const progressInsetScale = clamp(1 - (progressVisualScale - 1) * 0.28, 0.72, 1.18);
  const subtitleFontSize = scaleDimension(
    typography.subtitleFontSize,
    normalized.subtitleScale,
    16
  );
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
    chapterCardRadius: scaleDimension(typography.chapterCardRadius, normalized.chapterScale, 8.5, 0.25),
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
