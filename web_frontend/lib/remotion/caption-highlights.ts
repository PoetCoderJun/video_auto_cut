import type {
  RenderCaption,
  RenderCaptionEmphasisSpan,
  RenderCaptionHighlight,
  RenderCaptionToken,
} from "../api";

export type NormalizedCaptionToken = {
  text: string;
  start: number;
  end: number;
  hasHighlight: boolean;
  isEmphasized: boolean;
  highlightColor?: string;
  highlightFontScale?: number;
  backgroundColor?: string;
};

export type CaptionRenderChunk = {
  text: string;
  start: number;
  end: number;
  isHighlighted: boolean;
  isEmphasized: boolean;
  highlightColor?: string;
  highlightFontScale?: number;
  backgroundColor?: string;
};

const isCaptionTokenEmphasized = (
  tokenIndex: number,
  emphasisSpans: RenderCaptionEmphasisSpan[] | undefined,
): boolean =>
  Array.isArray(emphasisSpans)
    ? emphasisSpans.some(
        (span) =>
          Number.isFinite(span?.startToken) &&
          Number.isFinite(span?.endToken) &&
          tokenIndex >= span.startToken &&
          tokenIndex < span.endToken,
      )
    : false;

const resolveCaptionHighlight = (
  tokenIndex: number,
  highlights: RenderCaptionHighlight[] | undefined,
): RenderCaptionHighlight | null =>
  Array.isArray(highlights)
    ? (
        highlights.find(
          (highlight) =>
            Number.isFinite(highlight?.startToken) &&
            Number.isFinite(highlight?.endToken) &&
            tokenIndex >= Number(highlight.startToken) &&
            tokenIndex < Number(highlight.endToken),
        ) ?? null
      )
    : null;

export const normalizeCaptionTokensForRender = (
  tokens: RenderCaptionToken[] | undefined,
  caption: Pick<RenderCaption, "start" | "end"> | null,
  emphasisSpans: RenderCaptionEmphasisSpan[] | undefined,
  highlights: RenderCaptionHighlight[] | undefined,
): NormalizedCaptionToken[] => {
  if (!caption || !Array.isArray(tokens) || tokens.length === 0) return [];
  return tokens
    .map((token, tokenIndex) => ({
      text: String(token?.text || ""),
      start: Number(token?.start),
      end: Number(token?.end),
      sourceTokenIndex: tokenIndex,
      highlight: resolveCaptionHighlight(tokenIndex, highlights),
    }))
    .filter(
      (token) =>
        token.text &&
        Number.isFinite(token.start) &&
        Number.isFinite(token.end) &&
        token.end >= token.start &&
        token.end >= caption.start &&
        token.start <= caption.end,
    )
    .map((token, index, list) => ({
      text: token.text,
      start: index === 0 ? caption.start : Math.max(caption.start, token.start),
      end:
        index === list.length - 1
          ? caption.end
          : Math.min(caption.end, Math.max(token.start, token.end)),
      hasHighlight: Boolean(token.highlight),
      isEmphasized: isCaptionTokenEmphasized(token.sourceTokenIndex, emphasisSpans),
      highlightColor: String(token.highlight?.color || "").trim() || undefined,
      highlightFontScale:
        typeof token.highlight?.fontScale === "number" &&
        Number.isFinite(token.highlight.fontScale) &&
        token.highlight.fontScale > 0
          ? token.highlight.fontScale
          : undefined,
      backgroundColor: String(token.highlight?.backgroundColor || "").trim() || undefined,
    }));
};

const sharesChunkStyle = (
  previous: CaptionRenderChunk,
  next: NormalizedCaptionToken,
): boolean =>
  previous.isHighlighted === Boolean(next.hasHighlight || next.highlightColor || next.highlightFontScale || next.isEmphasized || next.backgroundColor) &&
  previous.isEmphasized === next.isEmphasized &&
  previous.highlightColor === next.highlightColor &&
  previous.backgroundColor === next.backgroundColor &&
  (previous.highlightFontScale ?? null) === (next.highlightFontScale ?? null);

export const buildCaptionRenderChunks = (
  tokens: NormalizedCaptionToken[],
): CaptionRenderChunk[] => {
  return tokens.reduce<CaptionRenderChunk[]>((chunks, token) => {
    const isHighlighted = Boolean(
      token.hasHighlight || token.highlightColor || token.highlightFontScale || token.isEmphasized || token.backgroundColor,
    );
    const previous = chunks[chunks.length - 1];
    if (previous && sharesChunkStyle(previous, token)) {
      previous.text += token.text;
      previous.end = token.end;
      previous.isHighlighted = previous.isHighlighted || isHighlighted;
      return chunks;
    }
    chunks.push({
      text: token.text,
      start: token.start,
      end: token.end,
      isHighlighted,
      isEmphasized: token.isEmphasized,
      highlightColor: token.highlightColor,
      highlightFontScale: token.highlightFontScale,
      backgroundColor: token.backgroundColor,
    });
    return chunks;
  }, []);
};

export const getCaptionChunkFontScale = (
  chunk: Pick<
    CaptionRenderChunk,
    "isHighlighted" | "isEmphasized" | "highlightColor" | "highlightFontScale"
  >,
): number | undefined => {
  if (!chunk.isHighlighted) return undefined;
  const requestedScale =
    typeof chunk.highlightFontScale === "number" &&
    Number.isFinite(chunk.highlightFontScale) &&
    chunk.highlightFontScale > 0
      ? chunk.highlightFontScale
      : 1;
  const softenedScale =
    requestedScale > 1 ? 1 + (requestedScale - 1) * 0.85 : 1;
  const minimumScale = 1.16;
  return Math.max(minimumScale, Math.min(1.3, softenedScale));
};
