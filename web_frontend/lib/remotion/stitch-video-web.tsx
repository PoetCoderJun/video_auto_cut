import React, {useMemo} from "react";
import {AbsoluteFill, Sequence, useCurrentFrame} from "remotion";
import {Video} from "@remotion/media";
import {clamp, cn} from "../utils.ts";
import type {
  RenderCaption as ApiRenderCaption,
  RenderCaptionEmphasisSpan,
  RenderCaptionHighlight,
  RenderCaptionToken,
} from "../api";

import {
  applyOverlayScaleToTypography,
  DEFAULT_OVERLAY_CONTROLS,
  resolveOverlayAnchorBottom,
  type ProgressLabelMode,
} from "./overlay-controls";
import {
  PROGRESS_LABEL_PADDING_X_EM,
  getChapterCardStyle,
  getProgressLabelPaddingX,
  reserveSubtitleBottomForProgress,
  getSubtitleBoxMaxWidth,
  getSubtitleTextMaxWidth,
  getSubtitleThemeFitWidth,
  getSubtitleThemeRenderFontSize,
  getSubtitleThemeStyle,
  isBoxedSubtitleTheme,
  isTextSubtitleTheme,
  normalizeSubtitleTheme,
} from "./overlay-presentation";
import {
  CHAPTER_TITLE_LINE_HEIGHT,
  fitAdaptiveTextToBox,
  fitChapterTitleToBox,
  fitSingleLineText,
  getChapterCardLayoutMetrics,
  getResponsiveOverlayTypography,
  getSafeSubtitleScale,
  getSubtitleLineHeight,
  OVERLAY_FONT_FAMILY,
  prepareCaptionDisplayText,
} from "./typography";
import {WEB_RENDER_DELAY_RENDER_TIMEOUT_MS} from "./rendering";
import {coerceStitchVideoWebProps, type SubtitleRenderV1Contract} from "./subtitle-render-v1";

export type RenderCaption = ApiRenderCaption;

export type RenderTopic = {
  title: string;
  start: number;
  end: number;
};

export type RenderSegment = {
  start: number;
  end: number;
};

export type SubtitleTheme =
  | "black"
  | "white";

export type StitchVideoWebProps = {
  src: string;
  captions: RenderCaption[];
  topics: RenderTopic[];
  segments: RenderSegment[];
  fps: number;
  width: number;
  height: number;
  subtitleTheme?: SubtitleTheme;
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

type TimelineSegment = {
  from: number;
  durationInFrames: number;
  trimBefore: number;
  cutStart: number;
  cutEnd: number;
};

const findActiveTopicIndexByStart = (
  topics: Array<{start: number}>,
  timeSec: number
): number => {
  if (!Number.isFinite(timeSec) || topics.length === 0) return -1;
  let activeIndex = -1;
  for (let index = 0; index < topics.length; index += 1) {
    if (timeSec >= topics[index].start) {
      activeIndex = index;
    } else {
      break;
    }
  }
  return activeIndex;
};

type NormalizedCaptionToken = {
  text: string;
  start: number;
  end: number;
  isEmphasized: boolean;
  highlightColor?: string;
  highlightFontScale?: number;
};

const isCaptionTokenEmphasized = (
  tokenIndex: number,
  emphasisSpans: RenderCaptionEmphasisSpan[] | undefined
): boolean =>
  Array.isArray(emphasisSpans)
    ? emphasisSpans.some(
        (span) =>
          Number.isFinite(span?.startToken) &&
          Number.isFinite(span?.endToken) &&
          tokenIndex >= span.startToken &&
          tokenIndex < span.endToken
      )
    : false;

const resolveCaptionHighlight = (
  tokenIndex: number,
  highlights: RenderCaptionHighlight[] | undefined
): RenderCaptionHighlight | null =>
  Array.isArray(highlights)
    ? (
        highlights.find(
          (highlight) =>
            Number.isFinite(highlight?.startToken) &&
            Number.isFinite(highlight?.endToken) &&
            tokenIndex >= Number(highlight.startToken) &&
            tokenIndex < Number(highlight.endToken)
        ) ?? null
      )
    : null;

const normalizeCaptionTokens = (
  tokens: RenderCaptionToken[] | undefined,
  caption: RenderCaption | null,
  emphasisSpans: RenderCaptionEmphasisSpan[] | undefined,
  highlights: RenderCaptionHighlight[] | undefined
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
        token.start <= caption.end
    )
    .map((token, index, list) => ({
      text: token.text,
      start: index === 0 ? caption.start : Math.max(caption.start, token.start),
      end: index === list.length - 1 ? caption.end : Math.min(caption.end, Math.max(token.start, token.end)),
      isEmphasized: isCaptionTokenEmphasized(token.sourceTokenIndex, emphasisSpans),
      highlightColor: String(token.highlight?.color || "").trim() || undefined,
      highlightFontScale:
        typeof token.highlight?.fontScale === "number" && Number.isFinite(token.highlight.fontScale) && token.highlight.fontScale > 0
          ? token.highlight.fontScale
          : undefined,
    }));
};

