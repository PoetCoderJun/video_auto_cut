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
};

export type CaptionWrapInput = {
  width: number;
  fontSize: number;
  maxWidthRatio?: number;
  safeWidthRatio?: number;
  fontWeight?: number;
  fontFamily?: string;
};

export type FitTextToBoxInput = {
  text: string;
  maxWidth: number;
  baseFontSize: number;
  minFontSize: number;
  maxLines: number;
  fontWeight?: number;
  fontFamily?: string;
};

export type FittedTextBox = {
  fontSize: number;
  lines: string[];
  text: string;
  truncated: boolean;
};

export type AdaptiveFittedTextBox = FittedTextBox & {
  maxLines: number;
};

export type DomSubtitleLayout = {
  fontSize: number;
  maxLines: number;
};

export type FitSingleLineTextInput = {
  text: string;
  maxWidth: number;
  baseFontSize: number;
  minFontSize: number;
  horizontalPadding?: number;
  maxFontSize?: number;
  maxHeight?: number;
  lineHeight?: number;
  targetWidthRatio?: number;
  fontWeight?: number;
  fontFamily?: string;
};

export type FittedSingleLineText = {
  fontSize: number;
  visible: boolean;
};

export type FitUniformSingleLineTextItem = {
  text: string;
  maxWidth: number;
};

export type FitUniformSingleLineTextInput = {
  items: FitUniformSingleLineTextItem[];
  baseFontSize: number;
  minFontSize: number;
  horizontalPadding?: number;
  maxFontSize?: number;
  maxHeight?: number;
  lineHeight?: number;
  targetWidthRatio?: number;
  fontWeight?: number;
  fontFamily?: string;
};

export type FittedUniformSingleLineText = {
  fontSize: number;
  labels: Array<{visible: boolean}>;
};

export type FitUniformTextBoxItem = {
  text: string;
  maxWidth: number;
};

export type FitUniformTextBoxInput = {
  items: FitUniformTextBoxItem[];
  baseFontSize: number;
  minFontSize: number;
  maxLines: number;
  horizontalPadding?: number;
  maxFontSize?: number;
  maxHeight?: number;
  lineHeight?: number;
  targetWidthRatio?: number;
  fontWeight?: number;
  fontFamily?: string;
};

export type FittedUniformTextBox = {
  fontSize: number;
  labels: Array<{
    visible: boolean;
    text: string;
    lines: string[];
    truncated: boolean;
  }>;
};

export type FittedUniformAdaptiveTextBox = FittedUniformTextBox & {
  maxLines: number;
};

const REFERENCE_WIDTH = 1920;
const REFERENCE_HEIGHT = 1080;
const SUBTITLE_SIZE_MULTIPLIER = 1.45 * 0.65;
const SCALE_EXPONENT = 0.72;
export const OVERLAY_FONT_FAMILY = [
  '"Noto Sans SC"',
  '"Noto Sans CJK SC"',
  '"Source Han Sans SC"',
  '"PingFang SC"',
  '"Hiragino Sans GB"',
  '"Microsoft YaHei"',
  '"微软雅黑"',
  '"Heiti SC"',
  '"WenQuanYi Micro Hei"',
  "sans-serif",
].join(", ");
const DEFAULT_FONT_FAMILY = OVERLAY_FONT_FAMILY;
const CJK_RE = /[\u2E80-\u9FFF\uF900-\uFAFF\u3040-\u30FF\uAC00-\uD7AF]/;
const BREAK_PUNCT_RE = /[，。！？；：、,.!?;:…—]/;
const EM_DASH_RE = /[—―－]/;
const EM_DASH_SEQUENCE_RE = /(?:[—―－]+|--+)/g;

const clamp = (value: number, min: number, max: number): number => {
  if (value < min) return min;
  if (value > max) return max;
  return value;
};

const round = (value: number): number => Math.round(value);
const atLeast = (value: number, min: number): number => Math.max(min, value);

const scaleFromReference = (value: number, reference: number): number =>
  Math.pow(Math.max(1, value) / reference, SCALE_EXPONENT);

const scaleDimension = (base: number, scale: number, min: number): number =>
  atLeast(round(base * scale), min);

let measurementContext:
  | CanvasRenderingContext2D
  | OffscreenCanvasRenderingContext2D
  | null
  | undefined;
const textWidthCache = new Map<string, number>();

