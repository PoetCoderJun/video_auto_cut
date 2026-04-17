"use client";

import React, {ChangeEvent, useRef} from "react";

import ExportFramePreview from "@/components/export-frame-preview";
import {Badge} from "@/components/ui/badge";
import {Button} from "@/components/ui/button";
import {Card, CardContent} from "@/components/ui/card";
import {Checkbox} from "@/components/ui/checkbox";
import {Progress} from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {WebRenderConfig} from "@/lib/api";
import type {SubtitleTheme} from "@/lib/remotion/stitch-video-web";
import {
  DEFAULT_OVERLAY_CONTROLS,
  OVERLAY_POSITION_LIMITS,
  OVERLAY_SCALE_LIMITS,
  type OverlayScaleControls,
  type ProgressLabelMode,
} from "@/lib/remotion/overlay-controls";
import {cn} from "@/lib/utils";
import {Download, FileVideo, Loader2} from "lucide-react";

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
        "flex cursor-pointer items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm transition hover:border-slate-300 hover:bg-slate-50",
        disabled && "cursor-not-allowed opacity-60",
      )}
    >
      <span className="font-medium text-slate-700">{label}</span>
      <Checkbox
        checked={checked}
        disabled={disabled}
        onCheckedChange={(value) => onCheckedChange(Boolean(value))}
      />
    </label>
  );
}

function OverlaySliderField({
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
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px] font-medium text-slate-500">
        <span>{label}</span>
        <span>{valueText}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.currentTarget.value))}
        className="h-2 w-full cursor-ew-resize accent-slate-900 disabled:cursor-not-allowed"
      />
    </div>
  );
}

