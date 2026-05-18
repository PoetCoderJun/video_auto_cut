"use client";

import React, {useCallback, useEffect, useRef, useState} from "react";

import ExportFramePreview from "@/components/export-frame-preview";
import {Alert, AlertDescription, AlertTitle} from "@/components/ui/alert";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {Button} from "@/components/ui/button";
import {Card, CardContent} from "@/components/ui/card";
import {Checkbox} from "@/components/ui/checkbox";
import {Progress} from "@/components/ui/progress";
import {Separator} from "@/components/ui/separator";
import {Slider} from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {RenderMeta, WebRenderConfig} from "@/lib/api";
import type {SubtitleTheme} from "@/lib/remotion/stitch-video-web";
import {
  DEFAULT_OVERLAY_CONTROLS,
  OVERLAY_POSITION_LIMITS,
  OVERLAY_SCALE_LIMITS,
  type OverlayScaleControls,
  type ProgressLabelMode,
} from "@/lib/remotion/overlay-controls";
import {cn} from "@/lib/utils";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileText,
  FileVideo,
  Info,
  Loader2,
  RotateCcw,
} from "lucide-react";

import type {RenderSourceCompatibilityState} from "./use-render-source-compatibility";
import {triggerFileDownload} from "./workspace-utils";

function OverlayToggleTile({
  label,
  checked,
  disabled,
  onCheckedChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-center justify-between rounded-lg border border-border px-3 py-2.5 text-sm transition hover:border-border hover:bg-muted/50",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <span className="font-medium text-foreground">{label}</span>
      <Checkbox
        checked={checked}
        disabled={disabled}
        onCheckedChange={(value) => onCheckedChange(Boolean(value))}
      />
    </label>
  );
}

function DebouncedSlider({
  label,
  valueText,
  min,
  max,
  step,
  value,
  disabled,
  onChange,
}: {
  label: string;
  valueText: string;
  min: number;
  max: number;
  step: number;
  value: number;
  disabled?: boolean;
  onChange: (value: number) => void;
}) {
  const [localValue, setLocalValue] = useState(value);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  const handleChange = useCallback(
    (values: number[]) => {
      const next = values[0];
      setLocalValue(next);
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      timeoutRef.current = setTimeout(() => {
        onChange(next);
      }, 120);
    },
    [onChange],
  );

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-[11px] font-medium text-muted-foreground">
        <span>{label}</span>
        <span>{valueText}</span>
      </div>
      <Slider
        min={min}
        max={max}
        step={step}
        value={[localValue]}
        disabled={disabled}
        onValueChange={handleChange}
      />
    </div>
  );
}

