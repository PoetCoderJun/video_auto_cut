"use client";

import {Suspense, useEffect, useMemo, useState} from "react";
import {useSearchParams} from "next/navigation";

import ExportFramePreview from "@/components/export-frame-preview";
import {Button} from "@/components/ui/button";
import {Card, CardContent} from "@/components/ui/card";
import {Checkbox} from "@/components/ui/checkbox";
import {Select, SelectContent, SelectItem, SelectTrigger, SelectValue} from "@/components/ui/select";
import type {ProgressLabelMode, SubtitleTheme} from "@/lib/api";
import {
  buildMockRenderConfig,
  DEFAULT_COMPARE_RESOLUTION_IDS,
  DEFAULT_MOCK_RESOLUTION_ID,
  DEFAULT_MOCK_SCENARIO_ID,
  getMockResolutionPreset,
  getMockScenarioPreset,
  MOCK_RESOLUTION_PRESETS,
  MOCK_SCENARIO_PRESETS,
  type MockScenarioPreset,
} from "@/lib/remotion/dev-export-preview-presets";
import {
  DEFAULT_OVERLAY_CONTROLS,
  OVERLAY_POSITION_LIMITS,
  OVERLAY_SCALE_LIMITS,
  type OverlayScaleControls,
} from "@/lib/remotion/overlay-controls";
import {
  WEB_RENDER_DELAY_RENDER_TIMEOUT_MS,
  getFriendlyWebRenderErrorMessage,
} from "@/lib/remotion/rendering";
import {StitchVideoWeb} from "@/lib/remotion/stitch-video-web";

const PROGRESS_LABEL_MODE_OPTIONS: Array<{value: ProgressLabelMode; label: string}> = [
  {value: "auto", label: "自动"},
  {value: "double", label: "双行"},
  {value: "single", label: "单行"},
];

const SUBTITLE_THEME_OPTIONS: Array<{value: SubtitleTheme; label: string}> = [
  {value: "box-white-on-black", label: "黑底白字"},
  {value: "box-black-on-white", label: "白底黑字"},
  {value: "text-white", label: "白字透明"},
  {value: "text-black", label: "黑字透明"},
];

const clamp = (value: number, min: number, max: number): number =>
  Math.max(min, Math.min(max, value));

type ExtractedFrame = {
  timeSec: number;
  dataUrl: string;
};

type MockExportState = {
  status: "idle" | "running" | "succeeded" | "failed";
  message: string;
  outputUrl: string | null;
  outputName: string | null;
  frames: ExtractedFrame[];
};

type EditableMockContent = {
  chapterTitle: string;
  subtitleText: string;
  extraTopicTitlesText: string;
  durationSec: number;
  previewTimeSec: number;
  inspectTimesText: string;
};

async function extractFrameFromVideo(videoUrl: string, timeSec: number): Promise<string> {
  const video = document.createElement("video");
  video.src = videoUrl;
  video.preload = "auto";
  video.muted = true;
  video.playsInline = true;
  video.crossOrigin = "anonymous";

  await new Promise<void>((resolve, reject) => {
    const onLoadedMetadata = () => resolve();
    const onError = () => reject(new Error("无法读取 mock 导出视频。"));
    video.addEventListener("loadedmetadata", onLoadedMetadata, {once: true});
    video.addEventListener("error", onError, {once: true});
  });

  await new Promise<void>((resolve, reject) => {
    const maxTime =
      Number.isFinite(video.duration) && video.duration > 0
        ? Math.max(0, video.duration - 0.05)
        : timeSec;
    const targetTime = clamp(timeSec, 0, maxTime);
    const onSeeked = () => resolve();
    const onError = () => reject(new Error("mock 导出视频定帧失败。"));
    video.addEventListener("seeked", onSeeked, {once: true});
    video.addEventListener("error", onError, {once: true});
    video.currentTime = targetTime;
  });

  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const context = canvas.getContext("2d");
  if (!context) {
    throw new Error("无法创建画布上下文。");
  }
  context.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/png");
}

