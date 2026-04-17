import {clamp} from "../utils.ts";
import {fitText, fitTextOnNLines, measureText} from "@remotion/layout-utils";
import {getChapterCardTitleMaxWidth} from "./overlay-presentation.ts";

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
  fontSizeStep?: number;
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
  fontSizeStep?: number;
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

export type ChapterCardLayoutMetrics = {
  cardMaxWidth: number;
  titleMaxWidth: number;
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

const round = (value: number): number => Math.round(value);
const atLeast = (value: number, min: number): number => Math.max(min, value);
const roundToStep = (value: number, step = 1): number => {
  const resolvedStep = Number.isFinite(step) && step > 0 ? step : 1;
  return Math.round(value / resolvedStep) * resolvedStep;
};
const floorToStep = (value: number, step = 1): number => {
  const resolvedStep = Number.isFinite(step) && step > 0 ? step : 1;
  return Math.floor(value / resolvedStep) * resolvedStep;
};

const scaleFromReference = (value: number, reference: number): number =>
  Math.pow(Math.max(1, value) / reference, SCALE_EXPONENT);

const scaleDimension = (base: number, scale: number, min: number, precisionStep = 1): number =>
  Math.max(min, roundToStep(base * scale, precisionStep));

const canUseRemotionLayoutUtils = (): boolean => typeof document !== "undefined";

export const CHAPTER_TITLE_LINE_HEIGHT = 1.16;

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

const tokenizeForLayoutUtils = (text: string): string[] => {
  const tokens: string[] = [];
  let asciiBuffer = "";

  const flushAscii = () => {
    if (!asciiBuffer) return;
    tokens.push(asciiBuffer);
    asciiBuffer = "";
  };

  for (const char of text) {
    if (char === "\n") {
      flushAscii();
      continue;
    }
    if (/\s/.test(char)) {
      flushAscii();
      continue;
    }
    if (CJK_RE.test(char) || BREAK_PUNCT_RE.test(char)) {
      flushAscii();
      tokens.push(char);
      continue;
    }
    asciiBuffer += char;
  }

  flushAscii();
  return tokens;
};

const reconstructLayoutUtilsLine = (line: string): string => {
  const tokens = line.split(" ").filter(Boolean);
  if (tokens.length === 0) return "";

  let rebuilt = tokens[0];
  for (let index = 1; index < tokens.length; index += 1) {
    const previous = tokens[index - 1];
    const current = tokens[index];
    const needsSpace = /[0-9A-Za-z]$/.test(previous) && /^[0-9A-Za-z]/.test(current);
    rebuilt += needsSpace ? ` ${current}` : current;
  }
  return rebuilt;
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
  if (canUseRemotionLayoutUtils()) {
    width = measureText({
      text: normalized,
      fontSize: roundedFontSize,
      fontWeight: String(fontWeight),
      fontFamily,
    }).width;
  } else if (ctx) {
    ctx.font = buildFontSpec({fontSize: roundedFontSize, fontWeight, fontFamily});
    width = ctx.measureText(normalized).width;
  } else {
    width = measureUnits(normalized) * roundedFontSize * 1.02;
  }

  textWidthCache.set(cacheKey, width);
  return width;
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
  const chapterWidthScale = horizontalScale * (1 + portraitStrength * 0.18);
  const progressLabelFontSize = scaleDimension(18.2, progressScale, 17);
  const progressHeight = atLeast(scaleDimension(40, progressScale, 34), round(progressLabelFontSize * 2.15));
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
    chapterGap: scaleDimension(5.5, chapterScale, 4.5, 0.25),
    chapterCardMinWidth: scaleDimension(360, chapterWidthScale, 240, 0.5),
    chapterCardMaxWidthRatio: clamp(0.64 + portraitStrength * 0.08, 0.64, 0.72),
    chapterCardPaddingX: scaleDimension(11.5, chapterScale, 9.5, 0.25),
    chapterCardPaddingY: scaleDimension(9.5, chapterScale, 7.5, 0.25),
    chapterCardRadius: scaleDimension(11, chapterScale, 9, 0.25),
    chapterMetaFontSize: scaleDimension(17, chapterScale, 14, 0.25),
    chapterTitleFontSize: scaleDimension(30, chapterScale, 24, 0.25),
    progressInsetX: scaleDimension(44, horizontalScale, 20),
    progressBottom: atLeast(round(resolvedHeight * 0.022), 18),
    progressHeight,
    progressRadius,
    progressLabelPaddingX: scaleDimension(4, progressScale, 3),
    progressLabelFontSize,
  };
};

