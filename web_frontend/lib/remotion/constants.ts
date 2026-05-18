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
  { value: "stroke-white", label: "标准白字" },
  { value: "stroke", label: "标准黑字" },
];
