"use client";

import React from "react";
import {useMemo} from "react";

import type {WebRenderConfig} from "@/lib/api";
import {
  applyOverlayScaleToTypography,
  normalizeOverlayScaleControls,
  type OverlayScaleControls,
  type ProgressLabelMode,
} from "@/lib/remotion/overlay-controls";
import {
  getProgressLabelPaddingX,
  getSubtitleBoxMaxWidth,
  getSubtitleTextMaxWidth,
  getSubtitleThemeFitWidth,
  getSubtitleThemeRenderFontSize,
  getSubtitleThemeStyle,
  isBoxedSubtitleTheme,
  isTextSubtitleTheme,
} from "@/lib/remotion/overlay-presentation";
import type {SubtitleTheme} from "@/lib/remotion/stitch-video-web";
import {
  CHAPTER_TITLE_LINE_HEIGHT,
  fitChapterTitleToBox,
  fitUniformAdaptiveTextToBox,
  fitUniformSingleLineText,
  fitUniformTextToBox,
  getChapterCardLayoutMetrics,
  getResponsiveOverlayTypography,
  getSafeSubtitleScale,
  getSubtitleLineHeight,
  OVERLAY_FONT_FAMILY,
  prepareCaptionDisplayText,
} from "@/lib/remotion/typography";

const clamp = (value: number, min: number, max: number): number => {
  if (!Number.isFinite(value)) return min;
  if (value < min) return min;
  if (value > max) return max;
  return value;
};

const findActiveTopicIndexByStart = (
  topics: Array<{start: number}>,
  timeSec: number,
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

export type PreviewModel = ReturnType<typeof buildPreviewModel>;

function buildPreviewModel({
  clampedPreviewTime,
  config,
  overlayControls,
  subtitleTheme,
  totalDuration,
}: {
  clampedPreviewTime: number;
  config: WebRenderConfig;
  overlayControls: OverlayScaleControls;
  subtitleTheme: SubtitleTheme;
  totalDuration: number;
}) {
  const composition = config.composition;
  const width = composition.width;
  const height = composition.height;
  const normalizedControls = normalizeOverlayScaleControls(overlayControls);
  const baseTypography = getResponsiveOverlayTypography({width, height});
  const safeSubtitleScale = getSafeSubtitleScale({
    requestedScale: normalizedControls.subtitleScale,
    width,
    height,
    baseSubtitleFontSize: baseTypography.subtitleFontSize,
  });
  const typography = applyOverlayScaleToTypography(baseTypography, {
    ...normalizedControls,
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
    (caption) => clampedPreviewTime >= caption.start && clampedPreviewTime < caption.end,
  );
  const activeCaption = activeCaptionIndex >= 0 ? wrappedCaptions[activeCaptionIndex] : null;
  const chapterCardMetrics = getChapterCardLayoutMetrics({
    width,
    typography,
  });
  const subtitleBoxedTheme = isBoxedSubtitleTheme(subtitleTheme);
  const subtitleThemeIsText = isTextSubtitleTheme(subtitleTheme);
  const subtitleLayoutTypography = subtitleThemeIsText ? baseTypography : typography;
  const subtitleBoxMaxWidth = getSubtitleBoxMaxWidth({
    width,
    maxWidthRatio: typography.subtitleMaxWidthRatio,
    safeWidthRatio: typography.subtitleSafeWidthRatio,
  });
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
  const progressLabelPaddingX = getProgressLabelPaddingX(typography.progressLabelFontSize);
  const topicSegmentsForLayout = normalizedTopics
    .map((topic, index) => {
      const startRatio = clamp(topic.start / totalDuration, 0, 1);
      const endRatio = clamp(topic.end / totalDuration, 0, 1);
      if (endRatio <= startRatio) return null;
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
        item,
      ): item is {
        title: string;
        startRatio: number;
        endRatio: number;
        index: number;
        segmentWidth: number;
      } => item !== null,
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
          Math.floor(typography.progressHeight / (progressLabelLineHeight * 2)),
        ),
        maxHeight: typography.progressHeight,
        lineHeight: progressLabelLineHeight,
        targetWidthRatio: 0.9,
        horizontalPadding: progressLabelPaddingX,
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
          Math.floor(typography.progressHeight * 0.58),
        ),
        maxHeight: typography.progressHeight,
        lineHeight: 1.2,
        targetWidthRatio: 0.84,
        horizontalPadding: progressLabelPaddingX,
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
    chapterCardMaxWidth: chapterCardMetrics.cardMaxWidth,
    chapterTitleMaxWidth: chapterCardMetrics.titleMaxWidth,
    subtitleYPercent: normalizedControls.subtitleYPercent,
    progressYPercent: normalizedControls.progressYPercent,
    showSubtitles: normalizedControls.showSubtitles,
    showProgress: normalizedControls.showProgress,
    showChapter: normalizedControls.showChapter,
    subtitleSafeScale: safeSubtitleScale,
    subtitleFitMaxWidth,
    subtitleThemeIsText,
    subtitleLayoutTypography,
  };
}

