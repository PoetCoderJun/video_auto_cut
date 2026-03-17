"use client";

import React, {useEffect, useMemo, useRef, useState} from "react";

import type {WebRenderConfig} from "@/lib/api";
import type {SubtitleTheme} from "@/lib/remotion/stitch-video-web";
import {
  applyOverlayScaleToTypography,
  type OverlayScaleControls,
  type ProgressLabelMode,
} from "@/lib/remotion/overlay-controls";
import {
  fitUniformAdaptiveTextToBox,
  CHAPTER_TITLE_LINE_HEIGHT,
  fitChapterTitleToBox,
  fitUniformSingleLineText,
  fitUniformTextToBox,
  getChapterCardLayoutMetrics,
  getChapterCardMinHeight,
  getResponsiveOverlayTypography,
  getSafeSubtitleScale,
  getSubtitleLineHeight,
  OVERLAY_FONT_FAMILY,
  prepareCaptionDisplayText,
} from "@/lib/remotion/typography";

type ExportFramePreviewProps = {
  config: WebRenderConfig | null;
  sourceFile: File | null;
  sourceUrlOverride?: string | null;
  emptyStateMode?: "message" | "blank";
  subtitleTheme: SubtitleTheme;
  previewTimeSec: number;
  overlayControls: OverlayScaleControls;
};

type TimelineSegment = {
  start: number;
  end: number;
  cutStart: number;
  cutEnd: number;
};

