import type {CSSProperties} from "react";

export const SUBTITLE_BOX_PADDING_X_EM = 0.34;
export const SUBTITLE_BOX_PADDING_Y_EM = 0.19;
export const SUBTITLE_BOX_RADIUS_EM = 0.24;
export const CHAPTER_CARD_GAP_EM = 0.18;
export const CHAPTER_CARD_PADDING_X_EM = 0.38;
export const CHAPTER_CARD_PADDING_Y_EM = 0.32;
export const CHAPTER_CARD_RADIUS_EM = 0.36;
export const PROGRESS_LABEL_PADDING_X_EM = 0.22;

const round = (value: number): number => Math.round(value);

export const isTextSubtitleTheme = (subtitleTheme: string | undefined): boolean =>
  subtitleTheme === "text-black" || subtitleTheme === "text-white";

export const isBoxedSubtitleTheme = (subtitleTheme: string | undefined): boolean =>
  subtitleTheme === "box-white-on-black" || subtitleTheme === "box-black-on-white";

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
  switch (subtitleTheme) {
    case "text-black":
      return {
        color: "#111111",
        backgroundColor: "transparent",
        padding: "0",
        borderRadius: 0,
        maxWidth: textMaxWidth,
        textShadow: "0 1px 1px rgba(255, 255, 255, 0.45)",
      };
    case "text-white":
      return {
        color: "#ffffff",
        backgroundColor: "transparent",
        padding: "0",
        borderRadius: 0,
        maxWidth: textMaxWidth,
        textShadow: "0 1px 2px rgba(0, 0, 0, 0.75)",
      };
    case "box-black-on-white":
      return {
        boxSizing: "border-box",
        color: "#111111",
        backgroundColor: "rgba(255, 255, 255, 0.92)",
        padding: `${SUBTITLE_BOX_PADDING_Y_EM}em ${SUBTITLE_BOX_PADDING_X_EM}em`,
        borderRadius: `${SUBTITLE_BOX_RADIUS_EM}em`,
        maxWidth: boxMaxWidth,
        textShadow: "none",
      };
    case "box-white-on-black":
    default:
      return {
        boxSizing: "border-box",
        color: "#ffffff",
        backgroundColor: "rgba(0, 0, 0, 0.82)",
        padding: `${SUBTITLE_BOX_PADDING_Y_EM}em ${SUBTITLE_BOX_PADDING_X_EM}em`,
        borderRadius: `${SUBTITLE_BOX_RADIUS_EM}em`,
        maxWidth: boxMaxWidth,
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

export const getChapterCardStyle = ({
  cardMaxWidth,
}: {
  cardMaxWidth: number;
}): CSSProperties => ({
  display: "inline-flex",
  flexDirection: "column",
  gap: `${CHAPTER_CARD_GAP_EM}em`,
  width: "fit-content",
  maxWidth: cardMaxWidth,
  padding: `${CHAPTER_CARD_PADDING_Y_EM}em ${CHAPTER_CARD_PADDING_X_EM}em`,
  borderRadius: `${CHAPTER_CARD_RADIUS_EM}em`,
  backgroundColor: "rgba(8, 12, 20, 0.74)",
  border: "1px solid rgba(255, 255, 255, 0.2)",
  boxSizing: "border-box",
});

export const getProgressLabelPaddingX = (fontSize: number): number =>
  Math.max(2, round(fontSize * PROGRESS_LABEL_PADDING_X_EM * 4) / 4);
