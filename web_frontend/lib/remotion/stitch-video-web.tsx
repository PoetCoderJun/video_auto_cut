import React, {useMemo} from "react";
import {AbsoluteFill, Sequence, useCurrentFrame} from "remotion";
import {Video} from "@remotion/media";

import {
  fitSingleLineText,
  fitUniformSingleLineText,
  fitTextToBox,
  getResponsiveOverlayTypography,
  OVERLAY_FONT_FAMILY,
  prepareCaptionDisplayText,
} from "./typography";

export type RenderCaption = {
  index: number;
  start: number;
  end: number;
  text: string;
};

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
  | "text-black"
  | "text-white"
  | "box-white-on-black"
  | "box-black-on-white";

export type StitchVideoWebProps = {
  src: string;
  captions: RenderCaption[];
  topics: RenderTopic[];
  segments: RenderSegment[];
  fps: number;
  width: number;
  height: number;
  subtitleTheme?: SubtitleTheme;
};

type TimelineSegment = {
  from: number;
  durationInFrames: number;
  trimBefore: number;
  cutStart: number;
  cutEnd: number;
};

const clamp = (value: number, min = 0, max = 1): number => {
  if (value < min) return min;
  if (value > max) return max;
  return value;
};

const round = (n: number) => Math.round(n);

