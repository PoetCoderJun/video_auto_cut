import type {
  RenderCaption,
  RenderSegment,
  RenderTopic,
  SubtitleTheme,
  WebRenderConfig,
} from "@/lib/api";

import type {OverlayScaleControls} from "./overlay-controls";

export type MockResolutionPreset = {
  id: string;
  label: string;
  width: number;
  height: number;
  fps?: number;
};

export type MockScenarioPreset = {
  id: string;
  label: string;
  description: string;
  previewTimeSec: number;
  inspectTimesSec: readonly number[];
  durationSec: number;
  captions: RenderCaption[];
  topics: RenderTopic[];
  segments: RenderSegment[];
  defaultSubtitleTheme?: SubtitleTheme;
  defaultOverlayControls?: OverlayScaleControls;
};

export const MOCK_RESOLUTION_PRESETS: MockResolutionPreset[] = [
  {id: "landscape-480", label: "低清横屏 854x480", width: 854, height: 480},
  {id: "landscape-720", label: "低分横屏 1280x720", width: 1280, height: 720},
  {id: "landscape-1080", label: "常规横屏 1920x1080", width: 1920, height: 1080},
  {id: "landscape-2k", label: "2K 横屏 2560x1440", width: 2560, height: 1440},
  {id: "landscape-4k", label: "4K 横屏 3840x2160", width: 3840, height: 2160},
  {id: "portrait-360", label: "低分竖屏 360x640", width: 360, height: 640},
  {id: "portrait-544", label: "手机竖屏 544x960", width: 544, height: 960},
  {id: "portrait-720", label: "手机竖屏 720x1280", width: 720, height: 1280},
  {id: "portrait-1080", label: "手机竖屏 1080x1920", width: 1080, height: 1920},
  {id: "portrait-2k", label: "2K 竖屏 1440x2560", width: 1440, height: 2560},
  {id: "portrait-4k", label: "4K 竖屏 2160x3840", width: 2160, height: 3840},
  {id: "square-1080", label: "方形 1080x1080", width: 1080, height: 1080},
  {id: "ultrawide-1440", label: "超宽 3440x1440", width: 3440, height: 1440},
];

export const MOCK_SCENARIO_PRESETS: MockScenarioPreset[] = [
  {
    id: "chapter-long-wrap",
    label: "章节长标题压测",
    description: "观察章节卡片在临界宽度下是否能自然换行，而不是突然缩字或留白过大。",
    previewTimeSec: 4,
    inspectTimesSec: [4, 6],
    durationSec: 8,
    captions: [
      {
        index: 1,
        start: 1.2,
        end: 6.8,
        text: "那我可以跟他聊聊。如果他什么都没有做过，他只是关心收益的话",
      },
    ],
    topics: [
      {title: "这是一个专门用来压测章节卡片换行和字号过渡是否自然的长标题", start: 0, end: 8},
    ],
    segments: [{start: 41, end: 49}],
    defaultSubtitleTheme: "box-white-on-black",
    defaultOverlayControls: {
      subtitleScale: 1.12,
      progressScale: 1.18,
      chapterScale: 1,
      progressLabelMode: "auto",
    },
  },
  {
    id: "chapter-short-compact",
    label: "章节短标题紧凑度",
    description: "观察单行章节标题时，卡片是否能贴近文字，不再显得空。",
    previewTimeSec: 3.5,
    inspectTimesSec: [3, 5],
    durationSec: 8,
    captions: [
      {
        index: 1,
        start: 1,
        end: 5.8,
        text: "真正重要的不是你知道多少，而是你能不能把结论讲得足够清楚。",
      },
    ],
    topics: [{title: "核心结论", start: 0, end: 8}],
    segments: [{start: 41, end: 49}],
    defaultSubtitleTheme: "box-white-on-black",
    defaultOverlayControls: {
      subtitleScale: 1.08,
      progressScale: 1.12,
      chapterScale: 0.96,
      progressLabelMode: "auto",
    },
  },
  {
    id: "landscape-progress-balance",
    label: "横屏章节与进度条平衡",
    description: "同时看横屏下的章节块宽度、标题换行，以及多段进度条标题的可读性。",
    previewTimeSec: 7.2,
    inspectTimesSec: [2, 7],
    durationSec: 12,
    captions: [
      {
        index: 1,
        start: 6.4,
        end: 10.2,
        text: "横屏场景更容易出现章节条变成长横幅，所以这里重点看标题和背景是否还够紧凑。",
      },
    ],
    topics: [
      {title: "为什么开头会拖沓", start: 0, end: 3},
      {title: "怎样保留真实感受", start: 3, end: 6},
      {title: "最后怎么落地执行", start: 6, end: 9},
      {title: "AI 协作怎么不失控", start: 9, end: 12},
    ],
    segments: [
      {start: 41, end: 44},
      {start: 44, end: 47},
      {start: 47, end: 50},
      {start: 50, end: 53},
    ],
    defaultSubtitleTheme: "box-white-on-black",
    defaultOverlayControls: {
      subtitleScale: 1,
      progressScale: 1,
      chapterScale: 0.94,
      progressLabelMode: "single",
    },
  },
];

