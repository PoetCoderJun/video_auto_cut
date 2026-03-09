export type OverlayTypographyInput = {
  width: number;
  height: number;
};

export type OverlayTypography = {
  subtitleFontSize: number;
  subtitleBottom: number;
  subtitleSidePadding: number;
  subtitlePaddingX: number;
  subtitlePaddingY: number;
  subtitleRadius: number;
  subtitleMaxWidthRatio: number;
  subtitleSafeWidthRatio: number;
  chapterTop: number;
  chapterInsetX: number;
  chapterGap: number;
  chapterCardMinWidth: number;
  chapterCardMaxWidthRatio: number;
  chapterCardPaddingX: number;
  chapterCardPaddingY: number;
  chapterCardRadius: number;
  chapterMetaFontSize: number;
  chapterTitleFontSize: number;
  progressInsetX: number;
  progressBottom: number;
  progressHeight: number;
  progressRadius: number;
  progressLabelPaddingX: number;
  progressLabelFontSize: number;
  progressLabelMinWidth: number;
};

export type CaptionWrapInput = {
  width: number;
  fontSize: number;
  maxWidthRatio?: number;
  safeWidthRatio?: number;
};

const REFERENCE_WIDTH = 1920;
const REFERENCE_HEIGHT = 1080;
const REFERENCE_AREA = REFERENCE_WIDTH * REFERENCE_HEIGHT;
const SUBTITLE_SIZE_MULTIPLIER = 1.45;
const CJK_RE = /[\u2E80-\u9FFF\uF900-\uFAFF\u3040-\u30FF\uAC00-\uD7AF]/;
const BREAK_PUNCT_RE = /[，。！？；：、,.!?;:]/;

const clamp = (value: number, min: number, max: number): number => {
  if (value < min) return min;
  if (value > max) return max;
  return value;
};

const round = (value: number): number => Math.round(value);

const charUnits = (char: string): number => {
  if (char === " " || char === "\t") return 0.35;
  if (BREAK_PUNCT_RE.test(char)) return 0.6;
  if (/[0-9A-Za-z]/.test(char)) return 0.56;
  if (CJK_RE.test(char)) return 1;
  return 0.75;
};

const measureUnits = (text: string): number => {
  let total = 0;
  for (const char of text) total += charUnits(char);
  return total;
};

const findLastBreakPos = (text: string): number => {
  for (let i = text.length - 1; i >= 0; i -= 1) {
    if (BREAK_PUNCT_RE.test(text[i])) return i + 1;
  }
  return -1;
};

const wrapSoftLine = (text: string, maxUnits: number): string[] => {
  if (!text) return [""];

  const wrapped: string[] = [];
  let line = "";
  let units = 0;
  let lastBreakPos = -1;
  const minBreakPrefix = Math.max(4, Math.floor(maxUnits * 0.45));

  for (const char of text) {
    const nextUnits = charUnits(char);
    if (line && BREAK_PUNCT_RE.test(char) && units + nextUnits > maxUnits) {
      line += char;
      units += nextUnits;
      lastBreakPos = line.length;
      wrapped.push(line);
      line = "";
      units = 0;
      lastBreakPos = -1;
      continue;
    }

    while (line && units + nextUnits > maxUnits) {
      const breakPos = lastBreakPos >= minBreakPrefix ? lastBreakPos : -1;
      if (breakPos > 0 && breakPos < line.length) {
        wrapped.push(line.slice(0, breakPos));
        line = line.slice(breakPos).trimStart();
      } else {
        wrapped.push(line);
        line = "";
      }
      units = measureUnits(line);
      lastBreakPos = findLastBreakPos(line);
    }

    if (!line && char === " ") continue;
    line += char;
    units += nextUnits;
    if (BREAK_PUNCT_RE.test(char)) lastBreakPos = line.length;
  }

  if (line) wrapped.push(line);
  return wrapped.length > 0 ? wrapped : [""];
};