export function useOverlayLayout({
  clampedPreviewTime,
  config,
  overlayControls,
  subtitleTheme,
  totalDuration,
}: {
  clampedPreviewTime: number;
  config: WebRenderConfig | null;
  overlayControls: OverlayScaleControls;
  subtitleTheme: SubtitleTheme;
  totalDuration: number;
}) {
  const previewModel = useMemo(
    () =>
      config
        ? buildPreviewModel({
            clampedPreviewTime,
            config,
            overlayControls,
            subtitleTheme,
            totalDuration,
          })
        : null,
    [clampedPreviewTime, config, overlayControls, subtitleTheme, totalDuration],
  );

  const subtitleInitialFontSize = previewModel?.subtitleLayoutTypography.subtitleFontSize ?? 0;
  const subtitleRenderText = previewModel?.activeCaption?.displayText ?? "";
  const subtitleMinFontSize = previewModel
    ? Math.max(
        previewModel.composition.height > previewModel.composition.width ? 23 : 26,
        Math.floor(
          previewModel.subtitleLayoutTypography.subtitleFontSize *
            (previewModel.composition.height > previewModel.composition.width ? 0.44 : 0.68),
        ),
      )
    : 0;
  const resolvedSubtitleSet = useMemo(
    () =>
      fitUniformAdaptiveTextToBox({
        items: (previewModel?.wrappedCaptions ?? []).map((caption) => ({
          text: caption.displayText,
          maxWidth: previewModel?.subtitleFitMaxWidth ?? 1,
        })),
        baseFontSize: subtitleInitialFontSize,
        minFontSize: subtitleMinFontSize,
        preferredMaxLines: 2,
        fallbackMaxLines: 3,
        finalMaxLines: 4,
        fontWeight: 700,
        fontFamily: OVERLAY_FONT_FAMILY,
      }),
    [previewModel?.subtitleFitMaxWidth, previewModel?.wrappedCaptions, subtitleInitialFontSize, subtitleMinFontSize],
  );
  const activeCaptionLayout =
    previewModel && previewModel.activeCaptionIndex >= 0
      ? resolvedSubtitleSet.labels[previewModel.activeCaptionIndex]
      : null;
  const subtitleRenderFontSize = useMemo(
    () =>
      previewModel
        ? getSubtitleThemeRenderFontSize({
            fittedFontSize: resolvedSubtitleSet.fontSize,
            subtitleScale: previewModel.subtitleSafeScale,
            isTextTheme: previewModel.subtitleThemeIsText,
          })
        : 0,
    [previewModel, resolvedSubtitleSet.fontSize],
  );

  const subtitleStyleOverrides = useMemo(() => {
    if (!previewModel) return {};
    return getSubtitleThemeStyle({
      subtitleTheme,
      boxMaxWidth: previewModel.subtitleBoxMaxWidth,
      textMaxWidth: previewModel.subtitleTextMaxWidth,
    });
  }, [previewModel, subtitleTheme]);

  return {
    activeCaptionLayout,
    previewModel,
    subtitleRenderFontSize,
    subtitleRenderText,
    subtitleStyleOverrides,
  };
}

export {CHAPTER_TITLE_LINE_HEIGHT, OVERLAY_FONT_FAMILY};
