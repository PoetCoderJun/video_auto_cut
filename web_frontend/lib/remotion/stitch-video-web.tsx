import React, {useLayoutEffect, useMemo, useRef, useState} from "react";
import {AbsoluteFill, Sequence, useCurrentFrame} from "remotion";
import {Video} from "@remotion/media";
import {clamp, cn} from "../utils.ts";
import type {RenderCaption as ApiRenderCaption} from "../api";

import {
  applyOverlayScaleToTypography,
  DEFAULT_OVERLAY_CONTROLS,
  resolveOverlayAnchorBottom,
  type ProgressLabelMode,
} from "./overlay-controls";
import {
  PROGRESS_LABEL_PADDING_X_EM,
  getChapterAccentColor,
  getChapterCardStyle,
  getProgressLabelPaddingX,
  reserveSubtitleBottomForProgress,
  getSubtitleBoxMaxWidth,
  getSubtitleTextMaxWidth,
  getSubtitleThemeFitWidth,
  getSubtitleThemeRenderFontSize,
  getSubtitleThemeStyle,
  getSubtitleTextTreatment,
  isBoxedSubtitleTheme,
  isTextSubtitleTheme,
  normalizeSubtitleTheme,
} from "./overlay-presentation";
import {
  CHAPTER_TITLE_LINE_HEIGHT,
  buildSubtitleDomLineCandidates,
  fitAdaptiveTextToBox,
  fitChapterTitleToBox,
  fitSubtitleLayoutWithDom,
  fitSingleLineText,
  getChapterCardLayoutMetrics,
  getResponsiveOverlayTypography,
  getSafeSubtitleScale,
  getSubtitleLineHeight,
  OVERLAY_FONT_FAMILY,
  prepareCaptionDisplayText,
  resolveOverlayReferenceCanvas,
} from "./typography";
import {WEB_RENDER_DELAY_RENDER_TIMEOUT_MS} from "./rendering";
import {coerceStitchVideoWebProps, type SubtitleRenderV1Contract} from "./subtitle-render-v1";
import {
  buildCaptionRenderChunks,
  getCaptionChunkFontScale,
  normalizeCaptionTokensForRender,
  type CaptionRenderChunk,
} from "./caption-highlights";

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

export type SubtitleTheme = "stroke" | "stroke-white";

