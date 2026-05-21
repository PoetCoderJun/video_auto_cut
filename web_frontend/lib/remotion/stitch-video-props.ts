import type {OverlayScaleControls} from "./overlay-controls";
import type {SubtitleTheme, WebRenderConfig} from "../api";

export const buildStitchVideoInputProps = ({
  config,
  src,
  subtitleTheme,
  overlayControls,
}: {
  config: WebRenderConfig;
  src: string;
  subtitleTheme: SubtitleTheme;
  overlayControls: OverlayScaleControls;
}) => {
  const baseProps = config.input_props;
  return {
    ...baseProps,
    src,
    captions: baseProps.captions,
    topics: baseProps.topics,
    segments: baseProps.segments,
    fps: config.composition.fps,
    width: config.composition.width,
    height: config.composition.height,
    overlayReferenceWidth: baseProps.overlayReferenceWidth,
    overlayReferenceHeight: baseProps.overlayReferenceHeight,
    subtitleTheme,
    subtitleScale: overlayControls.subtitleScale,
    subtitleYPercent: overlayControls.subtitleYPercent,
    progressScale: overlayControls.progressScale,
    progressYPercent: overlayControls.progressYPercent,
    chapterScale: overlayControls.chapterScale,
    showSubtitles: overlayControls.showSubtitles,
    showHighlights: overlayControls.showHighlights,
    showProgress: overlayControls.showProgress,
    showChapter: overlayControls.showChapter,
    progressLabelMode: overlayControls.progressLabelMode,
  };
};