export const StitchVideoWeb: React.FC<StitchVideoWebProps> = ({
  src,
  captions,
  topics,
  segments,
  fps,
  width,
  height,
  subtitleTheme = "box-white-on-black",
}) => {
  const frame = useCurrentFrame();
  const typography = useMemo(() => getResponsiveOverlayTypography({width, height}), [width, height]);
  const chapterWrapWidth = Math.max(1, width - typography.chapterInsetX * 2);
  const chapterCardMaxWidth = Math.min(
    chapterWrapWidth,
    Math.max(typography.chapterCardMinWidth, chapterWrapWidth * typography.chapterCardMaxWidthRatio)
  );
  const chapterCardMinWidth = Math.min(typography.chapterCardMinWidth, chapterCardMaxWidth);
  const chapterTitleMaxWidth = Math.max(1, chapterCardMaxWidth - typography.chapterCardPaddingX * 2);
  const progressInnerWidth = Math.max(1, width - typography.progressInsetX * 2);

  const scaledStyles = useMemo(() => {
    return {
      subtitleWrap: {
        position: "absolute" as const,
        left: 0,
        right: 0,
        bottom: typography.subtitleBottom,
        display: "flex" as const,
        justifyContent: "center" as const,
        pointerEvents: "none" as const,
        paddingLeft: typography.subtitleSidePadding,
        paddingRight: typography.subtitleSidePadding,
      },
      subtitleBox: {
        color: "#ffffff",
        fontSize: typography.subtitleFontSize,
        fontWeight: 700,
        fontFamily: OVERLAY_FONT_FAMILY,
        lineHeight: 1.35,
        lineBreak: "strict" as const,
        fontKerning: "none" as const,
        fontVariantLigatures: "none" as const,
        textAlign: "center" as const,
        textShadow: "0 1px 1px rgba(0, 0, 0, 0.75), 0 0 2px rgba(0, 0, 0, 0.55)",
        whiteSpace: "normal" as const,
        textWrap: "balance" as const,
        wordBreak: "keep-all" as const,
        overflowWrap: "normal" as const,
        maxWidth: `${round(typography.subtitleMaxWidthRatio * 100)}%`,
      },
      chapterWrap: {
        position: "absolute" as const,
        top: typography.chapterTop,
        left: typography.chapterInsetX,
        right: typography.chapterInsetX,
        pointerEvents: "none" as const,
      },
      chapterCard: {
        display: "inline-flex" as const,
        flexDirection: "column" as const,
        gap: typography.chapterGap,
        minWidth: chapterCardMinWidth,
        maxWidth: chapterCardMaxWidth,
        padding: `${typography.chapterCardPaddingY}px ${typography.chapterCardPaddingX}px`,
        borderRadius: typography.chapterCardRadius,
        backgroundColor: "rgba(8, 12, 20, 0.74)",
        border: "1px solid rgba(255, 255, 255, 0.2)",
      },
      chapterMeta: {
        fontSize: typography.chapterMetaFontSize,
        fontWeight: 700,
        fontFamily: OVERLAY_FONT_FAMILY,
        color: "#8ee0ff",
      },
      chapterTitle: {
        fontSize: typography.chapterTitleFontSize,
        lineHeight: 1.2,
        fontWeight: 800,
        fontFamily: OVERLAY_FONT_FAMILY,
        lineBreak: "strict" as const,
        color: "#ffffff",
        whiteSpace: "pre-line" as const,
        wordBreak: "keep-all" as const,
      },
      progressWrap: {
        position: "absolute" as const,
        left: typography.progressInsetX,
        right: typography.progressInsetX,
        bottom: typography.progressBottom,
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
        border: "1px solid rgba(255, 255, 255, 0.22)",
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
        borderRight: "1px solid rgba(255, 255, 255, 0.2)",
      },
      progressSegmentLabel: {
        maxWidth: "100%",
        padding: `0 ${typography.progressLabelPaddingX}px`,
        fontSize: typography.progressLabelFontSize,
        fontWeight: 700,
        fontFamily: OVERLAY_FONT_FAMILY,
        lineHeight: 1.2,
        whiteSpace: "nowrap" as const,
        overflow: "hidden" as const,
        textOverflow: "ellipsis" as const,
        color: "rgba(238, 244, 255, 0.9)",
      },
    };
  }, [chapterCardMaxWidth, chapterCardMinWidth, typography]);

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
  const activeCaption = wrappedCaptions.find((caption) => t >= caption.start && t < caption.end);

  const normalizedTopics = useMemo(() => {
    return (topics || [])
      .filter((topic) => Number.isFinite(topic.start) && Number.isFinite(topic.end) && topic.end > topic.start)
      .slice()
      .sort((a, b) => a.start - b.start);
  }, [topics]);

  const activeTopicIndex = normalizedTopics.findIndex((topic, index) => {
    const isLast = index === normalizedTopics.length - 1;
    if (isLast) {
      return t >= topic.start && t <= topic.end;
    }
    return t >= topic.start && t < topic.end;
  });
  const activeTopic = activeTopicIndex >= 0 ? normalizedTopics[activeTopicIndex] : null;
  const activeTopicLabel = activeTopic ? `${activeTopicIndex + 1}/${normalizedTopics.length}` : "";
  const topicTitleLayouts = useMemo(
    () =>
      normalizedTopics.map((topic) =>
        fitTextToBox({
          text: topic.title,
          maxWidth: chapterTitleMaxWidth,
          baseFontSize: typography.chapterTitleFontSize,
          minFontSize: Math.max(18, Math.floor(typography.chapterTitleFontSize * 0.72)),
          maxLines: 2,
          fontWeight: 800,
          fontFamily: OVERLAY_FONT_FAMILY,
        })
      ),
    [chapterTitleMaxWidth, normalizedTopics, typography.chapterTitleFontSize]
  );
  const activeTopicLayout = activeTopicIndex >= 0 ? topicTitleLayouts[activeTopicIndex] : null;

  const topicDurationEnd = normalizedTopics.reduce((max, item) => Math.max(max, item.end), 0);
  const captionDurationEnd = captions.reduce((max, item) => Math.max(max, item.end), 0);
  const segmentDurationEnd =
    timelineSegments.length > 0 ? timelineSegments[timelineSegments.length - 1].cutEnd : 0;
  const totalDuration = Math.max(1, topicDurationEnd, captionDurationEnd, segmentDurationEnd);
  const progress = clamp(t / totalDuration);

  const topicSegments = useMemo(() => {
    const segmentsForLayout = normalizedTopics
      .map((topic, index) => {
        const startRatio = clamp(topic.start / totalDuration);
        const endRatio = clamp(topic.end / totalDuration);
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

    const uniformLabelFit = fitUniformSingleLineText({
      items: segmentsForLayout.map((segment) => ({
        text: segment.title,
        maxWidth: segment.segmentWidth,
      })),
      baseFontSize: typography.progressLabelFontSize,
      minFontSize: Math.max(12, Math.floor(typography.progressLabelFontSize * 0.45)),
      maxFontSize: Math.max(
        typography.progressLabelFontSize,
        Math.floor(typography.progressHeight * 0.58)
      ),
      maxHeight: typography.progressHeight,
      lineHeight: 1.2,
      targetWidthRatio: 0.84,
      horizontalPadding: typography.progressLabelPaddingX,
      fontWeight: 700,
      fontFamily: OVERLAY_FONT_FAMILY,
    });

    return segmentsForLayout.map((segment, index) => ({
      ...segment,
      labelFit: {
        fontSize: uniformLabelFit.fontSize,
        visible: uniformLabelFit.labels[index]?.visible ?? false,
      },
    }));
  }, [
    normalizedTopics,
    progressInnerWidth,
    totalDuration,
    typography.progressLabelFontSize,
    typography.progressLabelPaddingX,
  ]);

  const subtitleStyleOverrides = useMemo(() => {
    const p = typography.subtitlePaddingY;
    const px = typography.subtitlePaddingX;
    const br = typography.subtitleRadius;
    switch (subtitleTheme) {
      case "text-black":
        return {
          color: "#111111",
          backgroundColor: "transparent",
          padding: "0",
          borderRadius: 0,
          textShadow: "0 1px 1px rgba(255, 255, 255, 0.45)",
        } as React.CSSProperties;
      case "text-white":
        return {
          color: "#ffffff",
          backgroundColor: "transparent",
          padding: "0",
          borderRadius: 0,
          textShadow: "0 1px 2px rgba(0, 0, 0, 0.75)",
        } as React.CSSProperties;
      case "box-black-on-white":
        return {
          color: "#111111",
          backgroundColor: "rgba(255, 255, 255, 0.92)",
          padding: `${p}px ${px}px`,
          borderRadius: br,
          maxWidth: `${round(typography.subtitleMaxWidthRatio * 100)}%`,
          textShadow: "none",
        } as React.CSSProperties;
      case "box-white-on-black":
      default:
        return {
          color: "#ffffff",
          backgroundColor: "rgba(0, 0, 0, 0.82)",
          padding: `${p}px ${px}px`,
          borderRadius: br,
          maxWidth: `${round(typography.subtitleMaxWidthRatio * 100)}%`,
          textShadow: "none",
        } as React.CSSProperties;
    }
  }, [subtitleTheme, typography]);

  return (
    <AbsoluteFill style={{backgroundColor: "black"}}>
      {timelineSegments.map((segment) => (
        <Sequence key={`${segment.from}-${segment.trimBefore}`} from={segment.from} durationInFrames={segment.durationInFrames}>
          <Video src={src} trimBefore={segment.trimBefore} style={{width: "100%", height: "100%", objectFit: "contain"}} />
        </Sequence>
      ))}

      {activeTopic ? (
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

      <div style={scaledStyles.subtitleWrap}>
        <div style={{...scaledStyles.subtitleBox, ...subtitleStyleOverrides}}>{activeCaption ? activeCaption.displayText : ""}</div>
      </div>

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
                  segment.index === activeTopicIndex ? "rgba(255, 255, 255, 0.08)" : "rgba(255, 255, 255, 0.02)",
              }}
            >
              <div
                style={{
                  ...scaledStyles.progressSegmentLabel,
                  fontSize: segment.labelFit.fontSize,
                  color: segment.index === activeTopicIndex ? "#ffffff" : "rgba(238, 244, 255, 0.84)",
                }}
              >
                {segment.labelFit.visible ? segment.title : ""}
              </div>
            </div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};