const buildInitialOverlayControls = (scenarioId: string): OverlayScaleControls => {
  const scenario = getMockScenarioPreset(scenarioId);
  return (
    scenario.defaultOverlayControls ?? {
      ...DEFAULT_OVERLAY_CONTROLS,
      subtitleScale: 1.12,
      progressScale: 1.18,
      chapterScale: 1,
      progressLabelMode: "auto",
    }
  );
};

const buildInitialSubtitleTheme = (scenarioId: string): SubtitleTheme =>
  getMockScenarioPreset(scenarioId).defaultSubtitleTheme ?? "box-white-on-black";

const parseLineList = (value: string): string[] =>
  value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);

const buildInitialEditableContent = (scenarioId: string): EditableMockContent => {
  const scenario = getMockScenarioPreset(scenarioId);
  const primaryTopic = scenario.topics[0]?.title ?? "章节标题示例";
  const otherTopics = scenario.topics.slice(1).map((topic) => topic.title).join("\n");
  const subtitleText = scenario.captions[0]?.text ?? "这是用来测试字幕布局的示例文本。";
  return {
    chapterTitle: primaryTopic,
    subtitleText,
    extraTopicTitlesText: otherTopics,
    durationSec: scenario.durationSec,
    previewTimeSec: scenario.previewTimeSec,
    inspectTimesText: scenario.inspectTimesSec.join(", "),
  };
};

const buildScenarioFromEditable = (
  scenario: MockScenarioPreset,
  editable: EditableMockContent
): MockScenarioPreset => {
  const durationSec = clamp(Number(editable.durationSec) || scenario.durationSec, 3, 60);
  const topicTitles = [editable.chapterTitle.trim(), ...parseLineList(editable.extraTopicTitlesText)].filter(Boolean);
  const safeTopicTitles = topicTitles.length > 0 ? topicTitles : [scenario.topics[0]?.title ?? "章节标题示例"];
  const topicDuration = durationSec / safeTopicTitles.length;
  const topics = safeTopicTitles.map((title, index) => ({
    title,
    start: Number((index * topicDuration).toFixed(3)),
    end: Number(((index + 1) * topicDuration).toFixed(3)),
  }));
  const previewTimeSec = clamp(Number(editable.previewTimeSec) || scenario.previewTimeSec, 0, durationSec - 0.1);
  const parsedInspectTimes = String(editable.inspectTimesText || "")
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item))
    .map((item) => clamp(item, 0, durationSec));
  const inspectTimesSec = parsedInspectTimes.length > 0 ? parsedInspectTimes : [...scenario.inspectTimesSec];
  const captionStart = Math.min(0.6, Math.max(0, durationSec * 0.08));
  const captionEnd = Math.max(captionStart + 0.8, durationSec * 0.86);
  const segments = safeTopicTitles.map((_, index) => ({
    start: Number((index * topicDuration).toFixed(3)),
    end: Number(((index + 1) * topicDuration).toFixed(3)),
  }));

  return {
    ...scenario,
    durationSec,
    previewTimeSec,
    inspectTimesSec,
    captions: [
      {
        index: 1,
        start: Number(captionStart.toFixed(3)),
        end: Number(clamp(captionEnd, captionStart + 0.2, durationSec).toFixed(3)),
        text: editable.subtitleText.trim() || "这是用来测试字幕布局的示例文本。",
      },
    ],
    topics,
    segments,
  };
};

