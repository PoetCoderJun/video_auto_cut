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

const scaleDimension = (value: number, factor: number, minimum: number): number =>
  Math.max(minimum, Math.round(value * factor));

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
  const subtitleFontSize = scaleDimension(
    typography.subtitleFontSize,
    normalized.subtitleScale,
    16
  );
  const progressLabelFontSize = scaleDimension(
    typography.progressLabelFontSize,
    normalized.progressScale,
    10
  );
  const chapterTitleFontSize = scaleDimension(
    typography.chapterTitleFontSize,
    normalized.chapterScale,
    16
  );
  const progressHeight = Math.max(
    scaleDimension(typography.progressHeight, normalized.progressScale, 18),
    Math.round(progressLabelFontSize * 2.25)
  );

  return {
    ...typography,
    subtitleFontSize,
    subtitlePaddingX: scaleDimension(typography.subtitlePaddingX, normalized.subtitleScale, 8),
    subtitlePaddingY: scaleDimension(typography.subtitlePaddingY, normalized.subtitleScale, 6),
    subtitleRadius: scaleDimension(typography.subtitleRadius, normalized.subtitleScale, 6),
    chapterGap: scaleDimension(typography.chapterGap, normalized.chapterScale, 6),
    chapterCardMinWidth: scaleDimension(
      typography.chapterCardMinWidth,
      normalized.chapterScale,
      120
    ),
    chapterCardPaddingX: scaleDimension(
      typography.chapterCardPaddingX,
      normalized.chapterScale,
      10
    ),
    chapterCardPaddingY: scaleDimension(
      typography.chapterCardPaddingY,
      normalized.chapterScale,
      8
    ),
    chapterCardRadius: scaleDimension(typography.chapterCardRadius, normalized.chapterScale, 10),
    chapterMetaFontSize: scaleDimension(
      typography.chapterMetaFontSize,
      normalized.chapterScale,
      12
    ),
    chapterTitleFontSize,
    progressHeight,
    progressRadius: scaleDimension(typography.progressRadius, normalized.progressScale, 8),
    progressLabelPaddingX: scaleDimension(
      typography.progressLabelPaddingX,
      normalized.progressScale,
      2
    ),
    progressLabelFontSize,
  };
};