export type StitchVideoWebProps = {
  src: string;
  captions: RenderCaption[];
  topics: RenderTopic[];
  segments: RenderSegment[];
  fps: number;
  width: number;
  height: number;
  overlayReferenceWidth?: number;
  overlayReferenceHeight?: number;
  subtitleTheme?: SubtitleTheme;
  subtitleScale?: number;
  subtitleYPercent?: number;
  progressScale?: number;
  progressYPercent?: number;
  chapterScale?: number;
  showSubtitles?: boolean;
  showHighlights?: boolean;
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

const getContrastTextColor = (bgColor: string): string => {
  const hex = bgColor.replace("#", "");
  const r = parseInt(hex.substring(0, 2), 16) / 255;
  const g = parseInt(hex.substring(2, 4), 16) / 255;
  const b = parseInt(hex.substring(4, 6), 16) / 255;
  const luminance = 0.299 * r + 0.587 * g + 0.114 * b;
  return luminance > 0.55 ? "#0f172a" : "#f8fafc";
};

const HIGHLIGHT_COLOR_PALETTE = ["#12E8D1", "#FF4D9D", "#FFE04B", "#63F261"] as const;

const normalizeHighlightColor = (color: string | undefined, index: number): string =>
  HIGHLIGHT_COLOR_PALETTE.includes(color as typeof HIGHLIGHT_COLOR_PALETTE[number])
    ? color as string
    : HIGHLIGHT_COLOR_PALETTE[index % HIGHLIGHT_COLOR_PALETTE.length];

const HIGHLIGHT_SHADOWS: Record<SubtitleTheme, string> = {
  stroke: "0 1px 2px rgba(255, 255, 255, 0.82), 0 3px 10px rgba(255, 255, 255, 0.42)",
  "stroke-white": "0 2px 5px rgba(2, 6, 23, 0.58), 0 5px 14px rgba(2, 6, 23, 0.34)",
};

const renderCaptionTokens = ({
  chunks,
  subtitleTheme,
}: {
  chunks: CaptionRenderChunk[];
  subtitleTheme: SubtitleTheme;
}): React.ReactNode => {
  return chunks.map((chunk, index) => {
    const highlightFontScale = getCaptionChunkFontScale(chunk);
    const highlightColor = chunk.isHighlighted ? normalizeHighlightColor(chunk.highlightColor, index) : "inherit";
    const textTreatment = getSubtitleTextTreatment(subtitleTheme);

    return (
      <span
        key={`caption-chunk-${index}-${chunk.start}-${chunk.end}-${chunk.text}`}
        className={cn(
          chunk.isHighlighted
            ? "inline-block whitespace-pre-wrap align-baseline font-black tracking-[0.01em]"
            : "inline whitespace-pre-wrap align-baseline font-bold"
        )}
        style={{
          color: highlightColor,
          opacity: 1,
          fontSize:
            highlightFontScale && highlightFontScale !== 1
              ? `calc(1em * ${highlightFontScale})`
              : undefined,
          textShadow: chunk.isHighlighted ? HIGHLIGHT_SHADOWS[subtitleTheme] : undefined,
          lineHeight: chunk.isHighlighted ? 1.04 : undefined,
          WebkitTextStroke: textTreatment.WebkitTextStroke,
          paintOrder: textTreatment.paintOrder,
        }}
      >
        {chunk.text}
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
    overlayReferenceWidth,
    overlayReferenceHeight,
    subtitleTheme = "white",
    subtitleScale = 1,
    subtitleYPercent = 90,
    progressScale = 1,
    progressYPercent = 97,
    chapterScale = 1,
    showSubtitles = true,
    showHighlights = true,
    showProgress = true,
    showChapter = true,
    progressLabelMode = "auto",
  } = coerceStitchVideoWebProps(rawProps as Record<string, unknown>) as StitchVideoWebProps;
  const frame = useCurrentFrame();
  const subtitleRef = useRef<HTMLDivElement | null>(null);
  const overlayCanvas = useMemo(
    () =>
      resolveOverlayReferenceCanvas({
        width,
        height,
        referenceWidth: overlayReferenceWidth,
        referenceHeight: overlayReferenceHeight,
      }),
    [height, overlayReferenceHeight, overlayReferenceWidth, width]
  );
  const overlayWidth = overlayCanvas.width;
  const overlayHeight = overlayCanvas.height;
  const baseTypography = useMemo(
    () => getResponsiveOverlayTypography({width: overlayWidth, height: overlayHeight}),
    [overlayHeight, overlayWidth]
  );
  const safeSubtitleScale = useMemo(
    () =>
      getSafeSubtitleScale({
        requestedScale: subtitleScale,
        width: overlayWidth,
        height: overlayHeight,
        baseSubtitleFontSize: baseTypography.subtitleFontSize,
      }),
    [baseTypography.subtitleFontSize, overlayHeight, overlayWidth, subtitleScale]
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
  const isPortrait = overlayHeight > overlayWidth;
  const chapterCardMetrics = useMemo(
    () =>
      getChapterCardLayoutMetrics({
        width: overlayWidth,
        typography,
      }),
    [overlayWidth, typography]
  );
  const progressInnerWidth = Math.max(1, overlayWidth - typography.progressInsetX * 2);
  const resolvedSubtitleTheme = normalizeSubtitleTheme(subtitleTheme);
  const subtitleBoxedTheme = isBoxedSubtitleTheme(resolvedSubtitleTheme);
  const subtitleThemeIsText = isTextSubtitleTheme(resolvedSubtitleTheme);
  const subtitleLayoutTypography = subtitleThemeIsText ? baseTypography : typography;
  const subtitleBoxMaxWidth = Math.max(
    1,
    getSubtitleBoxMaxWidth({
      width: overlayWidth,
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
    frameHeight: overlayHeight,
    baselineBottom: typography.subtitleBottom,
    currentPercent: clamp(subtitleYPercent, 0, 100),
    defaultPercent: DEFAULT_OVERLAY_CONTROLS.subtitleYPercent,
  });
  const resolvedProgressBottom = resolveOverlayAnchorBottom({
    frameHeight: overlayHeight,
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
  const subtitleRenderText = activeCaption?.displayText ?? "";
  const activeCaptionTokens = useMemo(
    () =>
      normalizeCaptionTokensForRender(
        activeCaptionIndex >= 0 ? captions[activeCaptionIndex]?.tokens : undefined,
        activeCaption
          ? {
              start: activeCaption.start,
              end: activeCaption.end,
            }
          : null,
        showHighlights ? activeCaptionLabel?.emphasisSpans : undefined,
        showHighlights ? activeCaptionLabel?.highlights : undefined
      ),
    [
      activeCaption,
      activeCaptionIndex,
      activeCaptionLabel?.emphasisSpans,
      activeCaptionLabel?.highlights,
      captions,
      showHighlights,
    ]
  );
  const activeCaptionChunks = useMemo(
    () => buildCaptionRenderChunks(activeCaptionTokens),
    [activeCaptionTokens]
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
  const subtitleRenderMinFontSize = useMemo(
    () =>
      getSubtitleThemeRenderFontSize({
        fittedFontSize: subtitleMinFontSize,
        subtitleScale: safeSubtitleScale,
        isTextTheme: subtitleThemeIsText,
      }),
    [safeSubtitleScale, subtitleMinFontSize, subtitleThemeIsText]
  );
  const subtitleDomLineCandidates = useMemo(
    () => buildSubtitleDomLineCandidates(activeCaptionLayout?.maxLines),
    [activeCaptionLayout?.maxLines]
  );
  const [subtitleDomLayout, setSubtitleDomLayout] = useState<{
    fontSize: number;
    maxLines: number;
  } | null>(null);
  const captionChunkSignature = useMemo(
    () =>
      activeCaptionChunks
        .map((chunk) =>
          [
            chunk.text,
            chunk.isHighlighted ? "h" : "n",
            chunk.highlightColor ?? "",
            chunk.highlightFontScale ?? "",
          ].join(":")
        )
        .join("|"),
    [activeCaptionChunks]
  );

  useLayoutEffect(() => {
    const element = subtitleRef.current;
    if (!element || !activeCaption || !subtitleRenderText) {
      setSubtitleDomLayout(null);
      return;
    }

    const nextLayout = fitSubtitleLayoutWithDom({
      element,
      baseFontSize: subtitleRenderFontSize,
      minFontSize: subtitleRenderMinFontSize,
      maxLinesCandidates: subtitleDomLineCandidates,
    });
    setSubtitleDomLayout((previous) =>
      previous?.fontSize === nextLayout.fontSize && previous.maxLines === nextLayout.maxLines
        ? previous
        : nextLayout
    );
  }, [
    activeCaption,
    captionChunkSignature,
    subtitleDomLineCandidates,
    subtitleRenderFontSize,
    subtitleRenderMinFontSize,
    subtitleRenderText,
  ]);
  const subtitleMeasuredFontSize = subtitleDomLayout?.fontSize ?? subtitleRenderFontSize;
  const reservedSubtitleBottom = useMemo(
    () =>
      reserveSubtitleBottomForProgress({
        subtitleBottom: resolvedSubtitleBottom,
        progressBottom: resolvedProgressBottom,
        progressHeight: typography.progressHeight,
        subtitleFontSize: subtitleMeasuredFontSize,
        showProgress,
      }),
    [resolvedProgressBottom, resolvedSubtitleBottom, showProgress, subtitleMeasuredFontSize, typography.progressHeight]
  );

  const overlayLayerStyle = useMemo(
    () => ({
      position: "absolute" as const,
      left: 0,
      top: 0,
      width: overlayWidth,
      height: overlayHeight,
      transform: `scale(${overlayCanvas.scaleX}, ${overlayCanvas.scaleY})`,
      transformOrigin: "top left",
      pointerEvents: "none" as const,
    }),
    [overlayCanvas.scaleX, overlayCanvas.scaleY, overlayHeight, overlayWidth]
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
  const activeTopicAccentColor = getChapterAccentColor(currentActiveTopicIndex);
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
        display: "block" as const,
        width: "100%",
        maxWidth: subtitleTextMaxWidth,
        overflow: "visible" as const,
      },
      subtitleBox: {
        boxSizing: "border-box" as const,
        ...getSubtitleTextTreatment(resolvedSubtitleTheme),
        fontSize: typography.subtitleFontSize,
        fontWeight: 700,
        fontFamily: OVERLAY_FONT_FAMILY,
        lineHeight: subtitleLineHeight,
        lineBreak: "auto" as const,
        fontKerning: "none" as const,
        fontVariantLigatures: "none" as const,
        textAlign: "center" as const,
        whiteSpace: "normal" as const,
        wordBreak: "normal" as const,
        overflowWrap: "anywhere" as const,
        overflow: "visible" as const,
      },
      chapterWrap: {
        position: "absolute" as const,
        top: typography.chapterTop,
        left: typography.chapterInsetX,
        pointerEvents: "none" as const,
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
        color: activeTopicAccentColor,
        letterSpacing: "0.14em",
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
        border: `${progressStrokeWidth}px solid rgba(255, 255, 255, 0.2)`,
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
        borderRight: `${progressStrokeWidth}px solid rgba(255, 255, 255, 0.18)`,
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
    activeTopicAccentColor,
    allowWrappedProgressLabels,
    currentActiveTopicIndex,
    chapterCardMetrics.cardMaxWidth,
    progressLabelLineHeight,
    resolvedProgressBottom,
    reservedSubtitleBottom,
    progressStrokeWidth,
    resolvedSubtitleTheme,
    subtitleLineHeight,
    subtitleBoxMaxWidth,
    subtitleTextMaxWidth,
    subtitleRenderFontSize,
    typography,
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

    const fittedSegments = segmentsForLayout.map((segment) => {
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
        maxFontSize: typography.progressLabelFontSize,
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

    // Unify font sizes across all segments so labels look consistent.
    const unifiedFontSize = fittedSegments.length > 0
      ? Math.min(...fittedSegments.map((s) => s.labelFit.fontSize))
      : typography.progressLabelFontSize;

    return fittedSegments.map((segment) => ({
      ...segment,
      labelFit: {
        ...segment.labelFit,
        fontSize: unifiedFontSize,
      },
    }));
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
  const subtitleThemeClassName =
    resolvedSubtitleTheme === "stroke-white" ? "text-slate-50" : "text-neutral-900";

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

      <div style={overlayLayerStyle}>
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
              <div
                ref={subtitleRef}
                className={subtitleThemeClassName}
                style={{
                  ...scaledStyles.subtitleBox,
                  ...subtitleStyleOverrides,
                  fontSize: subtitleMeasuredFontSize,
                  whiteSpace: "pre-line",
                  border: "none",
                  boxShadow: "none",
                  background: "transparent",
                  padding: 0,
                  borderRadius: 0,
                }}
              >
                {activeCaptionChunks.length > 0 ? (
                  <span
                    className="inline whitespace-pre-wrap"
                  >
                    {renderCaptionTokens({chunks: activeCaptionChunks, subtitleTheme: resolvedSubtitleTheme})}
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
                      segment.index === currentActiveTopicIndex
                        ? "rgba(255, 255, 255, 0.09)"
                        : "rgba(255, 255, 255, 0.02)",
                  }}
                >
                  <div
                    style={{
                      ...scaledStyles.progressSegmentLabel,
                      fontSize: segment.labelFit.fontSize,
                      fontWeight: segment.index === currentActiveTopicIndex ? 800 : 700,
                      color: segment.index === currentActiveTopicIndex ? "#ffffff" : "rgba(238, 244, 255, 0.82)",
                      textShadow:
                        segment.index === currentActiveTopicIndex
                          ? "0 1px 4px rgba(0, 0, 0, 0.3), 0 0 8px rgba(255, 255, 255, 0.18)"
                          : "none",
                    }}
                  >
                    {segment.labelFit.visible ? segment.labelFit.text : ""}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};
