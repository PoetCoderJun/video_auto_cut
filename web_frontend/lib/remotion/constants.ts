import type { ProgressLabelMode, SubtitleTheme } from "../api";

export const PROGRESS_LABEL_MODE_OPTIONS: Array<{
  value: ProgressLabelMode;
  label: string;
}> = [
  { value: "auto", label: "自动" },
  { value: "double", label: "双行" },
  { value: "single", label: "单行" },
];

export const SUBTITLE_THEME_OPTIONS: Array<{
  value: SubtitleTheme;
  label: string;
}> = [
  { value: "black", label: "黑底" },
  { value: "white", label: "白底" },
];