const renderCaptionTokens = ({
  tokens,
  subtitleTheme,
}: {
  tokens: NormalizedCaptionToken[];
  subtitleTheme: SubtitleTheme;
}): React.ReactNode => {
  return tokens.map((token, index) => {
    const isHighlighted = Boolean(token.highlightColor || token.highlightFontScale || token.isEmphasized);
    return (
      <span
        key={`caption-token-${index}-${token.start}-${token.end}-${token.text}`}
        className={cn(
          "inline whitespace-pre-wrap align-baseline",
          isHighlighted ? "font-black tracking-[0.01em]" : "font-bold"
        )}
        style={{
          color:
            token.highlightColor ??
            (isHighlighted
              ? subtitleTheme === "white"
                ? "#0f172a"
                : "#67e8f9"
              : "inherit"),
          opacity: 1,
          fontSize:
            token.highlightFontScale && token.highlightFontScale !== 1
              ? `calc(1em * ${Math.max(0.72, Math.min(1.6, token.highlightFontScale))})`
              : undefined,
          textShadow:
            isHighlighted && subtitleTheme === "black"
              ? "0 1px 10px rgba(15, 23, 42, 0.35)"
              : undefined,
        }}
      >
        {token.text}
      </span>
    );
  });
};

export const StitchVideoWeb: React.FC<StitchVideoWebProps | SubtitleRenderV1Contract> = (rawProps) => {
  const {
    src,
    captions,
    topics,
    segments,
    fps,
    width,
    height,
    subtitleTheme = "black",
    subtitleScale = 1,
    subtitleYPercent = 90,
    progressScale = 1,
    progressYPercent = 97,
    chapterScale = 1,
    showSubtitles = true,
    showProgress = true,
    showChapter = true,
    progressLabelMode = "auto",
  } = coerceStitchVideoWebProps(rawProps as Record<string, unknown>) as StitchVideoWebProps;
  const frame = useCurrentFrame();
  const baseTypography = useMemo(() => getResponsiveOverlayTypography({width, height}), [width, height]);
  const safeSubtitleScale = useMemo(
    () =>
      getSafeSubtitleScale({
        requestedScale: subtitleScale,
        width,
        height,
        baseSubtitleFontSize: baseTypography.subtitleFontSize,
      }),
    [baseTypography.subtitleFontSize, height, subtitleScale, width]
  );
  const typography = useMemo(
    () =>
      applyOverlayScaleToTypography(baseTypography, {
        subtitleScale: safeSubtitleScale,
        progressScale,
        chapterScale,
      }),
    [baseTypography, chapterScale, progressScale, safeSubtitleScale]
  );
  const isPortrait = height > width;
  const chapterCardMetrics = useMemo(
    () =>
      getChapterCardLayoutMetrics({
        width,
        typography,
      }),
    [typography, width]
  );
  const progressInnerWidth = Math.max(1, width - typography.progressInsetX * 2);
  const resolvedSubtitleTheme = normalizeSubtitleTheme(subtitleTheme);
  const subtitleBoxedTheme = isBoxedSubtitleTheme(resolvedSubtitleTheme);
  const subtitleThemeIsText = isTextSubtitleTheme(resolvedSubtitleTheme);
  const subtitleLayoutTypography = subtitleThemeIsText ? baseTypography : typography;
  const subtitleBoxMaxWidth = Math.max(
    1,
    getSubtitleBoxMaxWidth({
      width,
      maxWidthRatio: typography.subtitleMaxWidthRatio,
      safeWidthRatio: typography.subtitleSafeWidthRatio,
    })
  );
  const subtitleTextMaxWidth = getSubtitleTextMaxWidth({
    boxMaxWidth: subtitleBoxMaxWidth,
    fontSize: subtitleLayoutTypography.subtitleFontSize,
    isBoxedTheme: subtitleBoxedTheme,
  });
  const subtitleFitMaxWidth = getSubtitleThemeFitWidth({
    maxWidth: subtitleTextMaxWidth,
    subtitleScale: safeSubtitleScale,
    isTextTheme: subtitleThemeIsText,
  });
  const allowWrappedProgressLabels =
    progressLabelMode === "double" || (progressLabelMode === "auto" && isPortrait);
  const progressLabelLineHeight = allowWrappedProgressLabels ? 1.08 : 1.2;
  const progressLabelPaddingX = getProgressLabelPaddingX(typography.progressLabelFontSize);
  const subtitleLineHeight = getSubtitleLineHeight({subtitleScale: safeSubtitleScale, isPortrait});
  const resolvedSubtitleBottom = resolveOverlayAnchorBottom({
    frameHeight: height,
    baselineBottom: typography.subtitleBottom,
    currentPercent: clamp(subtitleYPercent, 0, 100),
    defaultPercent: DEFAULT_OVERLAY_CONTROLS.subtitleYPercent,
  });
  const resolvedProgressBottom = resolveOverlayAnchorBottom({
    frameHeight: height,
    baselineBottom: typography.progressBottom,
    currentPercent: clamp(progressYPercent, 0, 100),
    defaultPercent: DEFAULT_OVERLAY_CONTROLS.progressYPercent,
  });
  const progressStrokeWidth = Math.min(
    2,
    Math.max(1, Math.round((typography.progressHeight * 0.034 + Number.EPSILON) * 4) / 4)
  );

  const wrappedCaptions = useMemo(
    () =>
      captions.map((caption) => ({
        ...caption,
        displayText: prepareCaptionDisplayText(caption.text),
      })),
    [captions]
  );

  const timelineSegments = useMemo((): TimelineSegment[] => {
    const normalized = (segments || [])
      .filter((segment) => Number.isFinite(segment.start) && Number.isFinite(segment.end) && segment.end > segment.start)
      .slice()
      .sort((a, b) => a.start - b.start);
    let cursorFrames = 0;
    let cursorCutSec = 0;
    return normalized.map((segment) => {
      const trimBefore = Math.max(0, Math.floor(segment.start * fps));
      const trimAfterFrame = Math.max(trimBefore + 1, Math.ceil(segment.end * fps));
      const durationInFrames = Math.max(1, trimAfterFrame - trimBefore);
      const exactDurationSec = Math.max(0, segment.end - segment.start);
      const item = {
        from: cursorFrames,
        durationInFrames,
        trimBefore,
        cutStart: cursorCutSec,
        cutEnd: cursorCutSec + exactDurationSec,
      };
      cursorFrames += durationInFrames;
      cursorCutSec += exactDurationSec;
      return item;
    });
  }, [segments, fps]);

  const mappedTimelineTime = useMemo(() => {
    if (timelineSegments.length === 0) {
      return frame / fps;
    }
    const last = timelineSegments[timelineSegments.length - 1];
    const totalFrames = last.from + last.durationInFrames;
    if (frame <= 0) return 0;
    if (frame >= totalFrames) return last.cutEnd;

    for (const seg of timelineSegments) {
      const segEndFrame = seg.from + seg.durationInFrames;
      if (frame < segEndFrame) {
        const inSegFrame = frame - seg.from;
        const ratio = seg.durationInFrames > 0 ? inSegFrame / seg.durationInFrames : 0;
        return seg.cutStart + (seg.cutEnd - seg.cutStart) * clamp(ratio, 0, 1);
      }
    }
    return last.cutEnd;
  }, [frame, fps, timelineSegments]);

  const t = mappedTimelineTime;
  const activeCaptionIndex = wrappedCaptions.findIndex((caption) => t >= caption.start && t < caption.end);
  const activeCaption = activeCaptionIndex >= 0 ? wrappedCaptions[activeCaptionIndex] : null;
  const activeCaptionLabel = activeCaptionIndex >= 0 ? captions[activeCaptionIndex]?.label : undefined;
  const activeCaptionBadgeText = String(activeCaptionLabel?.badgeText || "").trim();
  const subtitleRenderText = activeCaption?.displayText ?? "";
  const activeCaptionTokens = useMemo(
    () =>
      normalizeCaptionTokens(
        activeCaptionIndex >= 0 ? captions[activeCaptionIndex]?.tokens : undefined,
        activeCaption
          ? {
              index: activeCaption.index,
              start: activeCaption.start,
              end: activeCaption.end,
              text: activeCaption.text,
              tokens: captions[activeCaptionIndex]?.tokens,
            }
          : null,
        activeCaptionLabel?.emphasisSpans,
        activeCaptionLabel?.highlights
      ),
    [activeCaption, activeCaptionIndex, activeCaptionLabel?.emphasisSpans, activeCaptionLabel?.highlights, captions]
  );
  const subtitleInitialFontSize = subtitleLayoutTypography.subtitleFontSize;
  const subtitleMinFontSize = Math.max(
    isPortrait ? 23 : 26,
    Math.floor(subtitleLayoutTypography.subtitleFontSize * (isPortrait ? 0.44 : 0.68))
  );
  const activeCaptionLayout = useMemo(
    () =>
      activeCaption
        ? fitAdaptiveTextToBox({
            text: activeCaption.displayText,
            maxWidth: subtitleFitMaxWidth,
            baseFontSize: subtitleInitialFontSize,
            minFontSize: subtitleMinFontSize,
            preferredMaxLines: 2,
            fallbackMaxLines: 3,
            finalMaxLines: 4,
            fontWeight: 700,
            fontFamily: OVERLAY_FONT_FAMILY,
          })
        : null,
    [activeCaption, subtitleFitMaxWidth, subtitleInitialFontSize, subtitleMinFontSize]
  );
  const subtitleRenderFontSize = useMemo(
    () =>
      getSubtitleThemeRenderFontSize({
        fittedFontSize: activeCaptionLayout?.fontSize ?? subtitleInitialFontSize,
        subtitleScale: safeSubtitleScale,
        isTextTheme: subtitleThemeIsText,
      }),
    [activeCaptionLayout?.fontSize, safeSubtitleScale, subtitleInitialFontSize, subtitleThemeIsText]
  );
  const reservedSubtitleBottom = useMemo(
    () =>
      reserveSubtitleBottomForProgress({
        subtitleBottom: resolvedSubtitleBottom,
        progressBottom: resolvedProgressBottom,
        progressHeight: typography.progressHeight,
        subtitleFontSize: subtitleRenderFontSize,
        showProgress,
      }),
    [resolvedProgressBottom, resolvedSubtitleBottom, showProgress, subtitleRenderFontSize, typography.progressHeight]
  );

  const normalizedTopics = useMemo(() => {
    return (topics || [])
      .filter((topic) => Number.isFinite(topic.start) && Number.isFinite(topic.end) && topic.end > topic.start)
      .slice()
      .sort((a, b) => a.start - b.start);
  }, [topics]);

  const currentActiveTopicIndex = findActiveTopicIndexByStart(normalizedTopics, t);
  const activeTopic = currentActiveTopicIndex >= 0 ? normalizedTopics[currentActiveTopicIndex] : null;
  const activeTopicLabel = activeTopic ? `${currentActiveTopicIndex + 1}/${normalizedTopics.length}` : "";
  const topicTitleLayouts = useMemo(
    () =>
      normalizedTopics.map((topic) =>
        fitChapterTitleToBox({
          text: topic.title,
          maxWidth: chapterCardMetrics.titleMaxWidth,
          baseFontSize: typography.chapterTitleFontSize,
        })
      ),
    [chapterCardMetrics.titleMaxWidth, normalizedTopics, typography.chapterTitleFontSize]
  );
  const activeTopicLayout = currentActiveTopicIndex >= 0 ? topicTitleLayouts[currentActiveTopicIndex] : null;

  const scaledStyles = useMemo(() => {
    const chapterWrapExtra: React.CSSProperties = {};
    if (currentActiveTopicIndex === 0) {
      chapterWrapExtra.display = "flex";
      chapterWrapExtra.justifyContent = "flex-end";
    }

    return {
      subtitleWrap: {
        position: "absolute" as const,
        left: 0,
        right: 0,
        bottom: reservedSubtitleBottom,
        display: "flex" as const,
        justifyContent: "center" as const,
        pointerEvents: "none" as const,
        paddingLeft: typography.subtitleSidePadding,
        paddingRight: typography.subtitleSidePadding,
      },
      subtitleFrame: {
        position: "relative" as const,
        display: "inline-flex" as const,
        flexDirection: "column" as const,
        alignItems: "flex-start" as const,
        gap: activeCaptionBadgeText ? Math.max(6, Math.round(subtitleRenderFontSize * 0.14)) : 0,
        width: "fit-content",
        maxWidth: subtitleBoxMaxWidth,
        overflow: "visible" as const,
      },
      subtitleBox: {
        boxSizing: "border-box" as const,
        color: "#ffffff",
        fontSize: typography.subtitleFontSize,
        fontWeight: 700,
        fontFamily: OVERLAY_FONT_FAMILY,
        lineHeight: subtitleLineHeight,
        lineBreak: "auto" as const,
        fontKerning: "none" as const,
        fontVariantLigatures: "none" as const,
        textAlign: "left" as const,
        textShadow: "0 1px 1px rgba(0, 0, 0, 0.72)",
        whiteSpace: "normal" as const,
        wordBreak: "normal" as const,
        overflowWrap: "anywhere" as const,
        overflow: "hidden" as const,
      },
      subtitleBadge: {
        maxWidth: Math.min(subtitleBoxMaxWidth, width * 0.42),
        padding: "0.24em 0.68em",
        borderRadius: 999,
        border: "1px solid rgba(255, 255, 255, 0.16)",
        background: "linear-gradient(135deg, rgba(15, 23, 42, 0.94), rgba(30, 41, 59, 0.82))",
        color: "rgba(255, 255, 255, 0.96)",
        fontSize: Math.max(11, Math.round(subtitleRenderFontSize * 0.24)),
        fontWeight: 700,
        fontFamily: OVERLAY_FONT_FAMILY,
        lineHeight: 1.15,
        letterSpacing: "0.02em",
        whiteSpace: "nowrap" as const,
        overflow: "hidden" as const,
        textOverflow: "ellipsis" as const,
        boxShadow: "0 14px 30px -22px rgba(2, 6, 23, 0.55)",
      },
      chapterWrap: {
        position: "absolute" as const,
        top: typography.chapterTop,
        left: typography.chapterInsetX,
        right: typography.chapterInsetX,
        pointerEvents: "none" as const,
        ...chapterWrapExtra,
      },
      chapterCard: {
        ...getChapterCardStyle({
          cardMaxWidth: chapterCardMetrics.cardMaxWidth,
          activeTopicIndex: currentActiveTopicIndex,
        }),
      },
      chapterMeta: {
        fontSize: typography.chapterMetaFontSize,
        fontWeight: 700,
        fontFamily: OVERLAY_FONT_FAMILY,
        color: "#8ee0ff",
      },
      chapterTitle: {
        fontSize: typography.chapterTitleFontSize,
        lineHeight: CHAPTER_TITLE_LINE_HEIGHT,
        fontWeight: 800,
        fontFamily: OVERLAY_FONT_FAMILY,
        color: "#ffffff",
        whiteSpace: "pre-line" as const,
        wordBreak: "normal" as const,
        overflowWrap: "anywhere" as const,
      },
      progressWrap: {
        position: "absolute" as const,
        left: typography.progressInsetX,
        right: typography.progressInsetX,
        bottom: resolvedProgressBottom,
        height: typography.progressHeight,
        pointerEvents: "none" as const,
      },
      progressTrack: {
        position: "relative" as const,
        width: "100%",
        height: "100%",
        borderRadius: typography.progressRadius,
        overflow: "hidden" as const,
        backgroundColor: "rgba(16, 22, 30, 0.42)",
        border: `${progressStrokeWidth}px solid rgba(255, 255, 255, 0.22)`,
      },
      progressFill: {
        position: "absolute" as const,
        left: 0,
        top: 0,
        bottom: 0,
        width: "0%",
        background: "linear-gradient(90deg, rgba(29, 217, 255, 0.58), rgba(66, 240, 180, 0.45))",
      },
      progressSegment: {
        position: "absolute" as const,
        top: 0,
        bottom: 0,
        display: "flex" as const,
        alignItems: "center" as const,
        justifyContent: "center" as const,
        overflow: "hidden" as const,
        borderRight: `${progressStrokeWidth}px solid rgba(255, 255, 255, 0.2)`,
      },
      progressSegmentLabel: {
        maxWidth: "100%",
        padding: `0 ${PROGRESS_LABEL_PADDING_X_EM}em`,
        fontSize: typography.progressLabelFontSize,
        fontWeight: 700,
        fontFamily: OVERLAY_FONT_FAMILY,
        lineHeight: progressLabelLineHeight,
        whiteSpace: allowWrappedProgressLabels ? "pre-line" as const : "nowrap" as const,
        overflow: "hidden" as const,
        textOverflow: "ellipsis" as const,
        textAlign: "center" as const,
        color: "rgba(238, 244, 255, 0.9)",
      },
    };
  }, [
    allowWrappedProgressLabels,
    currentActiveTopicIndex,
    chapterCardMetrics.cardMaxWidth,
    progressLabelLineHeight,
    resolvedProgressBottom,
    reservedSubtitleBottom,
    progressStrokeWidth,
    subtitleLineHeight,
    subtitleBoxMaxWidth,
    subtitleRenderFontSize,
    typography,
    width,
  ]);

  const topicDurationEnd = normalizedTopics.reduce((max, item) => Math.max(max, item.end), 0);
  const captionDurationEnd = captions.reduce((max, item) => Math.max(max, item.end), 0);
  const segmentDurationEnd =
    timelineSegments.length > 0 ? timelineSegments[timelineSegments.length - 1].cutEnd : 0;
  const totalDuration = Math.max(1, topicDurationEnd, captionDurationEnd, segmentDurationEnd);
  const progress = clamp(t / totalDuration, 0, 1);
  const topicSegments = useMemo(() => {
    const segmentsForLayout = normalizedTopics
      .map((topic, index) => {
        const startRatio = clamp(topic.start / totalDuration, 0, 1);
        const endRatio = clamp(topic.end / totalDuration, 0, 1);
        if (endRatio <= startRatio) {
          return null;
        }
        const segmentWidth = progressInnerWidth * (endRatio - startRatio);
        return {
          title: topic.title,
          startRatio,
          endRatio,
          index,
          segmentWidth,
        };
      })
      .filter(
        (
          item
        ): item is {
          title: string;
          startRatio: number;
          endRatio: number;
          index: number;
          segmentWidth: number;
        } => item !== null
      );

    return segmentsForLayout.map((segment) => {
      if (allowWrappedProgressLabels) {
        const layout = fitAdaptiveTextToBox({
          text: segment.title,
          maxWidth: Math.max(1, segment.segmentWidth - progressLabelPaddingX * 2),
          baseFontSize: typography.progressLabelFontSize,
          minFontSize: Math.max(12, Math.floor(typography.progressLabelFontSize * 0.45)),
          preferredMaxLines: 2,
          fallbackMaxLines: 2,
          finalMaxLines: 2,
          fontWeight: 700,
          fontFamily: OVERLAY_FONT_FAMILY,
        });

        return {
          ...segment,
          labelFit: {
            fontSize: layout.fontSize,
            visible: !layout.truncated,
            text: layout.text,
          },
        };
      }

      const layout = fitSingleLineText({
        text: segment.title,
        maxWidth: segment.segmentWidth,
        baseFontSize: typography.progressLabelFontSize,
        minFontSize: Math.max(12, Math.floor(typography.progressLabelFontSize * 0.45)),
        maxFontSize: Math.max(typography.progressLabelFontSize, Math.floor(typography.progressHeight * 0.7)),
        maxHeight: typography.progressHeight,
        lineHeight: 1.2,
        targetWidthRatio: 0.84,
        horizontalPadding: progressLabelPaddingX,
        fontWeight: 700,
        fontFamily: OVERLAY_FONT_FAMILY,
        fontSizeStep: 0.25,
      });

      return {
        ...segment,
        labelFit: {
          fontSize: layout.fontSize,
          visible: layout.visible,
          text: segment.title,
        },
      };
    });
  }, [
    allowWrappedProgressLabels,
    normalizedTopics,
    progressLabelLineHeight,
    progressInnerWidth,
    totalDuration,
    typography.progressLabelFontSize,
    typography.progressHeight,
    progressLabelPaddingX,
  ]);

  const subtitleStyleOverrides = useMemo(() => {
    return getSubtitleThemeStyle({
      subtitleTheme: resolvedSubtitleTheme,
      boxMaxWidth: subtitleBoxMaxWidth,
      textMaxWidth: subtitleTextMaxWidth,
    });
  }, [resolvedSubtitleTheme, subtitleBoxMaxWidth, subtitleTextMaxWidth]);
  const subtitleThemeClassName = resolvedSubtitleTheme === "white"
    ? "rounded-[0.24em] border border-slate-900/8 bg-white/92 text-slate-950 shadow-[0_20px_44px_-28px_rgba(15,23,42,0.18)]"
    : "rounded-[0.24em] border border-white/14 bg-black/82 text-white shadow-[0_24px_48px_-30px_rgba(2,6,23,0.48)]";

  return (
    <AbsoluteFill
      style={{
        background: src ? "linear-gradient(180deg, #f8fbff 0%, #eef4ff 100%)" : "#ffffff",
      }}
    >
      {src
        ? timelineSegments.map((segment) => (
            <Sequence
              key={`${segment.from}-${segment.trimBefore}`}
              from={segment.from}
              durationInFrames={segment.durationInFrames}
            >
              <Video
                src={src}
                trimBefore={segment.trimBefore}
                delayRenderTimeoutInMilliseconds={WEB_RENDER_DELAY_RENDER_TIMEOUT_MS}
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "contain",
                  objectPosition: "center center",
                  backgroundColor: "#eef4ff",
                }}
              />
            </Sequence>
          ))
        : null}

      {showChapter && activeTopic ? (
        <div style={scaledStyles.chapterWrap}>
          <div style={scaledStyles.chapterCard}>
            <div style={scaledStyles.chapterMeta}>CHAPTER {activeTopicLabel}</div>
            <div
              style={{
                ...scaledStyles.chapterTitle,
                fontSize: activeTopicLayout?.fontSize ?? scaledStyles.chapterTitle.fontSize,
              }}
            >
              {activeTopicLayout?.text ?? activeTopic.title}
            </div>
          </div>
        </div>
      ) : null}

      {showSubtitles ? (
        <div style={scaledStyles.subtitleWrap}>
          <div style={scaledStyles.subtitleFrame}>
            {activeCaptionBadgeText ? <div style={scaledStyles.subtitleBadge}>{activeCaptionBadgeText}</div> : null}
            <div
              className={subtitleThemeClassName}
              style={{
                ...scaledStyles.subtitleBox,
                ...subtitleStyleOverrides,
                fontSize: subtitleRenderFontSize,
                whiteSpace: "pre-line",
                border: undefined,
                boxShadow: undefined,
              }}
            >
              {activeCaptionTokens.length > 0 ? (
                <span
                  className="inline whitespace-pre-wrap"
                >
                  {renderCaptionTokens({tokens: activeCaptionTokens, subtitleTheme: resolvedSubtitleTheme})}
                </span>
              ) : (
                activeCaptionLayout?.text ?? subtitleRenderText
              )}
            </div>
          </div>
        </div>
      ) : null}

      {showProgress ? (
        <div style={scaledStyles.progressWrap}>
          <div style={scaledStyles.progressTrack}>
            <div style={{...scaledStyles.progressFill, width: `${progress * 100}%`}} />
            {topicSegments.map((segment) => (
              <div
                key={`segment-${segment.index}-${segment.startRatio}-${segment.endRatio}`}
                style={{
                  ...scaledStyles.progressSegment,
                  left: `${segment.startRatio * 100}%`,
                  width: `${(segment.endRatio - segment.startRatio) * 100}%`,
                  backgroundColor:
                    segment.index === currentActiveTopicIndex ? "rgba(255, 255, 255, 0.08)" : "rgba(255, 255, 255, 0.02)",
                }}
              >
                <div
                  style={{
                    ...scaledStyles.progressSegmentLabel,
                    fontSize: segment.labelFit.fontSize,
                    color: segment.index === currentActiveTopicIndex ? "#ffffff" : "rgba(238, 244, 255, 0.84)",
                  }}
                >
                  {segment.labelFit.visible ? segment.labelFit.text : ""}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