function DevExportPreviewPageInner() {
  const searchParams = useSearchParams();
  const initialScenarioId = searchParams.get("scenario") ?? DEFAULT_MOCK_SCENARIO_ID;
  const initialResolutionId = searchParams.get("resolution") ?? DEFAULT_MOCK_RESOLUTION_ID;
  const [selectedScenarioId, setSelectedScenarioId] = useState(initialScenarioId);
  const [selectedResolutionId, setSelectedResolutionId] = useState(initialResolutionId);
  const [subtitleTheme, setSubtitleTheme] = useState<SubtitleTheme>(
    buildInitialSubtitleTheme(initialScenarioId)
  );
  const [overlayControls, setOverlayControls] = useState<OverlayScaleControls>(
    buildInitialOverlayControls(initialScenarioId)
  );
  const [editableContent, setEditableContent] = useState<EditableMockContent>(
    buildInitialEditableContent(initialScenarioId)
  );
  const [mockExport, setMockExport] = useState<MockExportState>({
    status: "idle",
    message: "尚未执行 mock 导出",
    outputUrl: null,
    outputName: null,
    frames: [],
  });
  const autoRun = searchParams.get("autorun") === "1";

  const selectedScenario = useMemo(
    () => getMockScenarioPreset(selectedScenarioId),
    [selectedScenarioId]
  );
  const selectedResolution = useMemo(
    () => getMockResolutionPreset(selectedResolutionId),
    [selectedResolutionId]
  );
  const controls = useMemo(() => overlayControls, [overlayControls]);
  const runtimeScenario = useMemo(
    () => buildScenarioFromEditable(selectedScenario, editableContent),
    [editableContent, selectedScenario]
  );
  const activeConfig = useMemo(
    () =>
      buildMockRenderConfig({
        resolution: selectedResolution,
        scenario: runtimeScenario,
        subtitleTheme,
        overlayControls: controls,
      }),
    [controls, runtimeScenario, selectedResolution, subtitleTheme]
  );
  const compareConfigs = useMemo(
    () =>
      DEFAULT_COMPARE_RESOLUTION_IDS.map((resolutionId) => {
        const resolution = getMockResolutionPreset(resolutionId);
        return {
          resolution,
          config: buildMockRenderConfig({
            resolution,
            scenario: runtimeScenario,
            subtitleTheme,
            overlayControls: controls,
          }),
        };
      }),
    [controls, runtimeScenario, subtitleTheme]
  );

  const previewTimeSec = runtimeScenario.previewTimeSec;
  const inspectTimesSec = runtimeScenario.inspectTimesSec;
  const subtitlePercent = Math.round((overlayControls.subtitleScale ?? 1) * 100);
  const subtitleYPercent = Math.round(
    overlayControls.subtitleYPercent ?? DEFAULT_OVERLAY_CONTROLS.subtitleYPercent
  );
  const progressPercent = Math.round((overlayControls.progressScale ?? 1) * 100);
  const progressYPercent = Math.round(
    overlayControls.progressYPercent ?? DEFAULT_OVERLAY_CONTROLS.progressYPercent
  );
  const chapterPercent = Math.round((overlayControls.chapterScale ?? 1) * 100);

  useEffect(() => {
    return () => {
      if (mockExport.outputUrl) {
        URL.revokeObjectURL(mockExport.outputUrl);
      }
    };
  }, [mockExport.outputUrl]);

  const applyScenarioPreset = (scenarioId: string) => {
    const scenario = getMockScenarioPreset(scenarioId);
    setSelectedScenarioId(scenario.id);
    setSubtitleTheme(scenario.defaultSubtitleTheme ?? "box-white-on-black");
    setOverlayControls(
      scenario.defaultOverlayControls ?? {
        ...DEFAULT_OVERLAY_CONTROLS,
        subtitleScale: 1.12,
        progressScale: 1.18,
        chapterScale: 1,
        progressLabelMode: "auto",
      }
    );
    setEditableContent(buildInitialEditableContent(scenario.id));
    setMockExport((previous) => {
      if (previous.outputUrl) {
        URL.revokeObjectURL(previous.outputUrl);
      }
      return {
        status: "idle",
        message: "场景已切换，请重新执行 mock 导出",
        outputUrl: null,
        outputName: null,
        frames: [],
      };
    });
  };

  const runMockExport = async () => {
    setMockExport((previous) => {
      if (previous.outputUrl) {
        URL.revokeObjectURL(previous.outputUrl);
      }
      return {
        status: "running",
        message: "正在执行浏览器 mock 导出...",
        outputUrl: null,
        outputName: null,
        frames: [],
      };
    });

    try {
      setMockExport((previous) => ({
        ...previous,
        message: "正在加载浏览器导出器...",
      }));

      setMockExport((previous) => ({
        ...previous,
        message: "正在检测浏览器编码能力...",
      }));

      const rendered = await (async () => {
        const inputProps = {
          ...activeConfig.input_props,
          src: "",
        };
        const composition = {
          ...activeConfig.composition,
          component: StitchVideoWeb,
          defaultProps: inputProps,
        };

        if (!window.isSecureContext) {
          throw new Error("当前页面不是安全上下文，浏览器无法启用 mock 导出。");
        }

        const {renderMediaOnWeb, getEncodableAudioCodecs} = await import("@remotion/web-renderer");
        const mp4AudioCodecs = await getEncodableAudioCodecs("mp4");
        const webmAudioCodecs = await getEncodableAudioCodecs("webm");
        const hasMp4Audio = mp4AudioCodecs.length > 0;
        const hasWebmAudio = webmAudioCodecs.length > 0;

        type WebRendererVideoCodec = "h264" | "vp8" | "vp9" | "h265" | "av1";
        let container: "mp4" | "webm" = "mp4";
        let videoCodec: WebRendererVideoCodec = "h264";
        let muted = false;

        if (hasMp4Audio) {
          container = "mp4";
          videoCodec = "h264";
        } else if (hasWebmAudio) {
          container = "webm";
          videoCodec = "vp8";
        } else {
          muted = true;
        }

        setMockExport((previous) => ({
          ...previous,
          message: muted ? "开始渲染静音 mock 导出..." : "开始渲染 mock 导出...",
        }));

        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const renderOptions: Parameters<typeof renderMediaOnWeb>[0] = {
          composition: composition as any,
          inputProps,
          container,
          videoCodec,
          videoBitrate: "high",
          delayRenderTimeoutInMilliseconds: WEB_RENDER_DELAY_RENDER_TIMEOUT_MS,
          ...(muted ? {muted: true} : {}),
          onProgress: (progress) => {
            const totalFrames = Math.max(1, Number(activeConfig.composition.durationInFrames) || 1);
            const doneFrames =
              typeof progress.encodedFrames === "number" && Number.isFinite(progress.encodedFrames)
                ? progress.encodedFrames
                : progress.renderedFrames;
            setMockExport((previous) => ({
              ...previous,
              message: `正在渲染 mock 导出... ${doneFrames}/${totalFrames} 帧`,
            }));
          },
        };

        let result: Awaited<ReturnType<typeof renderMediaOnWeb>>;
        try {
          result = await renderMediaOnWeb(renderOptions);
        } catch (renderErr) {
          const message = renderErr instanceof Error ? renderErr.message : String(renderErr);
          if (!muted && message.includes("No audio codec can be encoded")) {
            setMockExport((previous) => ({
              ...previous,
              message: "音频编码不可用，切换为静音 mock 导出...",
            }));
            result = await renderMediaOnWeb({...renderOptions, muted: true});
            muted = true;
          } else {
            throw renderErr;
          }
        }

        return {
          blob: await result.getBlob(),
          container,
          muted,
        };
      })();

      setMockExport((previous) => ({
        ...previous,
        message: "导出完成，正在抽取检查帧...",
      }));
      const outputUrl = URL.createObjectURL(rendered.blob);
      const frames = await Promise.all(
        inspectTimesSec.map(async (timeSec) => ({
          timeSec,
          dataUrl: await extractFrameFromVideo(outputUrl, timeSec),
        }))
      );
      setMockExport({
        status: "succeeded",
        message: rendered.muted
          ? "mock 导出成功（当前环境未编码音频，结果为静音文件）"
          : "mock 导出成功",
        outputUrl,
        outputName: activeConfig.output_name.replace(/\.mp4$/, `.${rendered.container}`),
        frames,
      });
    } catch (error) {
      setMockExport({
        status: "failed",
        message: getFriendlyWebRenderErrorMessage(error),
        outputUrl: null,
        outputName: null,
        frames: [],
      });
    }
  };

  useEffect(() => {
    if (!autoRun || mockExport.status !== "idle") {
      return;
    }
    void runMockExport();
  }, [autoRun, mockExport.status]);

  return (
    <main className="mx-auto max-w-[1320px] px-6 py-8" data-mock-export-status={mockExport.status}>
      <div className="mx-auto mb-6 max-w-[1200px]">
        <h1 className="text-xl font-semibold text-slate-900">Overlay Mock Preview Lab</h1>
        <p className="mt-2 text-sm text-slate-500">
          用纯白底和固定场景快速检查章节块、字幕和进度条在不同画幅和分辨率下的表现。
        </p>
      </div>

      <div className="mx-auto grid max-w-[1200px] gap-3 xl:grid-cols-[minmax(0,640px)_360px] xl:items-stretch">
        <Card className="border-slate-200/80 xl:h-[min(72vh,800px)]">
          <CardContent className="flex h-full min-h-0 flex-col gap-3 p-3">
            <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
              <div>
                <div className="text-sm font-medium text-slate-900">{selectedScenario.label}</div>
                <div className="text-xs text-slate-500">{selectedScenario.description}</div>
              </div>
              <div className="rounded-full bg-white px-3 py-1 text-xs font-mono text-slate-500">
                {selectedResolution.width}x{selectedResolution.height}
              </div>
            </div>
            <div className="flex-1 min-h-0">
              <ExportFramePreview
                config={activeConfig}
                sourceFile={null}
                emptyStateMode="blank"
                subtitleTheme={subtitleTheme}
                previewTimeSec={previewTimeSec}
                overlayControls={controls}
              />
            </div>
          </CardContent>
        </Card>

        <Card className="xl:h-[min(72vh,800px)]">
          <CardContent className="flex h-full min-h-0 flex-col p-3">
            <div className="flex-1 space-y-4 overflow-y-auto pr-1">
              <div className="flex items-center justify-between gap-3">
                <label className="text-sm font-medium">Mock 场景</label>
                <Select value={selectedScenarioId} onValueChange={applyScenarioPreset}>
                  <SelectTrigger className="w-[188px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MOCK_SCENARIO_PRESETS.map((scenario) => (
                      <SelectItem key={scenario.id} value={scenario.id}>
                        {scenario.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between gap-3">
                <label className="text-sm font-medium">预览分辨率</label>
                <Select value={selectedResolutionId} onValueChange={setSelectedResolutionId}>
                  <SelectTrigger className="w-[188px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MOCK_RESOLUTION_PRESETS.map((resolution) => (
                      <SelectItem key={resolution.id} value={resolution.id}>
                        {resolution.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between gap-3">
                <label className="text-sm font-medium">标题行数</label>
                <Select
                  value={(overlayControls.progressLabelMode ?? "auto") as ProgressLabelMode}
                  onValueChange={(value) =>
                    setOverlayControls((previous) => ({
                      ...previous,
                      progressLabelMode: value as ProgressLabelMode,
                    }))
                  }
                >
                  <SelectTrigger className="w-[188px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PROGRESS_LABEL_MODE_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center justify-between gap-3">
                <label className="text-sm font-medium">字幕样式</label>
                <Select value={subtitleTheme} onValueChange={(value) => setSubtitleTheme(value as SubtitleTheme)}>
                  <SelectTrigger className="w-[188px]">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SUBTITLE_THEME_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-3 rounded-xl border border-slate-200/80 bg-slate-50/80 p-3">
                <div className="text-sm font-medium text-slate-900">显示内容</div>
                <label className="flex items-center justify-between gap-3 text-sm text-slate-700">
                  <span>显示字幕</span>
                  <Checkbox
                    checked={overlayControls.showSubtitles ?? DEFAULT_OVERLAY_CONTROLS.showSubtitles}
                    onCheckedChange={(checked) =>
                      setOverlayControls((previous) => ({
                        ...previous,
                        showSubtitles: checked !== false,
                      }))
                    }
                  />
                </label>
                <label className="flex items-center justify-between gap-3 text-sm text-slate-700">
                  <span>显示进度条</span>
                  <Checkbox
                    checked={overlayControls.showProgress ?? DEFAULT_OVERLAY_CONTROLS.showProgress}
                    onCheckedChange={(checked) =>
                      setOverlayControls((previous) => ({
                        ...previous,
                        showProgress: checked !== false,
                      }))
                    }
                  />
                </label>
                <label className="flex items-center justify-between gap-3 text-sm text-slate-700">
                  <span>显示章节</span>
                  <Checkbox
                    checked={overlayControls.showChapter ?? DEFAULT_OVERLAY_CONTROLS.showChapter}
                    onCheckedChange={(checked) =>
                      setOverlayControls((previous) => ({
                        ...previous,
                        showChapter: checked !== false,
                      }))
                    }
                  />
                </label>
              </div>

              <div className="space-y-2 border-t border-slate-200 pt-3">
                <div className="text-sm font-medium text-slate-900">章节标题</div>
                <textarea
                  value={editableContent.chapterTitle}
                  onChange={(event) =>
                    setEditableContent((previous) => ({
                      ...previous,
                      chapterTitle: event.currentTarget.value,
                    }))
                  }
                  rows={4}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-400"
                  placeholder={"支持直接输入长标题，也支持手动换行。\n例如：相同字数的标题\n中间强制换一行"}
                />
                <p className="text-[11px] text-slate-500">
                  这里支持手动换行，适合测试相同文本在不同断行策略下的表现。
                </p>
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium text-slate-900">字幕文本</div>
                <textarea
                  value={editableContent.subtitleText}
                  onChange={(event) =>
                    setEditableContent((previous) => ({
                      ...previous,
                      subtitleText: event.currentTarget.value,
                    }))
                  }
                  rows={4}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-400"
                  placeholder="输入你要压测的字幕文案。支持极限长句，也支持手动换行。"
                />
              </div>

              <div className="space-y-2">
                <div className="text-sm font-medium text-slate-900">其他进度条标题</div>
                <textarea
                  value={editableContent.extraTopicTitlesText}
                  onChange={(event) =>
                    setEditableContent((previous) => ({
                      ...previous,
                      extraTopicTitlesText: event.currentTarget.value,
                    }))
                  }
                  rows={4}
                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-400"
                  placeholder={"每行一个额外章节标题。\n例如：\n为什么开头会拖沓\n怎样保留真实感受\n最后怎么落地执行"}
                />
                <p className="text-[11px] text-slate-500">
                  第一条章节标题使用上面的“章节标题”；这里每行会生成一个后续进度段，方便测试多段标题在不同分辨率下的表现。
                </p>
              </div>

              <div className="grid grid-cols-3 gap-2">
                <label className="space-y-1">
                  <span className="text-xs font-medium text-slate-700">总时长(s)</span>
                  <input
                    type="number"
                    min={3}
                    max={60}
                    step={0.1}
                    value={editableContent.durationSec}
                    onChange={(event) =>
                      setEditableContent((previous) => ({
                        ...previous,
                        durationSec: Number(event.currentTarget.value) || previous.durationSec,
                      }))
                    }
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-400"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-slate-700">预览时间(s)</span>
                  <input
                    type="number"
                    min={0}
                    max={60}
                    step={0.1}
                    value={editableContent.previewTimeSec}
                    onChange={(event) =>
                      setEditableContent((previous) => ({
                        ...previous,
                        previewTimeSec: Number(event.currentTarget.value) || 0,
                      }))
                    }
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-400"
                  />
                </label>
                <label className="space-y-1">
                  <span className="text-xs font-medium text-slate-700">导出定帧(s)</span>
                  <input
                    type="text"
                    value={editableContent.inspectTimesText}
                    onChange={(event) =>
                      setEditableContent((previous) => ({
                        ...previous,
                        inspectTimesText: event.currentTarget.value,
                      }))
                    }
                    className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition focus:border-slate-400"
                    placeholder="2, 4, 7"
                  />
                </label>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <label className="font-medium">字幕大小</label>
                  <span className="font-mono text-slate-500">{subtitlePercent}%</span>
                </div>
                <input
                  type="range"
                  min={OVERLAY_SCALE_LIMITS.subtitle.min}
                  max={OVERLAY_SCALE_LIMITS.subtitle.max}
                  step={OVERLAY_SCALE_LIMITS.subtitle.step}
                  value={overlayControls.subtitleScale ?? OVERLAY_SCALE_LIMITS.subtitle.defaultValue}
                  onChange={(event) => {
                    const nextSubtitleScale = clamp(
                      Number(event.currentTarget.value),
                      OVERLAY_SCALE_LIMITS.subtitle.min,
                      OVERLAY_SCALE_LIMITS.subtitle.max
                    );
                    setOverlayControls((previous) => ({
                      ...previous,
                      subtitleScale: nextSubtitleScale,
                    }));
                  }}
                  className="h-2 w-full cursor-ew-resize accent-slate-900"
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <label className="font-medium">字幕位置</label>
                  <span className="font-mono text-slate-500">{subtitleYPercent}%</span>
                </div>
                <input
                  type="range"
                  min={OVERLAY_POSITION_LIMITS.subtitleY.min}
                  max={OVERLAY_POSITION_LIMITS.subtitleY.max}
                  step={OVERLAY_POSITION_LIMITS.subtitleY.step}
                  value={
                    overlayControls.subtitleYPercent ??
                    OVERLAY_POSITION_LIMITS.subtitleY.defaultValue
                  }
                  onChange={(event) => {
                    const nextSubtitleYPercent = clamp(
                      Number(event.currentTarget.value),
                      OVERLAY_POSITION_LIMITS.subtitleY.min,
                      OVERLAY_POSITION_LIMITS.subtitleY.max
                    );
                    setOverlayControls((previous) => ({
                      ...previous,
                      subtitleYPercent: nextSubtitleYPercent,
                    }));
                  }}
                  className="h-2 w-full cursor-ew-resize accent-slate-900"
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <label className="font-medium">进度条大小</label>
                  <span className="font-mono text-slate-500">{progressPercent}%</span>
                </div>
                <input
                  type="range"
                  min={OVERLAY_SCALE_LIMITS.progress.min}
                  max={OVERLAY_SCALE_LIMITS.progress.max}
                  step={OVERLAY_SCALE_LIMITS.progress.step}
                  value={overlayControls.progressScale ?? OVERLAY_SCALE_LIMITS.progress.defaultValue}
                  onChange={(event) => {
                    const nextProgressScale = clamp(
                      Number(event.currentTarget.value),
                      OVERLAY_SCALE_LIMITS.progress.min,
                      OVERLAY_SCALE_LIMITS.progress.max
                    );
                    setOverlayControls((previous) => ({
                      ...previous,
                      progressScale: nextProgressScale,
                    }));
                  }}
                  className="h-2 w-full cursor-ew-resize accent-slate-900"
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <label className="font-medium">进度条位置</label>
                  <span className="font-mono text-slate-500">{progressYPercent}%</span>
                </div>
                <input
                  type="range"
                  min={OVERLAY_POSITION_LIMITS.progressY.min}
                  max={OVERLAY_POSITION_LIMITS.progressY.max}
                  step={OVERLAY_POSITION_LIMITS.progressY.step}
                  value={
                    overlayControls.progressYPercent ??
                    OVERLAY_POSITION_LIMITS.progressY.defaultValue
                  }
                  onChange={(event) => {
                    const nextProgressYPercent = clamp(
                      Number(event.currentTarget.value),
                      OVERLAY_POSITION_LIMITS.progressY.min,
                      OVERLAY_POSITION_LIMITS.progressY.max
                    );
                    setOverlayControls((previous) => ({
                      ...previous,
                      progressYPercent: nextProgressYPercent,
                    }));
                  }}
                  className="h-2 w-full cursor-ew-resize accent-slate-900"
                />
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <label className="font-medium">章节块大小</label>
                  <span className="font-mono text-slate-500">{chapterPercent}%</span>
                </div>
                <input
                  type="range"
                  min={OVERLAY_SCALE_LIMITS.chapter.min}
                  max={OVERLAY_SCALE_LIMITS.chapter.max}
                  step={OVERLAY_SCALE_LIMITS.chapter.step}
                  value={overlayControls.chapterScale ?? OVERLAY_SCALE_LIMITS.chapter.defaultValue}
                  onChange={(event) => {
                    const nextChapterScale = clamp(
                      Number(event.currentTarget.value),
                      OVERLAY_SCALE_LIMITS.chapter.min,
                      OVERLAY_SCALE_LIMITS.chapter.max
                    );
                    setOverlayControls((previous) => ({
                      ...previous,
                      chapterScale: nextChapterScale,
                    }));
                  }}
                  className="h-2 w-full cursor-ew-resize accent-slate-900"
                />
              </div>
            </div>

            <div className="mt-3 border-t border-slate-200 bg-white pt-3">
              <div className="grid grid-cols-2 gap-2">
                <Button variant="outline" onClick={() => applyScenarioPreset(selectedScenarioId)}>
                  恢复场景默认值
                </Button>
                <Button size="lg" onClick={() => void runMockExport()}>
                  mock 导出视频
                </Button>
              </div>
              <p id="mock-export-message" className="mt-2 text-xs text-slate-500">
                {mockExport.message}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mx-auto mt-6 max-w-[1200px] space-y-3">
        <div className="flex items-end justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">常用分辨率并排对比</h2>
            <p className="text-xs text-slate-500">同一套场景和参数，同时看不同画幅下的章节块表现。</p>
          </div>
          <div className="text-xs text-slate-400">预览时间 {previewTimeSec.toFixed(1)}s</div>
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {compareConfigs.map(({resolution, config}) => (
            <Card key={resolution.id}>
              <CardContent className="space-y-3 p-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium text-slate-900">{resolution.label}</div>
                  <div className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-mono text-slate-500">
                    {resolution.width}x{resolution.height}
                  </div>
                </div>
                <div className="h-[260px]">
                  <ExportFramePreview
                    config={config}
                    sourceFile={null}
                    emptyStateMode="blank"
                    subtitleTheme={subtitleTheme}
                    previewTimeSec={previewTimeSec}
                    overlayControls={controls}
                  />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <div className="mx-auto mt-6 grid max-w-[1200px] gap-3 lg:grid-cols-2">
        <Card>
          <CardContent className="space-y-3 p-3">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold">mock 导出结果</h2>
              <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">
                {mockExport.status}
              </span>
            </div>
            {mockExport.outputUrl ? (
              <video
                src={mockExport.outputUrl}
                controls
                className="w-full rounded-xl border border-slate-200 bg-black"
              />
            ) : (
              <div className="flex aspect-[9/16] items-center justify-center rounded-xl border border-dashed border-slate-200 text-sm text-slate-400">
                导出完成后会显示结果视频
              </div>
            )}
            {mockExport.outputName ? (
              <p className="text-xs text-slate-500">{mockExport.outputName}</p>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 p-3">
            <h2 className="text-sm font-semibold">导出后定帧检查</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {inspectTimesSec.map((timeSec, index) => {
                const frame = mockExport.frames.find((item) => item.timeSec === timeSec) ?? null;
                return (
                  <div key={timeSec} className="space-y-2">
                    <div className="text-xs text-slate-500">导出视频 {timeSec.toFixed(1)}s</div>
                    {frame ? (
                      <img
                        src={frame.dataUrl}
                        alt={`mock export frame ${index + 1}`}
                        className="w-full rounded-xl border border-slate-200"
                      />
                    ) : (
                      <div className="flex aspect-[9/16] items-center justify-center rounded-xl border border-dashed border-slate-200 text-xs text-slate-400">
                        等待导出定帧
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}

export default function DevExportPreviewPage() {
  return (
    <Suspense fallback={null}>
      <DevExportPreviewPageInner />
    </Suspense>
  );
}
