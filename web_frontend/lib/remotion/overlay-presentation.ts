import type {CSSProperties} from "react";

export const SUBTITLE_BOX_PADDING_X_EM = 0.34;
export const SUBTITLE_BOX_PADDING_Y_EM = 0.19;
export const SUBTITLE_BOX_RADIUS_EM = 0.24;
export const CHAPTER_CARD_GAP_EM = 0.2;
export const CHAPTER_CARD_PADDING_X_EM = 0.62;
export const CHAPTER_CARD_PADDING_Y_EM = 0.34;
export const CHAPTER_CARD_RADIUS_EM = 0.36;
export const PROGRESS_LABEL_PADDING_X_EM = 0.22;
export const SUBTITLE_PROGRESS_GAP_EM = 0.34;

const round = (value: number): number => Math.round(value);

export const normalizeSubtitleTheme = (subtitleTheme: string | undefined): "stroke" | "stroke-white" =>
  subtitleTheme === "stroke-white" || subtitleTheme === "white" ? "stroke-white" : "stroke";

export const isTextSubtitleTheme = (_subtitleTheme: string | undefined): boolean => true;

export const isBoxedSubtitleTheme = (_subtitleTheme: string | undefined): boolean => false;

export type SubtitleTextLayerSpec = {
  key: string;
  color: string;
  opacity: number;
  translateXEm: number;
  translateYEm: number;
};

export type OverlayVisualLayerSpec = {
  key: string;
  kind: "shadow" | "surface" | "shine" | "accent";
  style: CSSProperties;
};

export const getSubtitleTextFillColor = (subtitleTheme: string | undefined): string => {
  switch (normalizeSubtitleTheme(subtitleTheme)) {
    case "stroke-white":
      return "#f9fbff";
    case "stroke":
    default:
      return "#111827";
  }
};

export const getSubtitleTextShadowLayers = (
  subtitleTheme: string | undefined,
): SubtitleTextLayerSpec[] => {
  switch (normalizeSubtitleTheme(subtitleTheme)) {
    case "stroke-white":
      return [
        {key: "outline-top", color: "#0f172a", opacity: 0.78, translateXEm: 0, translateYEm: -0.025},
        {key: "outline-right", color: "#0f172a", opacity: 0.78, translateXEm: 0.025, translateYEm: 0},
        {key: "outline-bottom", color: "#0f172a", opacity: 0.78, translateXEm: 0, translateYEm: 0.025},
        {key: "outline-left", color: "#0f172a", opacity: 0.78, translateXEm: -0.025, translateYEm: 0},
        {key: "shadow-near", color: "#020617", opacity: 0.36, translateXEm: 0, translateYEm: 0.07},
        {key: "shadow-far", color: "#020617", opacity: 0.22, translateXEm: 0, translateYEm: 0.13},
      ];
    case "stroke":
    default:
      return [
        {key: "outline-top", color: "#ffffff", opacity: 0.86, translateXEm: 0, translateYEm: -0.025},
        {key: "outline-right", color: "#ffffff", opacity: 0.86, translateXEm: 0.025, translateYEm: 0},
        {key: "outline-bottom", color: "#ffffff", opacity: 0.86, translateXEm: 0, translateYEm: 0.025},
        {key: "outline-left", color: "#ffffff", opacity: 0.86, translateXEm: -0.025, translateYEm: 0},
        {key: "shadow-glow", color: "#ffffff", opacity: 0.38, translateXEm: 0, translateYEm: 0.08},
        {key: "shadow-contrast", color: "#0f172a", opacity: 0.12, translateXEm: 0, translateYEm: 0.04},
      ];
  }
};

export const getSubtitleTextTreatment = (
  subtitleTheme: string | undefined,
): Pick<CSSProperties, "color"> => {
  return {
    color: getSubtitleTextFillColor(subtitleTheme),
  };
};

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
    case "stroke-white":
      return {
        ...getSubtitleTextTreatment(subtitleTheme),
        maxWidth: textMaxWidth || boxMaxWidth,
      };
    case "stroke":
    default:
      return {
        ...getSubtitleTextTreatment(subtitleTheme),
        maxWidth: textMaxWidth || boxMaxWidth,
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

const chapterAccentColors = [
  "#8ee0ff",
  "#ffb38a",
  "#9dffc3",
  "#c4a8ff",
  "#ffd166",
  "#ff8ad1",
  "#7fdbff",
];

export const getChapterAccentColor = (activeTopicIndex = 0): string =>
  chapterAccentColors[activeTopicIndex % chapterAccentColors.length] ?? "#8ee0ff";

export const getChapterCardStyle = ({
  cardMaxWidth,
}: {
  cardMaxWidth: number;
  activeTopicIndex?: number;
}): CSSProperties => {
  return {
    position: "relative",
    display: "inline-flex",
    flexDirection: "column",
    gap: `${CHAPTER_CARD_GAP_EM}em`,
    width: "fit-content",
    maxWidth: cardMaxWidth,
    padding: `${CHAPTER_CARD_PADDING_Y_EM}em ${CHAPTER_CARD_PADDING_X_EM}em`,
    borderRadius: `${CHAPTER_CARD_RADIUS_EM}em`,
    overflow: "hidden",
    boxSizing: "border-box",
  };
};

export const getChapterCardBackdropLayers = ({
  activeTopicIndex = 0,
}: {
  activeTopicIndex?: number;
} = {}): OverlayVisualLayerSpec[] => {
  const accent = getChapterAccentColor(activeTopicIndex);
  return [
    {
      key: "depth",
      kind: "shadow",
      style: {
        position: "absolute",
        inset: "0",
        backgroundColor: "rgba(0, 0, 0, 0.2)",
        transform: "translate(0.08em, 0.1em)",
        borderRadius: "inherit",
        opacity: 0.42,
      },
    },
    {
      key: "surface",
      kind: "surface",
      style: {
        position: "absolute",
        inset: "0",
        background:
          "linear-gradient(180deg, rgba(37, 43, 58, 0.66) 0%, rgba(13, 18, 27, 0.5) 100%)",
        borderRadius: "inherit",
      },
    },
    {
      key: "shine",
      kind: "shine",
      style: {
        position: "absolute",
        left: "0.08em",
        right: "0.08em",
        top: "0.06em",
        height: "0.08em",
        backgroundColor: "rgba(255, 255, 255, 0.14)",
        borderRadius: "999px",
      },
    },
    {
      key: "accent",
      kind: "accent",
      style: {
        position: "absolute",
        left: "0",
        top: "0",
        bottom: "0",
        width: "0.11em",
        backgroundColor: accent,
      },
    },
  ];
};

export const getProgressTrackBackdropLayers = (): OverlayVisualLayerSpec[] => [
  {
    key: "surface",
    kind: "surface",
    style: {
      position: "absolute",
      inset: "0",
      background:
        "linear-gradient(180deg, rgba(26, 34, 47, 0.58) 0%, rgba(11, 17, 26, 0.44) 100%)",
      borderRadius: "inherit",
    },
  },
  {
    key: "shine",
    kind: "shine",
    style: {
      position: "absolute",
      left: "0",
      right: "0",
      top: "0",
      height: "34%",
      backgroundColor: "rgba(255, 255, 255, 0.08)",
      borderTopLeftRadius: "inherit",
      borderTopRightRadius: "inherit",
    },
  },
];

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
