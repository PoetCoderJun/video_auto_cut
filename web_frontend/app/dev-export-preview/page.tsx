"use client";

import {Suspense, useEffect, useMemo, useState} from "react";
import {useSearchParams} from "next/navigation";

import ExportFramePreview from "@/components/export-frame-preview";
import {Button} from "@/components/ui/button";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {
  ProgressLabelMode,
  SubtitleTheme,
  WebRenderConfig,
} from "@/lib/api";
import {
  OVERLAY_SCALE_LIMITS,
  type OverlayScaleControls,
} from "@/lib/remotion/overlay-controls";
import {StitchVideoWeb} from "@/lib/remotion/stitch-video-web";

const SOURCE_URL = "/__codex/export_preview_source.mp4";
const INSPECT_TIMES_SEC = [4, 9] as const;

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

const MOCK_RENDER_CONFIG: WebRenderConfig = {
  output_name: "preview.mp4",
  composition: {
    id: "StitchVideoWeb",
    fps: 27,
    width: 544,
    height: 960,
    durationInFrames: 27 * 8,
  },
  input_props: {
    src: "",
    fps: 27,
    width: 544,
    height: 960,
    captions: [
      {
        index: 1,
        start: 1.2,
        end: 6.8,
        text: "那我可以跟他聊聊。如果他什么都没有做过，他只是关心收益的话",
      },
    ],
    topics: [
      {title: "长句换行压测", start: 0, end: 8},
    ],
    segments: [{start: 41, end: 49}],
  },
};

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

function DevExportPreviewPageInner() {
  const searchParams = useSearchParams();
  const [subtitleTheme, setSubtitleTheme] = useState<SubtitleTheme>("box-white-on-black");
  const [overlayControls, setOverlayControls] = useState<OverlayScaleControls>({
    subtitleScale: 1.12,
    progressScale: 1.18,
    chapterScale: 1,
    progressLabelMode: "auto",
  });
  const [mockExport, setMockExport] = useState<MockExportState>({
    status: "idle",
    message: "尚未执行 mock 导出",
    outputUrl: null,
    outputName: null,
    frames: [],
  });

  const previewTimeSec = 4;
  const subtitlePercent = Math.round((overlayControls.subtitleScale ?? 1) * 100);
  const progressPercent = Math.round((overlayControls.progressScale ?? 1) * 100);
  const chapterPercent = Math.round((overlayControls.chapterScale ?? 1) * 100);
  const controls = useMemo(() => overlayControls, [overlayControls]);
  const autoRun = searchParams.get("autorun") === "1";

  useEffect(() => {
    return () => {
      if (mockExport.outputUrl) {
        URL.revokeObjectURL(mockExport.outputUrl);
      }
    };
  }, [mockExport.outputUrl]);

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
      const config = {
        ...MOCK_RENDER_CONFIG,
        input_props: {
          ...MOCK_RENDER_CONFIG.input_props,
          subtitleTheme,
          subtitleScale: overlayControls.subtitleScale,
          progressScale: overlayControls.progressScale,
          chapterScale: overlayControls.chapterScale,
          progressLabelMode: overlayControls.progressLabelMode,
        },
      };

      setMockExport((previous) => ({
        ...previous,
        message: "正在检测浏览器编码能力...",
      }));
      const rendered = await (async () => {
        const inputProps = {
          ...config.input_props,
          src: SOURCE_URL,
        };
        const composition = {
          ...config.composition,
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
          ...(muted ? {muted: true} : {}),
          onProgress: (progress) => {
            const totalFrames = Math.max(1, Number(config.composition.durationInFrames) || 1);
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
        INSPECT_TIMES_SEC.map(async (timeSec) => ({
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
        outputName: `preview.${rendered.container}`,
        frames,
      });
    } catch (error) {
      setMockExport({
        status: "failed",
        message: error instanceof Error ? error.message : "mock 导出失败",
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
    <main className="mx-auto max-w-7xl px-6 py-8" data-mock-export-status={mockExport.status}>
      <div className="mx-auto grid max-w-[980px] gap-3 xl:grid-cols-[minmax(0,560px)_320px] xl:items-stretch">
        <Card className="border-slate-200/80 xl:h-[min(70vh,760px)]">
          <CardContent className="flex h-full min-h-0 flex-col justify-center gap-3 p-3">
            <ExportFramePreview
              config={MOCK_RENDER_CONFIG}
              sourceFile={null}
              sourceUrlOverride={SOURCE_URL}
              subtitleTheme={subtitleTheme}
              previewTimeSec={previewTimeSec}
              overlayControls={controls}
            />
          </CardContent>
        </Card>

        <Card className="xl:h-[min(70vh,760px)]">
          <CardContent className="flex h-full flex-col gap-4 p-3">
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
                <SelectTrigger className="w-[152px]">
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
              <Select
                value={subtitleTheme}
                onValueChange={(value) => setSubtitleTheme(value as SubtitleTheme)}
              >
                <SelectTrigger className="w-[152px]">
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

            <div className="mt-auto flex flex-col gap-2 border-t border-slate-200 pt-3">
              <Button size="lg" className="w-full" onClick={() => void runMockExport()}>
                mock 导出视频
              </Button>
              <p id="mock-export-message" className="text-xs text-slate-500">
                {mockExport.message}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mx-auto mt-6 grid max-w-[980px] gap-3 lg:grid-cols-2">
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
              {INSPECT_TIMES_SEC.map((timeSec, index) => {
                const frame = mockExport.frames.find((item) => item.timeSec === timeSec) ?? null;
                return (
                  <div key={timeSec} className="space-y-2">
                    <div className="text-xs text-slate-500">导出视频 {timeSec.toFixed(0)}s</div>
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