const fitTextToBoxLegacy = ({
  text,
  maxWidth,
  baseFontSize,
  minFontSize,
  maxLines,
  fontSizeStep = 1,
  fontWeight = 400,
  fontFamily = DEFAULT_FONT_FAMILY,
}: FitTextToBoxInput): FittedTextBox => {
  const normalized = (text || "").replace(/\r\n?/g, "\n").trim();
  if (!normalized) {
    return {fontSize: atLeast(round(baseFontSize), 1), lines: [""], text: "", truncated: false};
  }

  const resolvedMaxWidth = Math.max(1, maxWidth);
  const resolvedFontSizeStep = Math.max(0.05, Number.isFinite(fontSizeStep) ? fontSizeStep : 1);
  const resolvedBaseFontSize = Math.max(
    resolvedFontSizeStep,
    roundToStep(baseFontSize, resolvedFontSizeStep)
  );
  const resolvedMinFontSize = Math.min(
    resolvedBaseFontSize,
    Math.max(resolvedFontSizeStep, roundToStep(minFontSize, resolvedFontSizeStep))
  );
  const resolvedMaxLines = Math.max(1, Math.floor(maxLines));
  const minUnits = Math.round(resolvedMinFontSize / resolvedFontSizeStep);
  const maxUnits = Math.round(resolvedBaseFontSize / resolvedFontSizeStep);

  let low = minUnits;
  let high = maxUnits;
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
    const fontSize = mid * resolvedFontSizeStep;
    const lines = layoutTextLines({
      text: normalized,
      maxWidth: resolvedMaxWidth,
      fontSize,
      fontWeight,
      fontFamily,
    });
    if (lines.length <= resolvedMaxLines) {
      bestFontSize = fontSize;
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

export const fitTextToBox = (input: FitTextToBoxInput): FittedTextBox => {
  const {
    text,
    maxWidth,
    baseFontSize,
    minFontSize,
    maxLines,
    fontWeight = 400,
    fontFamily = DEFAULT_FONT_FAMILY,
  } = input;
  const normalized = (text || "").replace(/\r\n?/g, "\n").trim();
  const resolvedMaxLines = Math.max(1, Math.floor(maxLines));
  const resolvedMaxWidth = Math.max(1, maxWidth);
  const resolvedBaseFontSize = Math.max(1, baseFontSize);
  const resolvedMinFontSize = Math.min(resolvedBaseFontSize, Math.max(1, minFontSize));

  if (!normalized || !canUseRemotionLayoutUtils()) {
    return fitTextToBoxLegacy(input);
  }

  try {
    const layoutText = tokenizeForLayoutUtils(normalized).join(" ");
    const fitted = fitTextOnNLines({
      text: layoutText,
      maxBoxWidth: resolvedMaxWidth,
      maxLines: resolvedMaxLines,
      maxFontSize: resolvedBaseFontSize,
      fontWeight: String(fontWeight),
      fontFamily,
    });

    if (!Number.isFinite(fitted.fontSize) || fitted.fontSize < resolvedMinFontSize) {
      return fitTextToBoxLegacy(input);
    }

    return {
      fontSize: fitted.fontSize,
      lines: fitted.lines.map(reconstructLayoutUtilsLine),
      text: fitted.lines.map(reconstructLayoutUtilsLine).join("\n"),
      truncated: false,
    };
  } catch {
    return fitTextToBoxLegacy(input);
  }
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

export const DEFAULT_SUBTITLE_MAX_LINES = [2, 3, 4] as const;

export const fitChapterTitleToBox = ({
  text,
  maxWidth,
  baseFontSize,
}: {
  text: string;
  maxWidth: number;
  baseFontSize: number;
}): AdaptiveFittedTextBox =>
  fitAdaptiveTextToBox({
    text,
    maxWidth,
    baseFontSize,
    minFontSize: Math.max(18, baseFontSize * 0.76),
    preferredMaxLines: 2,
    fallbackMaxLines: 3,
    finalMaxLines: 4,
    fontSizeStep: 0.25,
    fontWeight: 800,
    fontFamily: OVERLAY_FONT_FAMILY,
  });

export const getChapterCardLayoutMetrics = ({
  width,
  typography,
}: {
  width: number;
  typography: Pick<
    OverlayTypography,
    "chapterInsetX" | "chapterCardMinWidth" | "chapterCardMaxWidthRatio" | "chapterTitleFontSize"
  >;
}): ChapterCardLayoutMetrics => {
  const chapterWrapWidth = Math.max(1, width - typography.chapterInsetX * 2);
  const cardMaxWidth = Math.min(
    chapterWrapWidth,
    Math.max(typography.chapterCardMinWidth, chapterWrapWidth * typography.chapterCardMaxWidthRatio)
  );

  return {
    cardMaxWidth,
    titleMaxWidth: getChapterCardTitleMaxWidth({
      cardMaxWidth,
      titleFontSize: typography.chapterTitleFontSize,
    }),
  };
};

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

const fitSingleLineTextLegacy = ({
  text,
  maxWidth,
  baseFontSize,
  minFontSize,
  fontSizeStep = 1,
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

  const resolvedFontSizeStep = Math.max(0.05, Number.isFinite(fontSizeStep) ? fontSizeStep : 1);
  const resolvedBaseFontSize = Math.max(
    resolvedFontSizeStep,
    roundToStep(baseFontSize, resolvedFontSizeStep)
  );
  const resolvedMinFontSize = Math.min(
    resolvedBaseFontSize,
    Math.max(resolvedFontSizeStep, roundToStep(minFontSize, resolvedFontSizeStep))
  );
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
  const widthDrivenMaxFontSize = atLeast(
    floorToStep(resolvedMaxWidth / naturalWidthAtOnePx, resolvedFontSizeStep),
    resolvedMinFontSize
  );
  const heightDrivenMaxFontSize =
    maxHeight && Number.isFinite(maxHeight)
      ? atLeast(
          floorToStep(Math.max(0, maxHeight) / Math.max(1, lineHeight), resolvedFontSizeStep),
          resolvedMinFontSize
        )
      : Number.POSITIVE_INFINITY;
  const explicitMaxFontSize =
    maxFontSize !== undefined
      ? atLeast(floorToStep(maxFontSize, resolvedFontSizeStep), resolvedMinFontSize)
      : Number.POSITIVE_INFINITY;
  const resolvedMaxFontSize = Math.min(widthDrivenMaxFontSize, heightDrivenMaxFontSize, explicitMaxFontSize);

  let low = Math.round(resolvedMinFontSize / resolvedFontSizeStep);
  let high = Math.max(low, Math.round(resolvedMaxFontSize / resolvedFontSizeStep));
  let best = minWidth <= targetWidth ? resolvedMinFontSize : 0;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2) * resolvedFontSizeStep;
    const width = measureTextWidth({text: normalized, fontSize: mid, fontWeight, fontFamily});
    if (width <= targetWidth) {
      best = mid;
      low = Math.round(mid / resolvedFontSizeStep) + 1;
    } else {
      high = Math.round(mid / resolvedFontSizeStep) - 1;
    }
  }

  if (best > 0) return {fontSize: best, visible: true};
  return {fontSize: resolvedMinFontSize, visible: true};
};

export const fitSingleLineText = (input: FitSingleLineTextInput): FittedSingleLineText => {
  const {
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
  } = input;
  const normalized = (text || "").trim();
  const resolvedBaseFontSize = Math.max(1, baseFontSize);
  const resolvedMinFontSize = Math.min(resolvedBaseFontSize, Math.max(1, minFontSize));
  const resolvedMaxWidth = Math.max(0, maxWidth - Math.max(0, horizontalPadding) * 2);
  const resolvedTargetWidth = Math.max(1, resolvedMaxWidth * clamp(targetWidthRatio, 0.55, 1));
  const resolvedMaxFontSize = Math.min(
    maxFontSize ?? Number.POSITIVE_INFINITY,
    maxHeight && Number.isFinite(maxHeight) ? Math.max(1, maxHeight / Math.max(1, lineHeight)) : Number.POSITIVE_INFINITY,
    resolvedBaseFontSize
  );

  if (!normalized || !canUseRemotionLayoutUtils()) {
    return fitSingleLineTextLegacy(input);
  }

  try {
    const minWidth = measureText({
      text: normalized,
      fontSize: resolvedMinFontSize,
      fontWeight: String(fontWeight),
      fontFamily,
    }).width;
    if (minWidth > resolvedMaxWidth) {
      return {fontSize: resolvedMinFontSize, visible: false};
    }

    const fitted = fitText({
      text: normalized,
      withinWidth: resolvedTargetWidth,
      fontWeight: String(fontWeight),
      fontFamily,
    });

    return {
      fontSize: Math.max(resolvedMinFontSize, Math.min(resolvedMaxFontSize, fitted.fontSize)),
      visible: true,
    };
  } catch {
    return fitSingleLineTextLegacy(input);
  }
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
