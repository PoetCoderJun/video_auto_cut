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
  { value: "box-white-on-black", label: "黑底白字" },
  { value: "box-black-on-white", label: "白底黑字" },
  { value: "text-white", label: "白字透明" },
  { value: "text-black", label: "黑字透明" },
];