export const DEFAULT_MOCK_RESOLUTION_ID = "portrait-544";
export const DEFAULT_MOCK_SCENARIO_ID = "chapter-long-wrap";
export const DEFAULT_COMPARE_RESOLUTION_IDS = [
  "landscape-480",
  "landscape-4k",
  "portrait-360",
  "portrait-544",
  "portrait-4k",
  "square-1080",
  "ultrawide-1440",
] as const;

const DEFAULT_FPS = 27;

export const getMockResolutionPreset = (id: string): MockResolutionPreset =>
  MOCK_RESOLUTION_PRESETS.find((preset) => preset.id === id) ??
  MOCK_RESOLUTION_PRESETS.find((preset) => preset.id === DEFAULT_MOCK_RESOLUTION_ID) ??
  MOCK_RESOLUTION_PRESETS[0];

export const getMockScenarioPreset = (id: string): MockScenarioPreset =>
  MOCK_SCENARIO_PRESETS.find((preset) => preset.id === id) ??
  MOCK_SCENARIO_PRESETS.find((preset) => preset.id === DEFAULT_MOCK_SCENARIO_ID) ??
  MOCK_SCENARIO_PRESETS[0];

export const buildMockRenderConfig = ({
  resolution,
  scenario,
  subtitleTheme,
  overlayControls,
}: {
  resolution: MockResolutionPreset;
  scenario: MockScenarioPreset;
  subtitleTheme: SubtitleTheme;
  overlayControls: OverlayScaleControls;
}): WebRenderConfig => {
  const fps = resolution.fps ?? DEFAULT_FPS;
  const durationInFrames = Math.max(1, Math.round(fps * scenario.durationSec));

  return {
    output_name: `${scenario.id}-${resolution.width}x${resolution.height}.mp4`,
    composition: {
      id: "StitchVideoWeb",
      fps,
      width: resolution.width,
      height: resolution.height,
      durationInFrames,
    },
    input_props: {
      src: "",
      fps,
      width: resolution.width,
      height: resolution.height,
      captions: scenario.captions,
      topics: scenario.topics,
      segments: scenario.segments,
      subtitleTheme,
      subtitleScale: overlayControls.subtitleScale,
      subtitleYPercent: overlayControls.subtitleYPercent,
      progressScale: overlayControls.progressScale,
      progressYPercent: overlayControls.progressYPercent,
      chapterScale: overlayControls.chapterScale,
      showSubtitles: overlayControls.showSubtitles,
      showProgress: overlayControls.showProgress,
      showChapter: overlayControls.showChapter,
      progressLabelMode: overlayControls.progressLabelMode,
    },
  };
};
