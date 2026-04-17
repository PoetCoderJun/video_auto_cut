import type {CSSProperties} from "react";

export const SUBTITLE_BOX_PADDING_X_EM = 0.34;
export const SUBTITLE_BOX_PADDING_Y_EM = 0.19;
export const SUBTITLE_BOX_RADIUS_EM = 0.24;
export const CHAPTER_CARD_GAP_EM = 0.18;
export const CHAPTER_CARD_PADDING_X_EM = 0.38;
export const CHAPTER_CARD_PADDING_Y_EM = 0.32;
export const CHAPTER_CARD_RADIUS_EM = 0.36;
export const PROGRESS_LABEL_PADDING_X_EM = 0.22;
export const SUBTITLE_PROGRESS_GAP_EM = 0.34;

const round = (value: number): number => Math.round(value);

export const normalizeSubtitleTheme = (subtitleTheme: string | undefined): "black" | "white" =>
  subtitleTheme === "white" || subtitleTheme === "box-black-on-white" || subtitleTheme === "text-black"
    ? "white"
    : "black";

export const isTextSubtitleTheme = (_subtitleTheme: string | undefined): boolean => false;

export const isBoxedSubtitleTheme = (_subtitleTheme: string | undefined): boolean => true;

export const getSubtitleBoxMaxWidth = ({
  width,
  maxWidthRatio,
  safeWidthRatio,
}: {
  width: number;
  maxWidthRatio: number;
  safeWidthRatio: number;
}): number => Math.max(1, width * maxWidthRatio * safeWidthRatio);

export const getSubtitleTextMaxWidth = ({
  boxMaxWidth,
  fontSize,
  isBoxedTheme,
}: {
  boxMaxWidth: number;
  fontSize: number;
  isBoxedTheme: boolean;
}): number => {
  if (!isBoxedTheme) return Math.max(1, boxMaxWidth);
  const horizontalPadding = fontSize * SUBTITLE_BOX_PADDING_X_EM * 2;
  return Math.max(1, boxMaxWidth - horizontalPadding);
};

export const getSubtitleThemeFitWidth = ({
  maxWidth,
  subtitleScale = 1,
  isTextTheme,
}: {
  maxWidth: number;
  subtitleScale?: number;
  isTextTheme: boolean;
}): number => {
  if (!isTextTheme) {
    return Math.max(1, maxWidth);
  }
  return Math.max(1, maxWidth / Math.max(0.7, Math.min(1.45, subtitleScale)));
};

export const getSubtitleThemeRenderFontSize = ({
  fittedFontSize,
  subtitleScale = 1,
  isTextTheme,
}: {
  fittedFontSize: number;
  subtitleScale?: number;
  isTextTheme: boolean;
}): number => {
  const renderedFontSize = isTextTheme
    ? fittedFontSize * Math.max(0.7, Math.min(1.45, subtitleScale))
    : fittedFontSize;
  return Math.max(1, round(renderedFontSize));
};

export const getSubtitleThemeStyle = ({
  subtitleTheme,
  boxMaxWidth,
  textMaxWidth,
}: {
  subtitleTheme: string | undefined;
  boxMaxWidth: number;
  textMaxWidth: number;
}): CSSProperties => {
  switch (normalizeSubtitleTheme(subtitleTheme)) {
    case "white":
      return {
        boxSizing: "border-box",
        color: "#111111",
        backgroundColor: "rgba(255, 255, 255, 0.92)",
        padding: `${SUBTITLE_BOX_PADDING_Y_EM}em ${SUBTITLE_BOX_PADDING_X_EM}em`,
        borderRadius: `${SUBTITLE_BOX_RADIUS_EM}em`,
        maxWidth: boxMaxWidth || textMaxWidth,
        textShadow: "none",
      };
    case "black":
    default:
      return {
        boxSizing: "border-box",
        color: "#ffffff",
        backgroundColor: "rgba(0, 0, 0, 0.82)",
        padding: `${SUBTITLE_BOX_PADDING_Y_EM}em ${SUBTITLE_BOX_PADDING_X_EM}em`,
        borderRadius: `${SUBTITLE_BOX_RADIUS_EM}em`,
        maxWidth: boxMaxWidth || textMaxWidth,
        textShadow: "none",
      };
  }
};

export const getChapterCardTitleMaxWidth = ({
  cardMaxWidth,
  titleFontSize,
}: {
  cardMaxWidth: number;
  titleFontSize: number;
}): number =>
  Math.max(1, cardMaxWidth - titleFontSize * CHAPTER_CARD_PADDING_X_EM * 2);

const chapterColors = [
  "rgba(8, 12, 20, 0.74)",
  "rgba(20, 8, 8, 0.74)",
  "rgba(8, 20, 8, 0.74)",
  "rgba(8, 8, 20, 0.74)",
  "rgba(20, 20, 8, 0.74)",
  "rgba(8, 20, 20, 0.74)",
  "rgba(20, 8, 20, 0.74)",
];

export const getChapterCardStyle = ({
  cardMaxWidth,
  activeTopicIndex = 0,
}: {
  cardMaxWidth: number;
  activeTopicIndex?: number;
}): CSSProperties => ({
  display: "inline-flex",
  flexDirection: "column",
  gap: `${CHAPTER_CARD_GAP_EM}em`,
  width: "fit-content",
  maxWidth: cardMaxWidth,
  padding: `${CHAPTER_CARD_PADDING_Y_EM}em ${CHAPTER_CARD_PADDING_X_EM}em`,
  borderRadius: `${CHAPTER_CARD_RADIUS_EM}em`,
  backgroundColor: chapterColors[activeTopicIndex % chapterColors.length] ?? "rgba(8, 12, 20, 0.74)",
  border: "1px solid rgba(255, 255, 255, 0.2)",
  boxSizing: "border-box",
});

export const getProgressLabelPaddingX = (fontSize: number): number =>
  Math.max(2, round(fontSize * PROGRESS_LABEL_PADDING_X_EM * 4) / 4);

export const reserveSubtitleBottomForProgress = ({
  subtitleBottom,
  progressBottom,
  progressHeight,
  subtitleFontSize,
  showProgress,
}: {
  subtitleBottom: number;
  progressBottom: number;
  progressHeight: number;
  subtitleFontSize: number;
  showProgress: boolean;
}): number => {
  if (!showProgress) return subtitleBottom;
  const gap = Math.max(12, round(subtitleFontSize * SUBTITLE_PROGRESS_GAP_EM));
  return Math.max(subtitleBottom, progressBottom + progressHeight + gap);
};