export function ExportStep({
  actions,
  state,
}: {
  actions: {
    clearRenderMessage: () => void;
    handleSourceFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
    handleStartRender: () => void;
    prepareRenderPreview: () => Promise<WebRenderConfig | null>;
    setOverlayControls: React.Dispatch<React.SetStateAction<OverlayScaleControls>>;
    setSubtitleTheme: React.Dispatch<React.SetStateAction<SubtitleTheme>>;
  };
  state: {
    busy: boolean;
    canStartRender: boolean;
    hasRenderSource: boolean;
    overlayControls: OverlayScaleControls;
    previewTimeSec: number;
    progressLabelModeOptions: Array<{value: ProgressLabelMode; label: string}>;
    renderActionBusy: boolean;
    renderBusy: boolean;
    renderConfig: WebRenderConfig | null;
    renderConfigBusy: boolean;
    renderDownloadUrl: string | null;
    renderFileName: string;
    renderPrimaryButtonLabel: string;
    renderPreviewProfile: {
      width: number;
      height: number;
      fps: number;
      isReduced: boolean;
    } | null;
    renderProgress: number;
    renderSetupError: string;
    renderSourceCompatibility: RenderSourceCompatibilityState;
    selectedFile: File | null;
    subtitleTheme: SubtitleTheme;
    subtitleThemeOptions: Array<{value: SubtitleTheme; label: string}>;
    supportedUploadAccept: string;
  };
}) {
  const renderSourceInputRef = useRef<HTMLInputElement>(null);
  const {
    busy,
    canStartRender,
    hasRenderSource,
    overlayControls,
    previewTimeSec,
    progressLabelModeOptions,
    renderActionBusy,
    renderBusy,
    renderConfig,
    renderConfigBusy,
    renderDownloadUrl,
    renderFileName,
    renderPrimaryButtonLabel,
    renderProgress,
    renderSetupError,
    renderSourceCompatibility,
    selectedFile,
    subtitleTheme,
    subtitleThemeOptions,
    supportedUploadAccept,
  } = state;

  return (
    <div className="space-y-4">
      <div className="mx-auto grid max-w-[1400px] gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(420px,0.92fr)] xl:items-start 2xl:max-w-[1520px] 2xl:grid-cols-[minmax(0,1.72fr)_minmax(456px,0.94fr)]">
        <div className="flex h-full min-h-0 flex-col gap-3 xl:h-[min(70vh,760px)]">
          <ExportFramePreview
            config={renderConfig}
            sourceFile={selectedFile}
            subtitleTheme={subtitleTheme}
            previewTimeSec={previewTimeSec}
            overlayControls={overlayControls}
          />
          {renderConfigBusy && (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在生成预览配置...
            </div>
          )}
          {renderSetupError && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              {renderSetupError}
            </div>
          )}
        </div>

        <Card className="overflow-hidden xl:self-start">
          <CardContent className="flex flex-col p-0">
            <input
              ref={renderSourceInputRef}
              type="file"
              accept={supportedUploadAccept}
              className="hidden"
              onChange={actions.handleSourceFileChange}
              disabled={renderActionBusy || busy}
            />

            <div className="border-b border-slate-200 bg-slate-50/60 px-3 py-2">
              <div className="text-sm font-semibold text-slate-900">导出设置</div>
            </div>

            <div className="px-3 py-2.5">
              <div className="space-y-2">
                {!hasRenderSource ? (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                    <p>尚未读取到当前项目的本地源视频缓存，导出前请重新选择源文件。</p>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="mt-2"
                      onClick={() => renderSourceInputRef.current?.click()}
                      disabled={renderActionBusy || busy}
                    >
                      重新选择源文件
                    </Button>
                  </div>
                ) : null}

                {hasRenderSource && renderSourceCompatibility.status === "checking" ? (
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                    <div className="flex items-center gap-2">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>{renderSourceCompatibility.message}</span>
                    </div>
                  </div>
                ) : null}

                {hasRenderSource && renderSourceCompatibility.status === "incompatible" ? (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                    <div className="font-medium">当前源视频不能直接浏览器导出</div>
                    <div className="mt-1">{renderSourceCompatibility.message}</div>
                  </div>
                ) : null}

                {hasRenderSource && renderSourceCompatibility.status === "blocked" ? (
                  <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
                    {renderSourceCompatibility.message}
                  </div>
                ) : null}

                {hasRenderSource && renderSourceCompatibility.status === "unknown" ? (
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                    {renderSourceCompatibility.message}
                  </div>
                ) : null}

                <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
                  <div className="space-y-1">
                    <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
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

                  <div className="space-y-1">
                    <label className="block text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                      字幕样式
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

                <section className="space-y-1 pt-1">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                    显示内容
                  </div>
                  <div className="grid grid-cols-3 gap-1.5">
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
                </section>

                <section className="space-y-1 border-t border-slate-100 pt-1.5">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                    字幕
                  </div>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                    <OverlaySliderField
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
                    <OverlaySliderField
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
                </section>

                <section className="space-y-1 border-t border-slate-100 pt-1.5">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                    进度条
                  </div>
                  <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                    <OverlaySliderField
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
                    <OverlaySliderField
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
                </section>

                <section className="space-y-1 border-t border-slate-100 pt-1.5">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                    章节
                  </div>
                  <OverlaySliderField
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
                </section>
              </div>
            </div>

            <div className="border-t border-slate-200 bg-white px-3 py-2.5">
              {renderBusy && (
                <div className="mb-2.5 space-y-1.5">
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>导出进度</span>
                    <span>{Math.round(renderProgress)}%</span>
                  </div>
                  <Progress value={renderProgress} className="h-2" />
                </div>
              )}

              <div className="grid gap-1.5">
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
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 正在生成预览
                    </>
                  ) : (
                    "刷新预览"
                  )}
                </Button>
                <Button
                  type="button"
                  className="w-full"
                  onClick={actions.handleStartRender}
                  disabled={!canStartRender || renderConfigBusy}
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
                {renderDownloadUrl && (
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full"
                    onClick={() => triggerFileDownload(renderDownloadUrl, renderFileName)}
                  >
                    <Download className="mr-2 h-4 w-4" /> 下载上次导出
                  </Button>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