function SourceStatusBanner({
  hasRenderSource,
  compatibility,
}: {
  hasRenderSource: boolean;
  compatibility: RenderSourceCompatibilityState;
}) {
  if (!hasRenderSource) {
    return (
      <Alert variant="warning" className="py-3">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle className="text-sm">需要重新上传视频</AlertTitle>
        <AlertDescription className="text-xs">
          本地渲染所需源视频缓存已丢失，请重新上传视频生成新的导出。
        </AlertDescription>
      </Alert>
    );
  }

  if (compatibility.status === "checking") {
    return (
      <div className="flex items-center gap-2 rounded-lg border bg-muted/50 px-3 py-2.5 text-sm text-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        <span>{compatibility.message}</span>
      </div>
    );
  }

  if (compatibility.status === "incompatible") {
    return (
      <Alert variant="warning" className="py-3">
        <Info className="h-4 w-4" />
        <AlertTitle className="text-sm">当前源视频不能直接浏览器导出</AlertTitle>
        <AlertDescription className="text-xs">
          {compatibility.message}
        </AlertDescription>
      </Alert>
    );
  }

  if (compatibility.status === "blocked") {
    return (
      <Alert variant="destructive" className="py-3">
        <AlertTriangle className="h-4 w-4" />
        <AlertTitle className="text-sm">导出被阻止</AlertTitle>
        <AlertDescription className="text-xs">
          {compatibility.message}
        </AlertDescription>
      </Alert>
    );
  }

  if (compatibility.status === "unknown") {
    return (
      <div className="flex items-center gap-2 rounded-lg border bg-muted/50 px-3 py-2.5 text-sm text-foreground">
        <Info className="h-4 w-4" />
        <span>{compatibility.message}</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2.5 text-sm text-emerald-800">
      <CheckCircle2 className="h-4 w-4 shrink-0" />
      <span>源视频检测通过，可直接导出</span>
    </div>
  );
}

function MetadataSummary({
  renderConfig,
  sourceMeta,
  estimatedFileSize,
}: {
  renderConfig: WebRenderConfig | null;
  sourceMeta: RenderMeta | null;
  estimatedFileSize: string | null;
}) {
  if (!renderConfig) return null;
  const width = sourceMeta?.width ?? renderConfig.composition.width;
  const height = sourceMeta?.height ?? renderConfig.composition.height;
  const fps = sourceMeta?.fps ?? renderConfig.composition.fps;
  const durationSec =
    sourceMeta?.duration_sec ??
    (renderConfig.composition.durationInFrames ?? 0) / renderConfig.composition.fps;
  const durationText =
    durationSec >= 60
      ? `${Math.floor(durationSec / 60)}分${Math.round(durationSec % 60)}秒`
      : `${Math.round(durationSec)}秒`;

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
      <span className="rounded-full bg-muted px-2 py-0.5 font-mono">
        {width}×{height}
      </span>
      <span className="rounded-full bg-muted px-2 py-0.5 font-mono">{fps}fps</span>
      <span className="rounded-full bg-muted px-2 py-0.5">约 {durationText}</span>
      {estimatedFileSize && (
        <span className="rounded-full bg-muted px-2 py-0.5">预估 {estimatedFileSize}</span>
      )}
    </div>
  );
}