const charUnits = (char: string): number => {
  if (char === " " || char === "\t") return 0.35;
  if (EM_DASH_RE.test(char)) return 1.05;
  if (char === "…") return 1;
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

export const normalizeCaptionDisplayText = (text: string): string =>
  (text || "").replace(EM_DASH_SEQUENCE_RE, "：");

const ASCII_WORD_RE = /[0-9A-Za-z]/;

export const prepareCaptionDisplayText = (rawText: string): string => {
  const normalized = normalizeCaptionDisplayText((rawText || "").replace(/\r\n?/g, "\n"));
  let flattened = "";

  for (let i = 0; i < normalized.length; i += 1) {
    const char = normalized[i];
    if (char !== "\n") {
      flattened += char;
      continue;
    }

    const prev = flattened.at(-1) ?? "";
    let next = "";
    for (let j = i + 1; j < normalized.length; j += 1) {
      const candidate = normalized[j];
      if (candidate === "\n") continue;
      if (!/\s/.test(candidate)) {
        next = candidate;
        break;
      }
    }

    if ((ASCII_WORD_RE.test(prev) || ASCII_WORD_RE.test(next)) && !flattened.endsWith(" ")) {
      flattened += " ";
    }
  }

  return flattened.replace(/[ \t\u3000]+/g, " ").trim();
};

const findLastBreakPos = (text: string): number => {
  for (let i = text.length - 1; i >= 0; i -= 1) {
    if (BREAK_PUNCT_RE.test(text[i])) return i + 1;
  }
  return -1;
};

const isSoftBreakChar = (char: string): boolean =>
  /\s/.test(char) || BREAK_PUNCT_RE.test(char) || char === "/" || char === "-" || char === "·";

const findMeasuredBreakPos = (text: string): number => {
  for (let i = text.length - 1; i >= 0; i -= 1) {
    const char = text[i];
    if (/\s/.test(char)) return i;
    if (isSoftBreakChar(char)) return i + 1;
  }
  return -1;
};

const getMeasurementContext = ():
  | CanvasRenderingContext2D
  | OffscreenCanvasRenderingContext2D
  | null => {
  if (measurementContext !== undefined) return measurementContext;

  if (typeof OffscreenCanvas !== "undefined") {
    measurementContext = new OffscreenCanvas(1, 1).getContext("2d");
    return measurementContext;
  }

  if (typeof document !== "undefined") {
    measurementContext = document.createElement("canvas").getContext("2d");
    return measurementContext;
  }

  measurementContext = null;
  return measurementContext;
};

const buildFontSpec = ({
  fontSize,
  fontWeight = 400,
  fontFamily = DEFAULT_FONT_FAMILY,
}: {
  fontSize: number;
  fontWeight?: number;
  fontFamily?: string;
}): string => `${fontWeight} ${Math.max(1, round(fontSize))}px ${fontFamily}`;

const measureTextWidth = ({
  text,
  fontSize,
  fontWeight = 400,
  fontFamily = DEFAULT_FONT_FAMILY,
}: {
  text: string;
  fontSize: number;
  fontWeight?: number;
  fontFamily?: string;
}): number => {
  const normalized = text || "";
  if (!normalized) return 0;

  const roundedFontSize = Math.max(1, round(fontSize));
  const cacheKey = `${fontWeight}|${roundedFontSize}|${fontFamily}|${normalized}`;
  const cached = textWidthCache.get(cacheKey);
  if (cached !== undefined) return cached;

  const ctx = getMeasurementContext();
  let width = 0;
  if (ctx) {
    ctx.font = buildFontSpec({fontSize: roundedFontSize, fontWeight, fontFamily});
    width = ctx.measureText(normalized).width;
  } else {
    width = measureUnits(normalized) * roundedFontSize * 1.02;
  }

  textWidthCache.set(cacheKey, width);
  return width;
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

const wrapTextByWidth = ({
  text,
  maxWidth,
  fontSize,
  fontWeight = 400,
  fontFamily = DEFAULT_FONT_FAMILY,
}: {
  text: string;
  maxWidth: number;
  fontSize: number;
  fontWeight?: number;
  fontFamily?: string;
}): string[] => {
  const normalized = (text || "").trim();
  if (!normalized) return [""];

  const resolvedMaxWidth = Math.max(1, maxWidth);
  const lines: string[] = [];
  let line = "";

  for (const char of normalized) {
    if (!line && /\s/.test(char)) continue;
    const candidate = `${line}${char}`;
    if (line && measureTextWidth({text: candidate, fontSize, fontWeight, fontFamily}) > resolvedMaxWidth) {
      const breakPos = findMeasuredBreakPos(line);
      if (breakPos > 0 && breakPos < line.length) {
        const head = line.slice(0, breakPos).trimEnd();
        const tail = line.slice(breakPos).trimStart();
        lines.push(head || line.trimEnd() || line);
        line = `${tail}${char}`.trimStart();
      } else {
        lines.push(line.trimEnd() || line);
        line = /\s/.test(char) ? "" : char;
      }
      continue;
    }

    line = candidate;
  }

  if (line) lines.push(line.trimEnd());
  return lines.length > 0 ? lines : [""];
};

const layoutTextLines = ({
  text,
  maxWidth,
  fontSize,
  fontWeight = 400,
  fontFamily = DEFAULT_FONT_FAMILY,
}: {
  text: string;
  maxWidth: number;
  fontSize: number;
  fontWeight?: number;
  fontFamily?: string;
}): string[] => {
  const normalized = (text || "").replace(/\r\n?/g, "\n").trim();
  if (!normalized) return [""];

  const lines: string[] = [];
  for (const hardLine of normalized.split("\n")) {
    const trimmed = hardLine.trim();
    if (!trimmed) continue;
    lines.push(
      ...wrapTextByWidth({
        text: trimmed,
        maxWidth,
        fontSize,
        fontWeight,
        fontFamily,
      })
    );
  }
  return lines.length > 0 ? lines : [""];
};

const ellipsizeToWidth = ({
  text,
  maxWidth,
  fontSize,
  fontWeight = 400,
  fontFamily = DEFAULT_FONT_FAMILY,
}: {
  text: string;
  maxWidth: number;
  fontSize: number;
  fontWeight?: number;
  fontFamily?: string;
}): string => {
  const normalized = (text || "").trim();
  if (!normalized) return "";
  if (measureTextWidth({text: normalized, fontSize, fontWeight, fontFamily}) <= maxWidth) {
    return normalized;
  }

  let low = 0;
  let high = normalized.length;
  let best = "…";

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const candidate = `${normalized.slice(0, mid).trimEnd()}…`;
    if (measureTextWidth({text: candidate, fontSize, fontWeight, fontFamily}) <= maxWidth) {
      best = candidate;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  return best;
};

export const getResponsiveOverlayTypography = ({
  width,
  height,
}: OverlayTypographyInput): OverlayTypography => {
  const resolvedWidth = Math.max(1, width);
  const resolvedHeight = Math.max(1, height);
  const aspectRatio = resolvedWidth / resolvedHeight;
  const portraitStrength = clamp((0.82 - aspectRatio) / 0.32, 0, 1);
  const verticalScale = scaleFromReference(resolvedHeight, REFERENCE_HEIGHT);
  const horizontalScale = scaleFromReference(resolvedWidth, REFERENCE_WIDTH);

  // Subtitle size still scales with frame height, but portrait exports need a
  // gentler boost than before. Otherwise narrow frames like 720x1268 can end
  // up with oversized captions that only fit after browser layout overflow.
  const subtitleScale = verticalScale * (1 + portraitStrength * 0.18);
  const subtitleVerticalScale = subtitleScale * (1 + portraitStrength * 0.8);
  const chapterScale = verticalScale * (1 + portraitStrength * 0.14);
  const progressScale = verticalScale * (1 + portraitStrength * 0.18);
  const chapterWidthScale = horizontalScale * (1 + portraitStrength * 0.28);
  const progressLabelFontSize = scaleDimension(18.2, progressScale, 17);
  const progressHeight = atLeast(scaleDimension(42, progressScale, 34), round(progressLabelFontSize * 2.25));
  const progressRadius = atLeast(scaleDimension(12, progressScale, 10), round(progressHeight * 0.28));

  return {
    subtitleFontSize: scaleDimension(44 * SUBTITLE_SIZE_MULTIPLIER, subtitleScale, 30),
    subtitleBottom: atLeast(round(resolvedHeight * (0.06 + portraitStrength * 0.018)), 52),
    subtitleSidePadding: scaleDimension(42, horizontalScale, 18),
    subtitlePaddingX: scaleDimension(14, subtitleScale, 16),
    subtitlePaddingY: scaleDimension(8, subtitleVerticalScale, 10),
    subtitleRadius: scaleDimension(10, subtitleScale, 10),
    subtitleMaxWidthRatio: clamp(0.88 + portraitStrength * 0.06, 0.88, 0.94),
    subtitleSafeWidthRatio: clamp(0.85 + portraitStrength * 0.05, 0.85, 0.9),
    chapterTop: atLeast(round(resolvedHeight * 0.028), 22),
    chapterInsetX: scaleDimension(44, horizontalScale, 20),
    chapterGap: scaleDimension(6, chapterScale, 5),
    chapterCardMinWidth: scaleDimension(422, chapterWidthScale, 280),
    chapterCardMaxWidthRatio: clamp(0.7 + portraitStrength * 0.1, 0.7, 0.8),
    chapterCardPaddingX: scaleDimension(14, chapterScale, 12),
    chapterCardPaddingY: scaleDimension(12, chapterScale, 10),
    chapterCardRadius: scaleDimension(12, chapterScale, 10),
    chapterMetaFontSize: scaleDimension(18, chapterScale, 16),
    chapterTitleFontSize: scaleDimension(32, chapterScale, 26),
    progressInsetX: scaleDimension(44, horizontalScale, 20),
    progressBottom: atLeast(round(resolvedHeight * 0.012), 10),
    progressHeight,
    progressRadius,
    progressLabelPaddingX: scaleDimension(4, progressScale, 3),
    progressLabelFontSize,
  };
};

export const fitTextToBox = ({
  text,
  maxWidth,
  baseFontSize,
  minFontSize,
  maxLines,
  fontWeight = 400,
  fontFamily = DEFAULT_FONT_FAMILY,
}: FitTextToBoxInput): FittedTextBox => {
  const normalized = (text || "").replace(/\r\n?/g, "\n").trim();
  if (!normalized) {
    return {fontSize: atLeast(round(baseFontSize), 1), lines: [""], text: "", truncated: false};
  }

  const resolvedMaxWidth = Math.max(1, maxWidth);
  const resolvedBaseFontSize = atLeast(round(baseFontSize), 1);
  const resolvedMinFontSize = Math.min(resolvedBaseFontSize, atLeast(round(minFontSize), 1));
  const resolvedMaxLines = Math.max(1, Math.floor(maxLines));

  let low = resolvedMinFontSize;
  let high = resolvedBaseFontSize;
  let bestFontSize = resolvedMinFontSize;
  let bestLines = layoutTextLines({
    text: normalized,
    maxWidth: resolvedMaxWidth,
    fontSize: resolvedMinFontSize,
    fontWeight,
    fontFamily,
  });
  let fits = bestLines.length <= resolvedMaxLines;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const lines = layoutTextLines({
      text: normalized,
      maxWidth: resolvedMaxWidth,
      fontSize: mid,
      fontWeight,
      fontFamily,
    });
    if (lines.length <= resolvedMaxLines) {
      bestFontSize = mid;
      bestLines = lines;
      fits = true;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  if (!fits) {
    const truncatedLines = bestLines.slice(0, resolvedMaxLines);
    truncatedLines[resolvedMaxLines - 1] = ellipsizeToWidth({
      text: truncatedLines[resolvedMaxLines - 1] || bestLines[resolvedMaxLines - 1] || normalized,
      maxWidth: resolvedMaxWidth,
      fontSize: resolvedMinFontSize,
      fontWeight,
      fontFamily,
    });
    return {
      fontSize: resolvedMinFontSize,
      lines: truncatedLines,
      text: truncatedLines.join("\n"),
      truncated: true,
    };
  }

  return {
    fontSize: bestFontSize,
    lines: bestLines,
    text: bestLines.join("\n"),
    truncated: false,
  };
};

export const fitAdaptiveTextToBox = ({
  preferredMaxLines = 2,
  fallbackMaxLines = 3,
  finalMaxLines = 4,
  ...rest
}: Omit<FitTextToBoxInput, "maxLines"> & {
  preferredMaxLines?: number;
  fallbackMaxLines?: number;
  finalMaxLines?: number;
}): AdaptiveFittedTextBox => {
  const preferred = fitTextToBox({
    ...rest,
    maxLines: preferredMaxLines,
  });
  if (!preferred.truncated || fallbackMaxLines <= preferredMaxLines) {
    return {
      ...preferred,
      maxLines: preferredMaxLines,
    };
  }

  const fallback = fitTextToBox({
    ...rest,
    maxLines: fallbackMaxLines,
  });
  if (!fallback.truncated || finalMaxLines <= fallbackMaxLines) {
    return {
      ...fallback,
      maxLines: fallbackMaxLines,
    };
  }

  const final = fitTextToBox({
    ...rest,
    maxLines: finalMaxLines,
  });
  return {
    ...final,
    maxLines: finalMaxLines,
  };
};

export const fitUniformAdaptiveTextToBox = ({
  preferredMaxLines = 2,
  fallbackMaxLines = 3,
  finalMaxLines = 4,
  ...rest
}: Omit<FitUniformTextBoxInput, "maxLines"> & {
  preferredMaxLines?: number;
  fallbackMaxLines?: number;
  finalMaxLines?: number;
}): FittedUniformAdaptiveTextBox => {
  const preferred = fitUniformTextToBox({
    ...rest,
    maxLines: preferredMaxLines,
  });
  if (!preferred.labels.some((label) => label.truncated) || fallbackMaxLines <= preferredMaxLines) {
    return {
      ...preferred,
      maxLines: preferredMaxLines,
    };
  }

  const fallback = fitUniformTextToBox({
    ...rest,
    maxLines: fallbackMaxLines,
  });
  if (!fallback.labels.some((label) => label.truncated) || finalMaxLines <= fallbackMaxLines) {
    return {
      ...fallback,
      maxLines: fallbackMaxLines,
    };
  }

  const final = fitUniformTextToBox({
    ...rest,
    maxLines: finalMaxLines,
  });
  return {
    ...final,
    maxLines: finalMaxLines,
  };
};

export const DEFAULT_SUBTITLE_MAX_LINES = [2, 3, 4] as const;

export const getSubtitleLineHeight = ({
  subtitleScale = 1,
  isPortrait,
}: {
  subtitleScale?: number;
  isPortrait: boolean;
}): number => {
  const normalizedScale = clamp(subtitleScale, 0.7, 1.45);
  const base = isPortrait ? 1.54 : 1.5;
  const scaleBoost = Math.max(0, normalizedScale - 1) * 0.38;
  return clamp(base + scaleBoost, base, isPortrait ? 1.74 : 1.68);
};

export const getSafeSubtitleScale = ({
  requestedScale = 1,
  width,
  height,
  baseSubtitleFontSize,
}: {
  requestedScale?: number;
  width: number;
  height: number;
  baseSubtitleFontSize: number;
}): number => {
  const normalizedScale = clamp(requestedScale, 0.7, 1.45);
  if (height <= width) {
    return normalizedScale;
  }

  const widthDrivenMaxFontSize = Math.max(30, round(width * 0.1065));
  const widthDrivenMaxScale = widthDrivenMaxFontSize / Math.max(1, baseSubtitleFontSize);
  return clamp(Math.min(normalizedScale, widthDrivenMaxScale), 0.7, 1.45);
};

export const fitSubtitleLayoutWithDom = ({
  element,
  baseFontSize,
  minFontSize,
  maxLinesCandidates = DEFAULT_SUBTITLE_MAX_LINES,
}: {
  element: HTMLElement;
  baseFontSize: number;
  minFontSize: number;
  maxLinesCandidates?: readonly number[];
}): DomSubtitleLayout => {
  const resolvedBaseFontSize = atLeast(round(baseFontSize), 1);
  const resolvedMinFontSize = Math.min(resolvedBaseFontSize, atLeast(round(minFontSize), 1));
  const resolvedCandidates = Array.from(
    new Set(maxLinesCandidates.map((value) => Math.max(1, Math.floor(value))))
  );
  const orderedCandidates = resolvedCandidates.length > 0 ? resolvedCandidates : [2];

  if (typeof window === "undefined" || element.clientWidth <= 0) {
    return {
      fontSize: resolvedBaseFontSize,
      maxLines: orderedCandidates[0],
    };
  }

  const previousInlineStyles = {
    display: element.style.display,
    overflow: element.style.overflow,
    maxHeight: element.style.maxHeight,
    webkitLineClamp: element.style.webkitLineClamp,
    webkitBoxOrient: element.style.webkitBoxOrient,
    fontSize: element.style.fontSize,
  };

  element.style.display = "block";
  element.style.overflow = "visible";
  element.style.maxHeight = "none";
  element.style.webkitLineClamp = "unset";
  element.style.webkitBoxOrient = "initial";

  const fitsAt = (fontSize: number, maxLines: number): boolean => {
    element.style.fontSize = `${fontSize}px`;
    const computed = window.getComputedStyle(element);
    const lineHeight = Number.parseFloat(computed.lineHeight) || fontSize * 1.35;
    const allowedHeight = lineHeight * maxLines + 1;
    return element.scrollHeight <= allowedHeight && element.scrollWidth <= element.clientWidth + 1;
  };

  let fallback = {
    fontSize: resolvedMinFontSize,
    maxLines: orderedCandidates[orderedCandidates.length - 1],
  };

  try {
    for (const maxLines of orderedCandidates) {
      let nextFontSize = resolvedBaseFontSize;
      while (nextFontSize > resolvedMinFontSize) {
        if (fitsAt(nextFontSize, maxLines)) {
          return {fontSize: nextFontSize, maxLines};
        }
        nextFontSize -= 1;
      }
      if (fitsAt(resolvedMinFontSize, maxLines)) {
        return {fontSize: resolvedMinFontSize, maxLines};
      }
      fallback = {fontSize: resolvedMinFontSize, maxLines};
    }
  } finally {
    element.style.display = previousInlineStyles.display;
    element.style.overflow = previousInlineStyles.overflow;
    element.style.maxHeight = previousInlineStyles.maxHeight;
    element.style.webkitLineClamp = previousInlineStyles.webkitLineClamp;
    element.style.webkitBoxOrient = previousInlineStyles.webkitBoxOrient;
    element.style.fontSize = previousInlineStyles.fontSize;
  }

  return fallback;
};

export const fitSingleLineText = ({
  text,
  maxWidth,
  baseFontSize,
  minFontSize,
  horizontalPadding = 0,
  maxFontSize,
  maxHeight,
  lineHeight = 1.2,
  targetWidthRatio = 0.82,
  fontWeight = 400,
  fontFamily = DEFAULT_FONT_FAMILY,
}: FitSingleLineTextInput): FittedSingleLineText => {
  const normalized = (text || "").trim();
  if (!normalized) return {fontSize: atLeast(round(baseFontSize), 1), visible: false};

  const resolvedMaxWidth = Math.max(0, maxWidth - Math.max(0, horizontalPadding) * 2);
  if (resolvedMaxWidth <= 0) {
    return {fontSize: atLeast(round(minFontSize), 1), visible: false};
  }

  const resolvedBaseFontSize = atLeast(round(baseFontSize), 1);
  const resolvedMinFontSize = Math.min(resolvedBaseFontSize, atLeast(round(minFontSize), 1));
  const resolvedTargetWidthRatio = clamp(targetWidthRatio, 0.55, 1);
  const targetWidth = Math.max(1, resolvedMaxWidth * resolvedTargetWidthRatio);
  const minWidth = measureTextWidth({
    text: normalized,
    fontSize: resolvedMinFontSize,
    fontWeight,
    fontFamily,
  });
  if (minWidth > resolvedMaxWidth) {
    return {fontSize: resolvedMinFontSize, visible: false};
  }

  const naturalWidthAtOnePx = Math.max(
    0.0001,
    measureTextWidth({
      text: normalized,
      fontSize: 1,
      fontWeight,
      fontFamily,
    })
  );
  const widthDrivenMaxFontSize = atLeast(Math.floor(resolvedMaxWidth / naturalWidthAtOnePx), resolvedMinFontSize);
  const heightDrivenMaxFontSize =
    maxHeight && Number.isFinite(maxHeight)
      ? atLeast(Math.floor(Math.max(0, maxHeight) / Math.max(1, lineHeight)), resolvedMinFontSize)
      : Number.POSITIVE_INFINITY;
  const explicitMaxFontSize =
    maxFontSize !== undefined
      ? atLeast(round(maxFontSize), resolvedMinFontSize)
      : Number.POSITIVE_INFINITY;
  const resolvedMaxFontSize = Math.min(widthDrivenMaxFontSize, heightDrivenMaxFontSize, explicitMaxFontSize);

  let low = resolvedMinFontSize;
  let high = Math.max(resolvedMinFontSize, resolvedMaxFontSize);
  let best = minWidth <= targetWidth ? resolvedMinFontSize : 0;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const width = measureTextWidth({text: normalized, fontSize: mid, fontWeight, fontFamily});
    if (width <= targetWidth) {
      best = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  if (best > 0) return {fontSize: best, visible: true};
  return {fontSize: resolvedMinFontSize, visible: true};
};

export const fitUniformSingleLineText = ({
  items,
  baseFontSize,
  minFontSize,
  horizontalPadding = 0,
  maxFontSize,
  maxHeight,
  lineHeight = 1.2,
  targetWidthRatio = 0.82,
  fontWeight = 400,
  fontFamily = DEFAULT_FONT_FAMILY,
}: FitUniformSingleLineTextInput): FittedUniformSingleLineText => {
  const resolvedBaseFontSize = atLeast(round(baseFontSize), 1);
  const resolvedMinFontSize = Math.min(resolvedBaseFontSize, atLeast(round(minFontSize), 1));
  const resolvedTargetWidthRatio = clamp(targetWidthRatio, 0.55, 1);
  const resolvedLabels = items.map((item) => {
    const normalized = (item.text || "").trim();
    const resolvedMaxWidth = Math.max(0, item.maxWidth - Math.max(0, horizontalPadding) * 2);
    if (!normalized || resolvedMaxWidth <= 0) {
      return {
        text: normalized,
        resolvedMaxWidth,
        targetWidth: 0,
        visible: false,
        resolvedMaxFontSize: resolvedMinFontSize,
      };
    }

    const naturalWidthAtOnePx = Math.max(
      0.0001,
      measureTextWidth({
        text: normalized,
        fontSize: 1,
        fontWeight,
        fontFamily,
      })
    );
    const widthDrivenMaxFontSize = atLeast(
      Math.floor(resolvedMaxWidth / naturalWidthAtOnePx),
      resolvedMinFontSize
    );
    const heightDrivenMaxFontSize =
      maxHeight && Number.isFinite(maxHeight)
        ? atLeast(Math.floor(Math.max(0, maxHeight) / Math.max(1, lineHeight)), resolvedMinFontSize)
        : Number.POSITIVE_INFINITY;
    const explicitMaxFontSize =
      maxFontSize !== undefined
        ? atLeast(round(maxFontSize), resolvedMinFontSize)
        : Number.POSITIVE_INFINITY;
    const minWidth = measureTextWidth({
      text: normalized,
      fontSize: resolvedMinFontSize,
      fontWeight,
      fontFamily,
    });

    return {
      text: normalized,
      resolvedMaxWidth,
      targetWidth: Math.max(1, resolvedMaxWidth * resolvedTargetWidthRatio),
      visible: minWidth <= resolvedMaxWidth,
      resolvedMaxFontSize: Math.min(widthDrivenMaxFontSize, heightDrivenMaxFontSize, explicitMaxFontSize),
    };
  });

  if (resolvedLabels.length === 0) {
    return {fontSize: resolvedBaseFontSize, labels: []};
  }

  if (resolvedLabels.some((label) => !label.visible)) {
    return {
      fontSize: resolvedMinFontSize,
      labels: resolvedLabels.map((label) => ({visible: label.visible})),
    };
  }

  let low = resolvedMinFontSize;
  let high = Math.max(
    resolvedMinFontSize,
    Math.min(...resolvedLabels.map((label) => label.resolvedMaxFontSize))
  );
  let best = resolvedLabels.every((label) =>
    measureTextWidth({
      text: label.text,
      fontSize: resolvedMinFontSize,
      fontWeight,
      fontFamily,
    }) <= label.targetWidth
  )
    ? resolvedMinFontSize
    : 0;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const fitsAll = resolvedLabels.every((label) =>
      measureTextWidth({
        text: label.text,
        fontSize: mid,
        fontWeight,
        fontFamily,
      }) <= label.targetWidth
    );
    if (fitsAll) {
      best = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  return {
    fontSize: best > 0 ? best : resolvedMinFontSize,
    labels: resolvedLabels.map(() => ({visible: true})),
  };
};

export const fitUniformTextToBox = ({
  items,
  baseFontSize,
  minFontSize,
  maxLines,
  horizontalPadding = 0,
  maxFontSize,
  maxHeight,
  lineHeight = 1.2,
  targetWidthRatio = 0.82,
  fontWeight = 400,
  fontFamily = DEFAULT_FONT_FAMILY,
}: FitUniformTextBoxInput): FittedUniformTextBox => {
  const resolvedBaseFontSize = atLeast(round(baseFontSize), 1);
  const resolvedMinFontSize = Math.min(resolvedBaseFontSize, atLeast(round(minFontSize), 1));
  const resolvedMaxLines = Math.max(1, Math.floor(maxLines));
  const resolvedTargetWidthRatio = clamp(targetWidthRatio, 0.55, 1);
  const resolvedHeightDrivenMaxFontSize =
    maxHeight && Number.isFinite(maxHeight)
      ? atLeast(
          Math.floor(Math.max(0, maxHeight) / Math.max(1, lineHeight * resolvedMaxLines)),
          resolvedMinFontSize
        )
      : Number.POSITIVE_INFINITY;
  const explicitMaxFontSize =
    maxFontSize !== undefined
      ? atLeast(round(maxFontSize), resolvedMinFontSize)
      : Number.POSITIVE_INFINITY;

  const resolvedItems = items.map((item) => {
    const normalized = (item.text || "").trim();
    const resolvedMaxWidth = Math.max(0, item.maxWidth - Math.max(0, horizontalPadding) * 2);
    const targetWidth = Math.max(1, resolvedMaxWidth * resolvedTargetWidthRatio);
    const layoutAtMin = normalized
      ? layoutTextLines({
          text: normalized,
          maxWidth: targetWidth,
          fontSize: resolvedMinFontSize,
          fontWeight,
          fontFamily,
        })
      : [""];

    return {
      text: normalized,
      visible: Boolean(normalized) && resolvedMaxWidth > 0,
      targetWidth,
      fitsAtMin: Boolean(normalized) && layoutAtMin.length <= resolvedMaxLines,
    };
  });

  if (resolvedItems.length === 0) {
    return {fontSize: resolvedBaseFontSize, labels: []};
  }

  let low = resolvedMinFontSize;
  const resolvedUpperBound = Math.min(resolvedHeightDrivenMaxFontSize, explicitMaxFontSize);
  let high = Math.max(
    resolvedMinFontSize,
    Number.isFinite(resolvedUpperBound)
      ? atLeast(round(resolvedUpperBound), resolvedBaseFontSize)
      : resolvedBaseFontSize
  );
  let best = resolvedItems.every((item) => !item.visible || item.fitsAtMin)
    ? resolvedMinFontSize
    : 0;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const fitsAll = resolvedItems.every((item) => {
      if (!item.visible) return true;
      return (
        layoutTextLines({
          text: item.text,
          maxWidth: item.targetWidth,
          fontSize: mid,
          fontWeight,
          fontFamily,
        }).length <= resolvedMaxLines
      );
    });
    if (fitsAll) {
      best = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }

  const resolvedFontSize = best > 0 ? best : resolvedMinFontSize;
  return {
    fontSize: resolvedFontSize,
    labels: resolvedItems.map((item) => {
      if (!item.visible) {
        return {visible: false, text: "", lines: [], truncated: false};
      }
      const layout = fitTextToBox({
        text: item.text,
        maxWidth: item.targetWidth,
        baseFontSize: resolvedFontSize,
        minFontSize: resolvedFontSize,
        maxLines: resolvedMaxLines,
        fontWeight,
        fontFamily,
      });
      return {
        visible: true,
        text: layout.text,
        lines: layout.lines,
        truncated: layout.truncated,
      };
    }),
  };
};

export const wrapCaptionText = (rawText: string, input: CaptionWrapInput): string => {
  const normalized = prepareCaptionDisplayText(rawText);
  if (!normalized) return "";

  const usableWidth = Math.max(260, input.width * (input.maxWidthRatio ?? 0.9));
  const safeWidthRatio = input.safeWidthRatio ?? 0.86;
  const maxWidth = Math.max(1, usableWidth * safeWidthRatio);

  const lines: string[] = [];
  for (const hardLine of normalized.split("\n")) {
    const trimmed = hardLine.trim();
    if (!trimmed) continue;
    lines.push(
      ...wrapTextByWidth({
        text: trimmed,
        maxWidth,
        fontSize: input.fontSize,
        fontWeight: input.fontWeight ?? 700,
        fontFamily: input.fontFamily ?? DEFAULT_FONT_FAMILY,
      })
    );
  }
  return lines.join("\n");
};