export const getResponsiveOverlayTypography = ({
  width,
  height,
}: OverlayTypographyInput): OverlayTypography => {
  const resolvedWidth = Math.max(1, width);
  const resolvedHeight = Math.max(1, height);
  const shortEdge = Math.min(resolvedWidth, resolvedHeight);
  const aspectRatio = resolvedWidth / resolvedHeight;
  const areaScale = Math.sqrt((resolvedWidth * resolvedHeight) / REFERENCE_AREA);
  const shortEdgeScale = shortEdge / REFERENCE_HEIGHT;
  const portraitStrength = clamp((0.82 - aspectRatio) / 0.32, 0, 1);

  // Use frame area as the baseline, then add a portrait boost so 9:16 exports
  // do not collapse into tiny fonts simply because the short edge is narrower.
  const layoutScale = clamp(areaScale * 0.72 + shortEdgeScale * 0.28 + portraitStrength * 0.18, 0.82, 1.18);
  const subtitleScale = clamp(layoutScale + portraitStrength * 0.08, 0.82, 1.22);
  const portraitSubtitleFontBoost = 1 + portraitStrength * 0.65;
  const portraitSubtitleVerticalBoost = 1 + portraitStrength * 1.25;
  const boostedSubtitleScale =
    subtitleScale * SUBTITLE_SIZE_MULTIPLIER * portraitSubtitleFontBoost;
  const chapterScale = clamp(layoutScale + portraitStrength * 0.03, 0.82, 1.14);
  const progressScale = clamp(layoutScale + portraitStrength * 0.06, 0.9, 1.18);

  return {
    subtitleFontSize: round(clamp(44 * boostedSubtitleScale, 46, 92)),
    subtitleBottom: round(clamp(resolvedHeight * (0.06 + portraitStrength * 0.018), 52, 138)),
    subtitleSidePadding: round(clamp(resolvedWidth * 0.028, 18, 42)),
    subtitlePaddingX: round(clamp(14 * boostedSubtitleScale, 16, 32)),
    subtitlePaddingY: round(clamp(8 * boostedSubtitleScale * portraitSubtitleVerticalBoost, 10, 36)),
    subtitleRadius: round(clamp(10 * boostedSubtitleScale, 10, 24)),
    subtitleMaxWidthRatio: clamp(0.88 + portraitStrength * 0.06, 0.88, 0.94),
    subtitleSafeWidthRatio: clamp(0.85 + portraitStrength * 0.05, 0.85, 0.9),
    chapterTop: round(clamp(resolvedHeight * 0.028, 22, 56)),
    chapterInsetX: round(clamp(resolvedWidth * 0.026, 20, 44)),
    chapterGap: round(clamp(6 * chapterScale, 5, 10)),
    chapterCardMinWidth: round(clamp(resolvedWidth * (0.28 + portraitStrength * 0.18), 280, 520)),
    chapterCardMaxWidthRatio: clamp(0.7 + portraitStrength * 0.1, 0.7, 0.8),
    chapterCardPaddingX: round(clamp(14 * chapterScale, 12, 20)),
    chapterCardPaddingY: round(clamp(12 * chapterScale, 10, 18)),
    chapterCardRadius: round(clamp(12 * chapterScale, 10, 18)),
    chapterMetaFontSize: round(clamp(18 * chapterScale, 16, 24)),
    chapterTitleFontSize: round(clamp(32 * chapterScale, 26, 40)),
    progressInsetX: round(clamp(resolvedWidth * 0.026, 20, 44)),
    progressBottom: round(clamp(resolvedHeight * 0.012, 10, 22)),
    progressHeight: round(clamp(42 * progressScale, 34, 52)),
    progressRadius: round(clamp(12 * progressScale, 10, 16)),
    progressLabelPaddingX: round(clamp(4 * progressScale, 3, 8)),
    progressLabelFontSize: round(clamp(13 * progressScale, 12, 17)),
    progressLabelMinWidth: round(clamp(resolvedWidth * 0.08, 54, 96)),
  };
};

export const shouldShowProgressSegmentLabel = ({
  containerWidth,
  segmentRatio,
  typography,
}: {
  containerWidth: number;
  segmentRatio: number;
  typography: OverlayTypography;
}): boolean => {
  if (!Number.isFinite(containerWidth) || !Number.isFinite(segmentRatio)) {
    return false;
  }
  return containerWidth * segmentRatio >= typography.progressLabelMinWidth;
};

export const wrapCaptionText = (rawText: string, input: CaptionWrapInput): string => {
  const normalized = (rawText || "").replace(/\r\n?/g, "\n").trim();
  if (!normalized) return "";

  const usableWidth = Math.max(260, input.width * (input.maxWidthRatio ?? 0.9));
  const safeWidthRatio = input.safeWidthRatio ?? 0.86;
  const maxUnits = Math.max(10, Math.floor((usableWidth * safeWidthRatio) / Math.max(1, input.fontSize)));

  const lines: string[] = [];
  for (const hardLine of normalized.split("\n")) {
    const trimmed = hardLine.trim();
    if (!trimmed) continue;
    lines.push(...wrapSoftLine(trimmed, maxUnits));
  }
  return lines.join("\n");
};