function KeyframeStrip({
  config,
  sourceFile,
  previewTimeSec,
  onPreviewTimeChange,
}: {
  config: WebRenderConfig | null;
  sourceFile: File | null;
  previewTimeSec: number;
  onPreviewTimeChange: (timeSec: number) => void;
}) {
  const [thumbnails, setThumbnails] = useState<Array<{timeSec: number; url: string}>>([]);
  const objectUrlRef = useRef<string | null>(null);

  useEffect(() => {
    if (!config || !sourceFile) {
      setThumbnails([]);
      return;
    }
    const fps = config.composition.fps ?? 30;
    const duration = (config.composition.durationInFrames ?? 0) / fps;
    if (!duration || duration <= 0) {
      setThumbnails([]);
      return;
    }

    const videoUrl = URL.createObjectURL(sourceFile);
    objectUrlRef.current = videoUrl;

    const times = [0.1, 0.3, 0.5, 0.7, 0.9].map((p) =>
      Math.min(duration * p, duration - 0.1),
    );

    const video = document.createElement("video");
    video.src = videoUrl;
    video.muted = true;
    video.playsInline = true;
    video.crossOrigin = "anonymous";

    let cancelled = false;

    const capture = async () => {
      await new Promise<void>((resolve, reject) => {
        video.addEventListener("loadedmetadata", () => resolve(), {once: true});
        video.addEventListener("error", () => reject(), {once: true});
      });
      if (cancelled) return;

      const results: Array<{timeSec: number; url: string}> = [];
      const canvas = document.createElement("canvas");
      canvas.width = Math.min(video.videoWidth || 320, 320);
      canvas.height = Math.min(video.videoHeight || 180, 180);
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      for (const timeSec of times) {
        if (cancelled) break;
        try {
          video.currentTime = timeSec;
          await new Promise<void>((resolve) => {
            const onSeeked = () => {
              video.removeEventListener("seeked", onSeeked);
              resolve();
            };
            video.addEventListener("seeked", onSeeked);
          });
          if (cancelled) break;
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          results.push({timeSec, url: canvas.toDataURL("image/jpeg", 0.6)});
        } catch {
          // ignore single frame failure
        }
      }

      if (!cancelled) {
        setThumbnails(results);
      }
    };

    void capture();

    return () => {
      cancelled = true;
      video.src = "";
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [config, sourceFile]);

  if (thumbnails.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="text-xs font-medium text-muted-foreground">关键帧预览</div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {thumbnails.map((thumb) => {
          const isActive = Math.abs(previewTimeSec - thumb.timeSec) < 1;
          return (
            <button
              key={thumb.timeSec}
              type="button"
              onClick={() => onPreviewTimeChange(thumb.timeSec)}
              className={cn(
                "relative shrink-0 overflow-hidden rounded-lg border transition",
                isActive
                  ? "border-primary ring-1 ring-primary"
                  : "border-border hover:border-primary/50",
              )}
            >
              <img
                src={thumb.url}
                alt={`${thumb.timeSec.toFixed(1)}s`}
                className="h-16 w-28 object-cover"
              />
              <span className="absolute bottom-1 right-1 rounded bg-black/60 px-1 text-[10px] text-white">
                {thumb.timeSec.toFixed(1)}s
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function ExportStep({
  actions,
  state,
}: {
  actions: {
    clearRenderMessage: () => void;
    handleExportSubtitles: () => void;
    handleReopenEditor: () => void;
    handleStartRender: () => void;
    onBackHome?: () => void;
    prepareRenderPreview: () => Promise<WebRenderConfig | null>;
    resetOverlayControls: () => void;
    setOverlayControls: React.Dispatch<React.SetStateAction<OverlayScaleControls>>;
    setSubtitleTheme: React.Dispatch<React.SetStateAction<SubtitleTheme>>;
  };
  state: {
    busy: boolean;
    canReopenEditor: boolean;
    canStartRender: boolean;
    estimatedFileSize: string | null;
    hasRenderSource: boolean;
    overlayControls: OverlayScaleControls;
    previewTimeSec: number;
    reopenEditorBusy: boolean;
    progressLabelModeOptions: Array<{value: ProgressLabelMode; label: string}>;
    renderActionBusy: boolean;
    renderBusy: boolean;
    renderConfig: WebRenderConfig | null;
    renderConfigBusy: boolean;
    renderDisabledReason: string;
    renderDownloadUrl: string | null;
    renderFileName: string;
    renderNote: string;
    renderPreviewProfile: {
      width: number;
      height: number;
      fps: number;
      isReduced: boolean;
    } | null;
    renderSourceMeta: RenderMeta | null;
    renderPrimaryButtonLabel: string;
    renderProgress: number;
    renderSetupError: string;
    renderSourceCompatibility: RenderSourceCompatibilityState;
    renderSourceFile: File | null;
    selectedFile: File | null;
    subtitleDownloadUrl: string | null;
    subtitleExportBusy: boolean;
    subtitleFileName: string;
    subtitleTheme: SubtitleTheme;
    subtitleThemeOptions: Array<{value: SubtitleTheme; label: string}>;
  };
}) {
  const {
    busy,
    canReopenEditor,
    canStartRender,
    estimatedFileSize,
    hasRenderSource,
    overlayControls,
    previewTimeSec,
    reopenEditorBusy,
    progressLabelModeOptions,
    renderActionBusy,
    renderBusy,
    renderConfig,
    renderConfigBusy,
    renderDisabledReason,
    renderDownloadUrl,
    renderFileName,
    renderNote,
    renderPreviewProfile,
    renderPrimaryButtonLabel,
    renderProgress,
    renderSetupError,
    renderSourceCompatibility,
    renderSourceFile,
    renderSourceMeta,
    selectedFile,
    subtitleDownloadUrl,
    subtitleExportBusy,
    subtitleFileName,
    subtitleTheme,
    subtitleThemeOptions,
  } = state;

  const [previewTime, setPreviewTime] = useState(previewTimeSec);

  useEffect(() => {
    setPreviewTime(previewTimeSec);
  }, [previewTimeSec]);

  const handlePreviewTimeChange = useCallback(
    (timeSec: number) => {
      setPreviewTime(timeSec);
    },
    [],
  );

  const effectiveSourceFile = renderSourceFile ?? selectedFile;

  return (
    <div className="space-y-4">
      <div className="mx-auto grid max-w-[1400px] gap-4 lg:grid-cols-[minmax(0,1fr)] xl:grid-cols-[minmax(0,1.6fr)_minmax(420px,0.92fr)] xl:items-start 2xl:max-w-[1520px] 2xl:grid-cols-[minmax(0,1.72fr)_minmax(456px,0.94fr)]">
        <div className="flex h-full min-h-[360px] flex-col gap-3 sm:min-h-[440px] lg:min-h-[560px] xl:h-[min(70vh,760px)] xl:min-h-0">
          <ExportFramePreview
            config={renderConfig}
            sourceFile={renderSourceFile ?? selectedFile}
            subtitleTheme={subtitleTheme}
            previewTimeSec={previewTime}
            onPreviewTimeChange={handlePreviewTimeChange}
            overlayControls={overlayControls}
          />

          <KeyframeStrip
            config={renderConfig}
            sourceFile={effectiveSourceFile}
            previewTimeSec={previewTime}
            onPreviewTimeChange={handlePreviewTimeChange}
          />

          {renderConfigBusy && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在生成预览配置…
            </div>
          )}

          {renderSetupError && (
            <Alert variant="destructive" className="py-3">
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription className="text-sm">
                {renderSetupError}
              </AlertDescription>
            </Alert>
          )}
        </div>

        <Card className="overflow-hidden xl:self-start">
          <CardContent className="flex max-h-[min(80vh,800px)] flex-col p-0">
            <div className="border-b border-border bg-card px-4 py-4 sm:px-5">
              <div className="space-y-1">
                <div className="text-sm font-semibold text-foreground">准备导出</div>
                <p className="text-xs leading-5 text-muted-foreground">
                  默认使用推荐样式，确认预览无误后直接导出；需要微调字幕、章节或进度条时再展开高级设置。
                </p>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-4 sm:px-5">
              <div className="space-y-4">
                <SourceStatusBanner
                  hasRenderSource={hasRenderSource}
                  compatibility={renderSourceCompatibility}
                />

                {!hasRenderSource && actions.onBackHome && (
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full"
                    onClick={actions.onBackHome}
                    disabled={renderActionBusy || busy}
                  >
                    重新上传视频
                  </Button>
                )}

                <MetadataSummary
                  renderConfig={renderConfig}
                  sourceMeta={renderSourceMeta}
                  estimatedFileSize={estimatedFileSize}
                />

                <div className="rounded-2xl border border-border bg-muted/25 p-3 sm:p-4">
                  {renderBusy && (
                    <div className="mb-3 space-y-1.5">
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>{renderNote || "导出中…"}</span>
                        <span>{Math.round(renderProgress)}%</span>
                      </div>
                      <Progress value={renderProgress} className="h-2" />
                    </div>
                  )}

                  {!renderBusy && renderNote && (
                    <div className="mb-3 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
                      <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                      <span>{renderNote}</span>
                    </div>
                  )}

                  <div className="grid gap-2">
                    <Button
                      type="button"
                      size="lg"
                      className="h-12 w-full rounded-full text-base font-semibold"
                      onClick={actions.handleStartRender}
                      disabled={!canStartRender}
                    >
                      {renderBusy ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 正在导出
                        </>
                      ) : (
                        <>
                          <FileVideo className="mr-2 h-4 w-4" /> {renderPrimaryButtonLabel}
                        </>
                      )}
                    </Button>

                    {!canStartRender && !renderBusy && renderDisabledReason && (
                      <p className="text-center text-xs leading-5 text-amber-700">
                        {renderDisabledReason}
                      </p>
                    )}

                    <div
                      className={cn(
                        "grid grid-cols-1 gap-2",
                        canReopenEditor ? "sm:grid-cols-3" : "sm:grid-cols-2",
                      )}
                    >
                      <Button
                        type="button"
                        variant="secondary"
                        className="w-full"
                        onClick={actions.handleExportSubtitles}
                        disabled={busy || renderBusy || subtitleExportBusy}
                      >
                        {subtitleExportBusy ? (
                          <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 正在导出字幕
                          </>
                        ) : (
                          <>
                            <FileText className="mr-2 h-4 w-4" /> 下载字幕
                          </>
                        )}
                      </Button>

                      <Button
                        type="button"
                        variant="outline"
                        className="w-full"
                        onClick={() => {
                          actions.clearRenderMessage();
                          void actions.prepareRenderPreview();
                        }}
                        disabled={busy || renderActionBusy || renderConfigBusy}
                      >
                        {renderConfigBusy ? (
                          <>
                            <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 正在刷新预览
                          </>
                        ) : (
                          "刷新预览"
                        )}
                      </Button>

                      {canReopenEditor && (
                        <Button
                          type="button"
                          variant="outline"
                          className="w-full"
                          onClick={actions.handleReopenEditor}
                          disabled={busy || renderActionBusy || reopenEditorBusy}
                        >
                          {reopenEditorBusy ? (
                            <>
                              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 返回中
                            </>
                          ) : (
                            "返回修改"
                          )}
                        </Button>
                      )}
                    </div>

                    {subtitleDownloadUrl && (
                      <Button
                        type="button"
                        variant="ghost"
                        className="w-full text-muted-foreground"
                        onClick={() => triggerFileDownload(subtitleDownloadUrl, subtitleFileName)}
                      >
                        <Download className="mr-2 h-4 w-4" /> 下载上次字幕
                      </Button>
                    )}

                    {renderDownloadUrl && (
                      <Button
                        type="button"
                        variant="outline"
                        className="w-full border-primary/30 text-primary hover:bg-primary/5"
                        onClick={() => triggerFileDownload(renderDownloadUrl, renderFileName)}
                      >
                        <Download className="mr-2 h-4 w-4" /> 下载上次导出
                      </Button>
                    )}
                  </div>
                </div>

                <Accordion type="single" collapsible className="w-full rounded-2xl border border-border bg-card px-3">
                  <AccordionItem value="advanced" className="border-0">
                    <AccordionTrigger className="py-3 text-sm font-semibold text-foreground hover:no-underline">
                      高级设置
                    </AccordionTrigger>
                    <AccordionContent>
                      <div className="space-y-4 pb-3">
                        <div className="flex items-center justify-between rounded-lg bg-muted/40 px-3 py-2">
                          <span className="text-xs text-muted-foreground">不确定怎么调时，直接使用默认推荐样式即可。</span>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-7 shrink-0 gap-1 text-xs text-muted-foreground"
                            onClick={actions.resetOverlayControls}
                            disabled={renderActionBusy}
                          >
                            <RotateCcw className="h-3 w-3" />
                            恢复默认
                          </Button>
                        </div>

                        <div className="grid grid-cols-2 gap-x-3 gap-y-2">
                          <div className="space-y-1.5">
                            <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                              标题行数
                            </label>
                            <Select
                              value={(overlayControls.progressLabelMode ?? "auto") as ProgressLabelMode}
                              onValueChange={(value) =>
                                actions.setOverlayControls((previous) => ({
                                  ...previous,
                                  progressLabelMode: value as ProgressLabelMode,
                                }))
                              }
                              disabled={renderActionBusy}
                            >
                              <SelectTrigger className="h-9 w-full">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {progressLabelModeOptions.map((option) => (
                                  <SelectItem key={option.value} value={option.value}>
                                    {option.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>

                          <div className="space-y-1.5">
                            <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                              字幕颜色
                            </label>
                            <Select
                              value={subtitleTheme}
                              onValueChange={(value) =>
                                actions.setSubtitleTheme(value as SubtitleTheme)
                              }
                              disabled={renderActionBusy}
                            >
                              <SelectTrigger className="h-9 w-full">
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {subtitleThemeOptions.map((option) => (
                                  <SelectItem key={option.value} value={option.value}>
                                    {option.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                          </div>
                        </div>

                        <Accordion type="multiple" className="w-full">
                          <AccordionItem value="display" className="border-0">
                            <AccordionTrigger className="py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground hover:no-underline">
                              显示内容
                            </AccordionTrigger>
                            <AccordionContent>
                              <div className="grid grid-cols-2 gap-1.5 pt-1 sm:grid-cols-4">
                                <OverlayToggleTile
                                  label="字幕"
                                  checked={overlayControls.showSubtitles ?? DEFAULT_OVERLAY_CONTROLS.showSubtitles}
                                  disabled={renderActionBusy}
                                  onCheckedChange={(checked) =>
                                    actions.setOverlayControls((previous) => ({
                                      ...previous,
                                      showSubtitles: checked,
                                    }))
                                  }
                                />
                                <OverlayToggleTile
                                  label="高亮"
                                  checked={overlayControls.showHighlights ?? DEFAULT_OVERLAY_CONTROLS.showHighlights}
                                  disabled={renderActionBusy}
                                  onCheckedChange={(checked) =>
                                    actions.setOverlayControls((previous) => ({
                                      ...previous,
                                      showHighlights: checked,
                                    }))
                                  }
                                />
                                <OverlayToggleTile
                                  label="进度条"
                                  checked={overlayControls.showProgress ?? DEFAULT_OVERLAY_CONTROLS.showProgress}
                                  disabled={renderActionBusy}
                                  onCheckedChange={(checked) =>
                                    actions.setOverlayControls((previous) => ({
                                      ...previous,
                                      showProgress: checked,
                                    }))
                                  }
                                />
                                <OverlayToggleTile
                                  label="章节"
                                  checked={overlayControls.showChapter ?? DEFAULT_OVERLAY_CONTROLS.showChapter}
                                  disabled={renderActionBusy}
                                  onCheckedChange={(checked) =>
                                    actions.setOverlayControls((previous) => ({
                                      ...previous,
                                      showChapter: checked,
                                    }))
                                  }
                                />
                              </div>
                            </AccordionContent>
                          </AccordionItem>

                          <Separator />

                          <AccordionItem value="size-position" className="border-0">
                            <AccordionTrigger className="py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground hover:no-underline">
                              大小和位置
                            </AccordionTrigger>
                            <AccordionContent>
                              <div className="space-y-5 pt-1">
                                <div className="space-y-3">
                                  <div className="text-[11px] font-semibold text-muted-foreground">字幕</div>
                                  <DebouncedSlider
                                    label="大小"
                                    valueText={`${Math.round((overlayControls.subtitleScale ?? 1) * 100)}%`}
                                    min={OVERLAY_SCALE_LIMITS.subtitle.min}
                                    max={OVERLAY_SCALE_LIMITS.subtitle.max}
                                    step={OVERLAY_SCALE_LIMITS.subtitle.step}
                                    value={overlayControls.subtitleScale ?? OVERLAY_SCALE_LIMITS.subtitle.defaultValue}
                                    disabled={renderActionBusy}
                                    onChange={(value) =>
                                      actions.setOverlayControls((previous) => ({
                                        ...previous,
                                        subtitleScale: Math.min(
                                          Math.max(value, OVERLAY_SCALE_LIMITS.subtitle.min),
                                          OVERLAY_SCALE_LIMITS.subtitle.max,
                                        ),
                                      }))
                                    }
                                  />
                                  <DebouncedSlider
                                    label="位置"
                                    valueText={`Y ${Math.round(overlayControls.subtitleYPercent ?? DEFAULT_OVERLAY_CONTROLS.subtitleYPercent)}%`}
                                    min={OVERLAY_POSITION_LIMITS.subtitleY.min}
                                    max={OVERLAY_POSITION_LIMITS.subtitleY.max}
                                    step={OVERLAY_POSITION_LIMITS.subtitleY.step}
                                    value={overlayControls.subtitleYPercent ?? OVERLAY_POSITION_LIMITS.subtitleY.defaultValue}
                                    disabled={renderActionBusy}
                                    onChange={(value) =>
                                      actions.setOverlayControls((previous) => ({
                                        ...previous,
                                        subtitleYPercent: Math.min(
                                          Math.max(value, OVERLAY_POSITION_LIMITS.subtitleY.min),
                                          OVERLAY_POSITION_LIMITS.subtitleY.max,
                                        ),
                                      }))
                                    }
                                  />
                                </div>

                                <Separator />

                                <div className="space-y-3">
                                  <div className="text-[11px] font-semibold text-muted-foreground">进度条</div>
                                  <DebouncedSlider
                                    label="大小"
                                    valueText={`${Math.round((overlayControls.progressScale ?? 1) * 100)}%`}
                                    min={OVERLAY_SCALE_LIMITS.progress.min}
                                    max={OVERLAY_SCALE_LIMITS.progress.max}
                                    step={OVERLAY_SCALE_LIMITS.progress.step}
                                    value={overlayControls.progressScale ?? OVERLAY_SCALE_LIMITS.progress.defaultValue}
                                    disabled={renderActionBusy}
                                    onChange={(value) =>
                                      actions.setOverlayControls((previous) => ({
                                        ...previous,
                                        progressScale: Math.min(
                                          Math.max(value, OVERLAY_SCALE_LIMITS.progress.min),
                                          OVERLAY_SCALE_LIMITS.progress.max,
                                        ),
                                      }))
                                    }
                                  />
                                  <DebouncedSlider
                                    label="位置"
                                    valueText={`Y ${Math.round(overlayControls.progressYPercent ?? DEFAULT_OVERLAY_CONTROLS.progressYPercent)}%`}
                                    min={OVERLAY_POSITION_LIMITS.progressY.min}
                                    max={OVERLAY_POSITION_LIMITS.progressY.max}
                                    step={OVERLAY_POSITION_LIMITS.progressY.step}
                                    value={overlayControls.progressYPercent ?? OVERLAY_POSITION_LIMITS.progressY.defaultValue}
                                    disabled={renderActionBusy}
                                    onChange={(value) =>
                                      actions.setOverlayControls((previous) => ({
                                        ...previous,
                                        progressYPercent: Math.min(
                                          Math.max(value, OVERLAY_POSITION_LIMITS.progressY.min),
                                          OVERLAY_POSITION_LIMITS.progressY.max,
                                        ),
                                      }))
                                    }
                                  />
                                </div>

                                <Separator />

                                <div className="space-y-3">
                                  <div className="text-[11px] font-semibold text-muted-foreground">章节</div>
                                  <DebouncedSlider
                                    label="章节块大小"
                                    valueText={`${Math.round((overlayControls.chapterScale ?? 1) * 100)}%`}
                                    min={OVERLAY_SCALE_LIMITS.chapter.min}
                                    max={OVERLAY_SCALE_LIMITS.chapter.max}
                                    step={OVERLAY_SCALE_LIMITS.chapter.step}
                                    value={overlayControls.chapterScale ?? OVERLAY_SCALE_LIMITS.chapter.defaultValue}
                                    disabled={renderActionBusy}
                                    onChange={(value) =>
                                      actions.setOverlayControls((previous) => ({
                                        ...previous,
                                        chapterScale: Math.min(
                                          Math.max(value, OVERLAY_SCALE_LIMITS.chapter.min),
                                          OVERLAY_SCALE_LIMITS.chapter.max,
                                        ),
                                      }))
                                    }
                                  />
                                </div>
                              </div>
                            </AccordionContent>
                          </AccordionItem>
                        </Accordion>
                      </div>
                    </AccordionContent>
                  </AccordionItem>
                </Accordion>
              </div>
            </div>

          </CardContent>
        </Card>
      </div>
    </div>
  );
}