const clamp = (value: number, min: number, max: number): number => {
  if (!Number.isFinite(value)) return min;
  if (value < min) return min;
  if (value > max) return max;
  return value;
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

const getTotalDuration = (config: WebRenderConfig | null): number => {
  if (!config) return 1;
  const input = config.input_props;
  const topicEnd = input.topics.reduce((max, item) => Math.max(max, item.end), 0);
  const captionEnd = input.captions.reduce((max, item) => Math.max(max, item.end), 0);
  const segmentEnd = input.segments.reduce((sum, segment) => sum + Math.max(0, segment.end - segment.start), 0);
  return Math.max(1, topicEnd, captionEnd, segmentEnd);
};

const buildTimelineSegments = (config: WebRenderConfig): TimelineSegment[] => {
  let cursor = 0;
  return config.input_props.segments
    .filter((segment) => Number.isFinite(segment.start) && Number.isFinite(segment.end) && segment.end > segment.start)
    .slice()
    .sort((a, b) => a.start - b.start)
    .map((segment) => {
      const duration = Math.max(0, segment.end - segment.start);
      const item = {
        start: segment.start,
        end: segment.end,
        cutStart: cursor,
        cutEnd: cursor + duration,
      };
      cursor += duration;
      return item;
    });
};

const mapPreviewTimeToSourceTime = (segments: TimelineSegment[], previewTimeSec: number): number => {
  if (segments.length === 0) return Math.max(0, previewTimeSec);
  const clamped = Math.max(0, previewTimeSec);
  for (const segment of segments) {
    if (clamped < segment.cutEnd) {
      return segment.start + (clamped - segment.cutStart);
    }
  }
  const last = segments[segments.length - 1];
  return last.end;
};

const getCenteredVideoStyle = (
  sourceDimensions: {width: number; height: number} | null,
  compositionWidth: number,
  compositionHeight: number
): React.CSSProperties => {
  const fallback: React.CSSProperties = {
    width: "100%",
    height: "100%",
    objectFit: "contain",
    objectPosition: "center center",
    display: "block",
    backgroundColor: "#eef4ff",
  };

  if (!sourceDimensions) return fallback;

  const sourceAspect = sourceDimensions.width / sourceDimensions.height;
  const compositionAspect = compositionWidth / compositionHeight;
  if (!Number.isFinite(sourceAspect) || sourceAspect <= 0) return fallback;

  if (sourceAspect >= compositionAspect) {
    return {
      position: "absolute",
      left: 0,
      top: "50%",
      width: "100%",
      height: Math.round(compositionWidth / sourceAspect),
      transform: "translateY(-50%)",
      display: "block",
      backgroundColor: "#eef4ff",
    };
  }

  return {
    position: "absolute",
    left: "50%",
    top: 0,
    width: Math.round(compositionHeight * sourceAspect),
    height: "100%",
    transform: "translateX(-50%)",
    display: "block",
    backgroundColor: "#eef4ff",
  };
};

export default function ExportFramePreview({
  config,
  sourceFile,
  sourceUrlOverride = null,
  emptyStateMode = "message",
  subtitleTheme,
  previewTimeSec,
  overlayControls,
}: ExportFramePreviewProps) {
  const [sourceUrl, setSourceUrl] = useState<string | null>(null);
  const [sourceDimensions, setSourceDimensions] = useState<{width: number; height: number} | null>(null);
  const [frameSize, setFrameSize] = useState({width: 0, height: 0});
  const frameRef = useRef<HTMLDivElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    if (sourceUrlOverride) {
      setSourceUrl(sourceUrlOverride);
      return;
    }
    if (!sourceFile) {
      setSourceDimensions(null);
      setSourceUrl((previous) => {
        if (previous && previous.startsWith("blob:")) URL.revokeObjectURL(previous);
        return null;
      });
      return;
    }

    const nextUrl = URL.createObjectURL(sourceFile);
    setSourceUrl((previous) => {
      if (previous && previous.startsWith("blob:")) URL.revokeObjectURL(previous);
      return nextUrl;
    });

    return () => {
      URL.revokeObjectURL(nextUrl);
    };
  }, [sourceFile, sourceUrlOverride]);

  useEffect(() => {
    const element = frameRef.current;
    if (!element) return;

    const update = () => {
      const nextSize = {
        width: Math.round(element.clientWidth),
        height: Math.round(element.clientHeight),
      };
      setFrameSize((previous) =>
        previous.width === nextSize.width && previous.height === nextSize.height ? previous : nextSize
      );
    };

    update();

    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", update);
      return () => {
        window.removeEventListener("resize", update);
      };
    }

    const observer = new ResizeObserver(() => {
      update();
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, [config?.composition.height, config?.composition.width]);

  const totalDuration = useMemo(() => getTotalDuration(config), [config]);
  const clampedPreviewTime = clamp(previewTimeSec, 0, totalDuration);

  const timelineSegments = useMemo(() => (config ? buildTimelineSegments(config) : []), [config]);
  const sourceTime = useMemo(
    () => mapPreviewTimeToSourceTime(timelineSegments, clampedPreviewTime),
    [clampedPreviewTime, timelineSegments]
  );

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !Number.isFinite(sourceTime)) return;
    const applyTime = () => {
      video.pause();
      const maxTime = Number.isFinite(video.duration) && video.duration > 0 ? Math.max(0, video.duration - 0.05) : sourceTime;
      const nextTime = clamp(sourceTime, 0, maxTime);
      if (Math.abs(video.currentTime - nextTime) > 0.033) {
        video.currentTime = nextTime;
      }
    };

    if (video.readyState >= 1) {
      applyTime();
      return;
    }

    video.addEventListener("loadedmetadata", applyTime, {once: true});
    return () => {
      video.removeEventListener("loadedmetadata", applyTime);
    };
  }, [sourceTime, sourceUrl]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const updateDimensions = () => {
      const width = Math.round(video.videoWidth || 0);
      const height = Math.round(video.videoHeight || 0);
      if (width <= 0 || height <= 0) return;
      setSourceDimensions((previous) =>
        previous?.width === width && previous?.height === height ? previous : {width, height}
      );
    };

    updateDimensions();
    video.addEventListener("loadedmetadata", updateDimensions);
    return () => {
      video.removeEventListener("loadedmetadata", updateDimensions);
    };
  }, [sourceUrl]);

  const previewModel = useMemo(() => {
    if (!config) return null;
    const composition = config.composition;
    const width = composition.width;
    const height = composition.height;
    const baseTypography = getResponsiveOverlayTypography({width, height});
    const safeSubtitleScale = getSafeSubtitleScale({
      requestedScale: overlayControls.subtitleScale,
      width,
      height,
      baseSubtitleFontSize: baseTypography.subtitleFontSize,
    });
    const typography = applyOverlayScaleToTypography(baseTypography, {
      ...overlayControls,
      subtitleScale: safeSubtitleScale,
    });
    const input = config.input_props;
    const wrappedCaptions = input.captions.map((caption) => ({
      ...caption,
      displayText: prepareCaptionDisplayText(caption.text),
    }));
    const isPortrait = height > width;
    const subtitleLineHeight = getSubtitleLineHeight({
      subtitleScale: safeSubtitleScale,
      isPortrait,
    });
    const activeCaptionIndex = wrappedCaptions.findIndex(
      (caption) => clampedPreviewTime >= caption.start && clampedPreviewTime < caption.end
    );
    const activeCaption = activeCaptionIndex >= 0 ? wrappedCaptions[activeCaptionIndex] : null;
    const chapterCardMetrics = getChapterCardLayoutMetrics({
      width,
      height,
      chapterScale: overlayControls.chapterScale,
      typography,
    });
    const chapterCardMinHeight = getChapterCardMinHeight({
      titleFontSize: typography.chapterTitleFontSize,
      titleLineCount: 1,
      metaFontSize: typography.chapterMetaFontSize,
      gap: typography.chapterGap,
      paddingY: typography.chapterCardPaddingY,
    });
    const subtitleBoxedTheme =
      subtitleTheme === "box-white-on-black" || subtitleTheme === "box-black-on-white";
    const subtitleBoxMaxWidth = Math.max(
      1,
      width * typography.subtitleMaxWidthRatio * typography.subtitleSafeWidthRatio
    );
    const subtitleTextMaxWidth = Math.max(
      1,
      subtitleBoxMaxWidth - (subtitleBoxedTheme ? typography.subtitlePaddingX * 2 : 0)
    );
    const normalizedTopics = input.topics
      .filter((topic) => Number.isFinite(topic.start) && Number.isFinite(topic.end) && topic.end > topic.start)
      .slice()
      .sort((a, b) => a.start - b.start);
    const activeTopicIndex = findActiveTopicIndexByStart(normalizedTopics, clampedPreviewTime);
    const activeTopic = activeTopicIndex >= 0 ? normalizedTopics[activeTopicIndex] : null;
    const activeTopicLabel = activeTopic ? `${activeTopicIndex + 1}/${normalizedTopics.length}` : "";
    const activeTopicLayout =
      activeTopicIndex >= 0
        ? fitChapterTitleToBox({
            text: normalizedTopics[activeTopicIndex].title,
            maxWidth: chapterCardMetrics.titleMaxWidth,
            baseFontSize: typography.chapterTitleFontSize,
          })
        : null;
    const progressInnerWidth = Math.max(1, width - typography.progressInsetX * 2);
    const progressLabelMode = (overlayControls.progressLabelMode ?? "auto") as ProgressLabelMode;
    const allowWrappedProgressLabels =
      progressLabelMode === "double" || (progressLabelMode === "auto" && isPortrait);
    const progressLabelLineHeight = allowWrappedProgressLabels ? 1.08 : 1.2;
    const topicSegmentsForLayout = normalizedTopics
      .map((topic, index) => {
        const startRatio = clamp(topic.start / totalDuration, 0, 1);
        const endRatio = clamp(topic.end / totalDuration, 0, 1);
        if (endRatio <= startRatio) {
          return null;
        }
        return {
          title: topic.title,
          startRatio,
          endRatio,
          index,
          segmentWidth: progressInnerWidth * (endRatio - startRatio),
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
    const uniformLabelFit = allowWrappedProgressLabels
      ? fitUniformTextToBox({
          items: topicSegmentsForLayout.map((segment) => ({
            text: segment.title,
            maxWidth: segment.segmentWidth,
          })),
          baseFontSize: typography.progressLabelFontSize,
          minFontSize: Math.max(12, Math.floor(typography.progressLabelFontSize * 0.45)),
          maxLines: 2,
          maxFontSize: Math.max(
            typography.progressLabelFontSize,
            Math.floor(typography.progressHeight / (progressLabelLineHeight * 2))
          ),
          maxHeight: typography.progressHeight,
          lineHeight: progressLabelLineHeight,
          targetWidthRatio: 0.9,
          horizontalPadding: typography.progressLabelPaddingX,
          fontWeight: 700,
          fontFamily: OVERLAY_FONT_FAMILY,
        })
      : fitUniformSingleLineText({
          items: topicSegmentsForLayout.map((segment) => ({
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

    return {
      composition,
      typography,
      subtitleLineHeight,
      subtitleBoxMaxWidth,
      subtitleTextMaxWidth,
      wrappedCaptions,
      activeCaptionIndex,
      activeCaption,
      activeTopic,
      activeTopicLabel,
      activeTopicLayout,
      progressRatio: clamp(clampedPreviewTime / totalDuration, 0, 1),
      topicSegments: topicSegmentsForLayout.map((segment, index) => ({
        ...segment,
        labelFit: {
          fontSize: uniformLabelFit.fontSize,
          visible: uniformLabelFit.labels[index]?.visible ?? false,
          text:
            allowWrappedProgressLabels
              ? (uniformLabelFit.labels[index] as {text?: string} | undefined)?.text ?? segment.title
              : segment.title,
        },
      })),
      allowWrappedProgressLabels,
      progressLabelLineHeight,
      chapterCardMinHeight,
      chapterCardStyleMinWidth: chapterCardMetrics.cardStyleMinWidth,
      chapterCardStyleWidth: chapterCardMetrics.cardStyleWidth,
      chapterCardStyleMaxWidth: chapterCardMetrics.cardStyleMaxWidth,
      chapterTitleMaxWidth: chapterCardMetrics.titleMaxWidth,
    };
  }, [clampedPreviewTime, config, overlayControls, subtitleTheme, totalDuration]);

  const subtitleInitialFontSize = previewModel?.typography.subtitleFontSize ?? 0;
  const subtitleRenderText = previewModel?.activeCaption?.displayText ?? "";
  const subtitleMinFontSize = previewModel
    ? Math.max(
        previewModel.composition.height > previewModel.composition.width ? 23 : 26,
        Math.floor(
          previewModel.typography.subtitleFontSize *
            (previewModel.composition.height > previewModel.composition.width ? 0.44 : 0.68)
        )
      )
    : 0;
  const resolvedSubtitleSet = useMemo(
    () =>
      fitUniformAdaptiveTextToBox({
        items: (previewModel?.wrappedCaptions ?? []).map((caption) => ({
          text: caption.displayText,
          maxWidth: previewModel?.subtitleTextMaxWidth ?? 1,
        })),
        baseFontSize: subtitleInitialFontSize,
        minFontSize: subtitleMinFontSize,
        preferredMaxLines: 2,
        fallbackMaxLines: 3,
        finalMaxLines: 4,
        fontWeight: 700,
        fontFamily: OVERLAY_FONT_FAMILY,
      }),
    [previewModel?.subtitleTextMaxWidth, previewModel?.wrappedCaptions, subtitleInitialFontSize, subtitleMinFontSize]
  );
  const activeCaptionLayout =
    previewModel && previewModel.activeCaptionIndex >= 0
      ? resolvedSubtitleSet.labels[previewModel.activeCaptionIndex]
      : null;

  const subtitleStyleOverrides = useMemo(() => {
    if (!previewModel) return {};
    const typography = previewModel.typography;
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
          maxWidth: previewModel.subtitleTextMaxWidth,
          textShadow: "0 1px 1px rgba(255, 255, 255, 0.45)",
        } as React.CSSProperties;
      case "text-white":
        return {
          color: "#ffffff",
          backgroundColor: "transparent",
          padding: "0",
          borderRadius: 0,
          maxWidth: previewModel.subtitleTextMaxWidth,
          textShadow: "0 1px 2px rgba(0, 0, 0, 0.75)",
        } as React.CSSProperties;
      case "box-black-on-white":
        return {
          boxSizing: "border-box",
          color: "#111111",
          backgroundColor: "rgba(255, 255, 255, 0.92)",
          padding: `${p}px ${px}px`,
          borderRadius: br,
          maxWidth: previewModel.subtitleBoxMaxWidth,
          textShadow: "none",
        } as React.CSSProperties;
      case "box-white-on-black":
      default:
        return {
          boxSizing: "border-box",
          color: "#ffffff",
          backgroundColor: "rgba(0, 0, 0, 0.82)",
          padding: `${p}px ${px}px`,
          borderRadius: br,
          maxWidth: previewModel.subtitleBoxMaxWidth,
          textShadow: "none",
        } as React.CSSProperties;
    }
  }, [previewModel, subtitleTheme]);

  if (!config || !previewModel) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
        正在准备导出预览...
      </div>
    );
  }

  const compositionWidth = config.composition.width;
  const compositionHeight = config.composition.height;
  const widthScale = frameSize.width > 0 ? frameSize.width / compositionWidth : 1;
  const heightScale = frameSize.height > 0 ? frameSize.height / compositionHeight : 1;
  const previewScale = Math.min(widthScale, heightScale);
  const centeredVideoStyle = getCenteredVideoStyle(sourceDimensions, compositionWidth, compositionHeight);

  return (
    <div className="flex min-h-0 w-full flex-1 items-center justify-center">
      <div
        ref={frameRef}
        className="relative flex h-full min-h-0 w-full items-center justify-center overflow-hidden rounded-[20px] border border-slate-200/80 bg-[linear-gradient(180deg,#f8fbff_0%,#edf4ff_100%)]"
      >
        <div
          className="absolute left-1/2 top-1/2 overflow-hidden rounded-[18px] border border-white/80 shadow-[0_22px_50px_-30px_rgba(15,23,42,0.35)]"
          style={{
            width: compositionWidth,
            height: compositionHeight,
            transform: `translate(-50%, -50%) scale(${previewScale || 1})`,
            transformOrigin: "center center",
            background: "linear-gradient(180deg, #f8fbff 0%, #eef4ff 100%)",
          }}
        >
          {sourceUrl ? (
            <video
              ref={videoRef}
              src={sourceUrl}
              muted
              playsInline
              preload="metadata"
              style={centeredVideoStyle}
            />
          ) : emptyStateMode === "blank" ? (
            <div className="h-full w-full bg-white" />
          ) : (
            <div className="flex h-full w-full items-center justify-center bg-[linear-gradient(180deg,#f8fbff_0%,#eef4ff_100%)] text-sm text-slate-500">
              当前会话缺少本地原视频，预览不可用
            </div>
          )}

          {previewModel?.activeTopic ? (
            <div
              style={{
                position: "absolute",
                top: previewModel.typography.chapterTop,
                left: previewModel.typography.chapterInsetX,
                right: previewModel.typography.chapterInsetX,
                pointerEvents: "none",
              }}
            >
              <div
                style={{
                  display: "inline-flex",
                  flexDirection: "column",
                  gap: previewModel.typography.chapterGap,
                  minWidth: previewModel.chapterCardStyleMinWidth,
                  width: previewModel.chapterCardStyleWidth,
                  maxWidth: previewModel.chapterCardStyleMaxWidth,
                  minHeight: previewModel.chapterCardMinHeight,
                  padding: `${previewModel.typography.chapterCardPaddingY}px ${previewModel.typography.chapterCardPaddingX}px`,
                  borderRadius: previewModel.typography.chapterCardRadius,
                  backgroundColor: "rgba(8, 12, 20, 0.74)",
                  border: "1px solid rgba(255, 255, 255, 0.2)",
                }}
              >
                <div
                  style={{
                    fontSize: previewModel.typography.chapterMetaFontSize,
                    fontWeight: 700,
                    fontFamily: OVERLAY_FONT_FAMILY,
                    color: "#8ee0ff",
                  }}
                >
                  CHAPTER {previewModel.activeTopicLabel}
                </div>
                <div
                  style={{
                    fontSize:
                      previewModel.activeTopicLayout?.fontSize ?? previewModel.typography.chapterTitleFontSize,
                    lineHeight: CHAPTER_TITLE_LINE_HEIGHT,
                    fontWeight: 800,
                    fontFamily: OVERLAY_FONT_FAMILY,
                    color: "#ffffff",
                    whiteSpace: "pre-line",
                    wordBreak: "normal",
                    overflowWrap: "anywhere",
                    maxWidth: previewModel.chapterTitleMaxWidth,
                  }}
                >
                  {previewModel.activeTopicLayout?.text ?? previewModel.activeTopic.title}
                </div>
              </div>
            </div>
          ) : null}

          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              bottom: previewModel?.typography.subtitleBottom,
              display: "flex",
              justifyContent: "center",
              pointerEvents: "none",
              paddingLeft: previewModel?.typography.subtitleSidePadding,
              paddingRight: previewModel?.typography.subtitleSidePadding,
            }}
          >
            <div
              style={{
                boxSizing: "border-box",
                color: "#ffffff",
                fontSize: resolvedSubtitleSet.fontSize,
                fontWeight: 700,
                fontFamily: OVERLAY_FONT_FAMILY,
                lineHeight: previewModel.subtitleLineHeight,
                textAlign: "center",
                whiteSpace: "pre-line",
                wordBreak: "normal",
                overflowWrap: "anywhere",
                overflow: "hidden",
                ...subtitleStyleOverrides,
              }}
            >
              {activeCaptionLayout?.text ?? subtitleRenderText}
            </div>
          </div>

          <div
            style={{
              position: "absolute",
              left: previewModel?.typography.progressInsetX,
              right: previewModel?.typography.progressInsetX,
              bottom: previewModel?.typography.progressBottom,
              height: previewModel?.typography.progressHeight,
              pointerEvents: "none",
            }}
          >
            <div
              style={{
                position: "relative",
                width: "100%",
                height: "100%",
                borderRadius: previewModel?.typography.progressRadius,
                overflow: "hidden",
                backgroundColor: "rgba(16, 22, 30, 0.42)",
                border: "1px solid rgba(255, 255, 255, 0.22)",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: `${(previewModel?.progressRatio ?? 0) * 100}%`,
                  background:
                    "linear-gradient(90deg, rgba(29, 217, 255, 0.58), rgba(66, 240, 180, 0.45))",
                }}
              />
              {(previewModel?.topicSegments ?? []).map((segment) => (
                <div
                  key={`preview-segment-${segment.index}-${segment.startRatio}-${segment.endRatio}`}
                  style={{
                    position: "absolute",
                    top: 0,
                    bottom: 0,
                    left: `${segment.startRatio * 100}%`,
                    width: `${(segment.endRatio - segment.startRatio) * 100}%`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    overflow: "hidden",
                    borderRight: "1px solid rgba(255, 255, 255, 0.2)",
                    backgroundColor:
                      segment.index ===
                      (previewModel?.activeTopicLabel ? Number(previewModel.activeTopicLabel.split("/")[0]) - 1 : -1)
                        ? "rgba(255, 255, 255, 0.08)"
                        : "rgba(255, 255, 255, 0.02)",
                  }}
                >
                  <div
                    style={{
                      maxWidth: "100%",
                      padding: `0 ${previewModel?.typography.progressLabelPaddingX ?? 0}px`,
                      fontSize: segment.labelFit.fontSize,
                      fontWeight: 700,
                      fontFamily: OVERLAY_FONT_FAMILY,
                      lineHeight: previewModel?.progressLabelLineHeight ?? 1.2,
                      whiteSpace: previewModel?.allowWrappedProgressLabels ? "pre-line" : "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      textAlign: "center",
                      color:
                        segment.index ===
                        (previewModel?.activeTopicLabel ? Number(previewModel.activeTopicLabel.split("/")[0]) - 1 : -1)
                          ? "#ffffff"
                          : "rgba(238, 244, 255, 0.84)",
                    }}
                  >
                    {segment.labelFit.visible ? segment.labelFit.text : ""}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
