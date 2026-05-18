"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";

import {
  clearRenderCompletionPending,
  getRenderCompletionPending,
  getWebRenderConfig,
  getWebRenderConfigWithMeta,
  markRenderSucceeded,
  reopenTestForEditing,
  ApiClientError,
  type Job,
  type RenderMeta,
  type WebRenderConfig,
  setRenderCompletionPending,
} from "../../lib/api";
import {
  buildDynamicRenderBitratePlan,
  buildVideoBitrateFallbacks,
  type WebRenderAudioCodec,
  type WebRenderVideoCodec,
} from "../../lib/remotion/export-bitrate";
import {
  PROGRESS_LABEL_MODE_OPTIONS,
  SUBTITLE_THEME_OPTIONS,
} from "../../lib/remotion/constants";
import {
  DEFAULT_OVERLAY_CONTROLS,
  type OverlayScaleControls,
} from "../../lib/remotion/overlay-controls";
import {getRenderConfigTotalDuration} from "../../lib/remotion/utils";
import {
  getFriendlyWebRenderErrorMessage,
  WEB_RENDER_DELAY_RENDER_TIMEOUT_MS,
} from "../../lib/remotion/rendering";
import {
  StitchVideoWeb,
  type SubtitleTheme,
} from "../../lib/remotion/stitch-video-web";
import {getSourceVideoMismatchMessage} from "../../lib/source-video-guard";
import {
  loadCachedJobSourceVideoRecord,
  saveCachedJobSourceVideo,
} from "../../lib/video-cache";
import {
  getRenderSourceDirectExportErrorMessage,
  inspectRenderSourceCompatibility,
} from "../../lib/video-render-compatibility";
import {mergeJobSnapshot} from "../../lib/job-status";
import {STATUS} from "../../lib/workflow";

import {
  RENDER_COMPLETE_RETRY_BASE_MS,
  RENDER_COMPLETE_RETRY_MAX_MS,
} from "./constants";
import {useRenderSourceCompatibility} from "./use-render-source-compatibility";
import {
  buildPreviewRenderMeta,
  clampPercent,
  getFriendlyError,
  getRandomPreviewTime,
  isPreviewRenderMetaReduced,
  resolveRenderMetaFromFile,
  triggerFileDownload,
  withTimeout,
} from "./workspace-utils";
import {buildSrtDownloadFromRenderConfig} from "./export-subtitles";

const RENDER_META_TIMEOUT_MS = 60_000;
const RENDER_CONFIG_TIMEOUT_MS = 90_000;
const EXPORT_SETTINGS_KEY = "ac_export_settings_v1";
const MISSING_RENDER_SOURCE_MESSAGE = "本地渲染所需源视频缓存已丢失，请重新上传视频生成新的导出。";
const REOPEN_ROUTE_NOT_READY_MESSAGE =
  "返回编辑接口暂时不可用，请刷新页面或重启后端服务后再试。";

function loadSavedExportSettings(): {
  overlayControls: OverlayScaleControls | null;
  subtitleTheme: SubtitleTheme | null;
} {
  try {
    const raw = localStorage.getItem(EXPORT_SETTINGS_KEY);
    if (!raw) return {overlayControls: null, subtitleTheme: null};
    const parsed = JSON.parse(raw);
    return {
      overlayControls: parsed.overlayControls ?? null,
      subtitleTheme: parsed.subtitleTheme ?? null,
    };
  } catch {
    return {overlayControls: null, subtitleTheme: null};
  }
}

function saveExportSettings(
  overlayControls: OverlayScaleControls,
  subtitleTheme: SubtitleTheme,
) {
  try {
    localStorage.setItem(
      EXPORT_SETTINGS_KEY,
      JSON.stringify({overlayControls, subtitleTheme}),
    );
  } catch {
    // ignore
  }
}

export function useExportStepController({
  busy,
  job,
  jobId,
  selectedFile,
  setError,
  setJob,
  setSelectedFile,
}: {
  busy: boolean;
  job: Job | null;
  jobId: string;
  selectedFile: File | null;
  setError: (error: string) => void;
  setJob: Dispatch<SetStateAction<Job | null>>;
  setSelectedFile: Dispatch<SetStateAction<File | null>>;
}) {
  const [renderPreviewProfile, setRenderPreviewProfile] = useState<{
    width: number;
    height: number;
    fps: number;
    isReduced: boolean;
  } | null>(null);
  const [renderNote, setRenderNote] = useState("");
  const [renderCompletionMarkerMessage, setRenderCompletionMarkerMessage] =
    useState("");
  const [renderBusy, setRenderBusy] = useState(false);
  const [renderProgress, setRenderProgress] = useState(0);
  const [renderDownloadUrl, setRenderDownloadUrl] = useState<string | null>(null);
  const [renderFileName, setRenderFileName] = useState("output.mp4");
  const [subtitleExportBusy, setSubtitleExportBusy] = useState(false);
  const [subtitleDownloadUrl, setSubtitleDownloadUrl] = useState<string | null>(null);
  const [subtitleFileName, setSubtitleFileName] = useState("output.txt");
  const [renderConfig, setRenderConfig] = useState<WebRenderConfig | null>(null);
  const [renderConfigBusy, setRenderConfigBusy] = useState(false);
  const [renderSetupError, setRenderSetupError] = useState("");
  const [reopenEditorBusy, setReopenEditorBusy] = useState(false);
  const [previewTimeSec, setPreviewTimeSec] = useState(0);
  const [cachedRenderMeta, setCachedRenderMeta] = useState<RenderMeta | null>(null);

  const savedSettings = useRef(loadSavedExportSettings());
  const [subtitleTheme, setSubtitleTheme] = useState<SubtitleTheme>(
    savedSettings.current.subtitleTheme ?? "stroke-white",
  );
  const [overlayControls, setOverlayControls] = useState<OverlayScaleControls>(
    savedSettings.current.overlayControls ?? {...DEFAULT_OVERLAY_CONTROLS},
  );
  const {renderSourceCompatibility, setRenderSourceCompatibility} =
    useRenderSourceCompatibility(selectedFile);

  // Persist settings to localStorage whenever they change
  useEffect(() => {
    saveExportSettings(overlayControls, subtitleTheme);
  }, [overlayControls, subtitleTheme]);

  // beforeunload guard during render
  useEffect(() => {
    if (!renderBusy) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "正在导出视频中，离开页面将丢失进度。";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [renderBusy]);

  const loadRenderConfigWithMeta = useCallback(
    async (
      sourceFile: File,
      meta: Awaited<ReturnType<typeof resolveRenderMetaFromFile>>,
      options: {timeoutMs?: {config?: number}} = {},
    ): Promise<WebRenderConfig> => {
      const configRequest = getWebRenderConfigWithMeta(jobId, meta);
      const config =
        typeof options.timeoutMs?.config === "number"
          ? await withTimeout(
              configRequest,
              options.timeoutMs.config,
              "生成预览配置超时，请重试。",
            )
          : await configRequest;
      const sourceMismatchMessage = getSourceVideoMismatchMessage(
        sourceFile.name,
        meta,
        config,
      );
      if (sourceMismatchMessage) {
        throw new Error(sourceMismatchMessage);
      }
      return config;
    },
    [jobId],
  );

  const loadRenderSourceAsset = useCallback(async (): Promise<{
    sourceFile: File | null;
    renderMeta: RenderMeta | null;
  }> => {
    if (selectedFile && cachedRenderMeta) {
      return {sourceFile: selectedFile, renderMeta: cachedRenderMeta};
    }

    if (selectedFile) {
      const cachedRecord = await loadCachedJobSourceVideoRecord(jobId).catch(
        () => null,
      );
      const renderMeta = cachedRecord?.renderMeta ?? null;
      if (renderMeta) {
        setCachedRenderMeta(renderMeta);
      }
      return {sourceFile: selectedFile, renderMeta};
    }

    const cachedRecord = await loadCachedJobSourceVideoRecord(jobId).catch(
      () => null,
    );
    if (!cachedRecord) {
      return {sourceFile: null, renderMeta: null};
    }

    setSelectedFile(cachedRecord.file);
    setCachedRenderMeta(cachedRecord.renderMeta);
    return {
      sourceFile: cachedRecord.file,
      renderMeta: cachedRecord.renderMeta,
    };
  }, [
    cachedRenderMeta,
    jobId,
    selectedFile,
    setSelectedFile,
  ]);

  const applyRenderPreviewConfig = useCallback((config: WebRenderConfig) => {
    setRenderConfig(config);
    setPreviewTimeSec((previous) => {
      const totalDuration = getRenderConfigTotalDuration(config);
      if (previous > 0 && previous < totalDuration) {
        return previous;
      }
      return getRandomPreviewTime(config);
    });
    return config;
  }, []);

  const resolveSourceRenderMeta = useCallback(
    async (
      sourceFile: File,
      renderMeta: RenderMeta | null,
      options: {persistCache?: boolean} = {},
    ): Promise<RenderMeta> => {
      if (renderMeta) {
        setCachedRenderMeta(renderMeta);
        return renderMeta;
      }

      const resolvedMeta = await withTimeout(
        resolveRenderMetaFromFile(sourceFile),
        RENDER_META_TIMEOUT_MS,
        "读取本地视频元数据超时。当前源片较大，请稍后重试，或重新上传视频后再试。",
      );
      if (options.persistCache !== false) {
        setCachedRenderMeta(resolvedMeta);
        void saveCachedJobSourceVideo(jobId, sourceFile, {
          renderMeta: resolvedMeta,
        }).catch(() => undefined);
      }
      return resolvedMeta;
    },
    [jobId],
  );

  const prepareRenderPreviewForFile = useCallback(
    async (
      sourceFile: File,
      renderMeta: RenderMeta | null = null,
    ): Promise<WebRenderConfig | null> => {
      setRenderConfigBusy(true);
      setRenderSetupError("");
      try {
        const meta = await resolveSourceRenderMeta(sourceFile, renderMeta);
        const previewMeta = buildPreviewRenderMeta(meta);
        setRenderPreviewProfile({
          width: previewMeta.width,
          height: previewMeta.height,
          fps: previewMeta.fps,
          isReduced: isPreviewRenderMetaReduced(meta, previewMeta),
        });
        const config = await loadRenderConfigWithMeta(sourceFile, previewMeta, {
          timeoutMs: {config: RENDER_CONFIG_TIMEOUT_MS},
        });
        return applyRenderPreviewConfig(config);
      } catch (err) {
        setRenderConfig(null);
        setRenderPreviewProfile(null);
        setRenderSetupError(
          err instanceof Error ? err.message : "导出预览初始化失败，请重试。",
        );
        return null;
      } finally {
        setRenderConfigBusy(false);
      }
    },
    [applyRenderPreviewConfig, loadRenderConfigWithMeta, resolveSourceRenderMeta],
  );

  const prepareRenderPreview = useCallback(async (): Promise<WebRenderConfig | null> => {
    if (renderBusy) {
      return null;
    }

    try {
      if (!selectedFile) {
        const config = await getWebRenderConfig(jobId);
        applyRenderPreviewConfig(config);
        return config;
      }

      const {sourceFile, renderMeta} = await loadRenderSourceAsset();
      if (!sourceFile) {
        throw new Error(MISSING_RENDER_SOURCE_MESSAGE);
      }
      return await prepareRenderPreviewForFile(sourceFile, renderMeta);
    } catch (err) {
      setRenderConfig(null);
      setRenderPreviewProfile(null);
      setRenderSetupError(
        err instanceof Error ? err.message : "导出预览初始化失败，请重试。",
      );
      return null;
    }
  }, [
    applyRenderPreviewConfig,
    getWebRenderConfig,
    jobId,
    loadRenderSourceAsset,
    prepareRenderPreviewForFile,
    renderBusy,
    selectedFile,
  ]);

  useEffect(() => {
    return () => {
      if (renderDownloadUrl) {
        URL.revokeObjectURL(renderDownloadUrl);
      }
      if (subtitleDownloadUrl) {
        URL.revokeObjectURL(subtitleDownloadUrl);
      }
    };
  }, [renderDownloadUrl, subtitleDownloadUrl]);

  useEffect(() => {
    setRenderBusy(false);
    setRenderProgress(0);
    setRenderConfig(null);
    setRenderPreviewProfile(null);
    setRenderConfigBusy(false);
    setRenderSetupError("");
    setRenderCompletionMarkerMessage("");
    setPreviewTimeSec(0);
    setCachedRenderMeta(null);
    setRenderNote("");
    setRenderDownloadUrl((previous) => {
      if (previous) {
        URL.revokeObjectURL(previous);
      }
      return null;
    });
    setRenderFileName("output.mp4");
    setSubtitleExportBusy(false);
    setSubtitleDownloadUrl((previous) => {
      if (previous) {
        URL.revokeObjectURL(previous);
      }
      return null;
    });
    setSubtitleFileName("output.txt");
    // Do NOT reset subtitleTheme/overlayControls here so user preferences survive job switches
    setSelectedFile(null);
  }, [jobId, setSelectedFile]);

  useEffect(() => {
    let active = true;
    loadCachedJobSourceVideoRecord(jobId)
      .then((record) => {
        if (!active || !record) {
          return;
        }
        setSelectedFile((previous) => previous ?? record.file);
        setCachedRenderMeta(record.renderMeta);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [jobId, setSelectedFile]);



  useEffect(() => {
    if (!job) {
      return;
    }
    if (job.status === STATUS.SUCCEEDED) {
      setRenderCompletionMarkerMessage("");
      clearRenderCompletionPending(jobId);
      return;
    }
    if (job.status !== STATUS.TEST_CONFIRMED) {
      return;
    }

    const marker = getRenderCompletionPending(jobId);
    if (!marker) {
      return;
    }

    let cancelled = false;
    let timer: number | null = null;

    const retry = async () => {
      if (cancelled) {
        return;
      }
      const latestMarker = getRenderCompletionPending(jobId);
      if (!latestMarker) {
        return;
      }
      try {
        const completion = await markRenderSucceeded(jobId, {keepalive: true});
        if (cancelled) {
          return;
        }
        clearRenderCompletionPending(jobId);
        setRenderCompletionMarkerMessage("");
        setJob((previous) => mergeJobSnapshot(previous, completion.job));
      } catch (err) {
        if (cancelled) {
          return;
        }
        const message = getFriendlyError(err);
        const nextMarker = setRenderCompletionPending(jobId, message);
        const delay = Math.min(
          RENDER_COMPLETE_RETRY_MAX_MS,
          RENDER_COMPLETE_RETRY_BASE_MS *
            2 ** Math.max((nextMarker?.attempts || 1) - 1, 0),
        );
        setRenderCompletionMarkerMessage(
          `导出确认未完成：${message}，约 ${Math.ceil(delay / 1000)} 秒后将自动重试。`,
        );
        timer = window.setTimeout(retry, delay);
      }
    };

    void retry();

    return () => {
      cancelled = true;
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [job?.status, jobId, setJob]);

  useEffect(() => {
    const exportReady =
      job?.status === STATUS.TEST_CONFIRMED || job?.status === STATUS.SUCCEEDED;
    if (!exportReady || renderConfig || renderConfigBusy || renderSetupError) {
      return;
    }
    void prepareRenderPreview();
  }, [
    job?.status,
    prepareRenderPreview,
    renderConfig,
    renderConfigBusy,
    renderSetupError,
  ]);

  const handleStartRender = useCallback(async () => {
    setError("");
    setRenderNote("正在准备导出…");
    setRenderSetupError("");
    setRenderBusy(true);
    setRenderProgress(0);

    let sourceObjectUrl: string | null = null;
    try {
      const {
        sourceFile: initialSourceFile,
        renderMeta: initialRenderMeta,
      } = await loadRenderSourceAsset();
      if (!initialSourceFile) {
        throw new Error(MISSING_RENDER_SOURCE_MESSAGE);
      }

      const sourceFile = initialSourceFile;
      const sourceMeta = await resolveSourceRenderMeta(
        sourceFile,
        initialRenderMeta,
      );
      const resolvedConfig = await loadRenderConfigWithMeta(sourceFile, sourceMeta);

      const compatibility =
        await inspectRenderSourceCompatibility(initialSourceFile);
      setRenderSourceCompatibility(compatibility);
      const compatibilityError = getRenderSourceDirectExportErrorMessage(
        compatibility,
      );
      if (compatibilityError) {
        throw new Error(compatibilityError);
      }

      setRenderNote("正在检测浏览器编码能力…");

      sourceObjectUrl = URL.createObjectURL(sourceFile);
      const inputProps = {
        ...resolvedConfig.input_props,
        src: sourceObjectUrl,
        subtitleTheme,
        subtitleScale: overlayControls.subtitleScale,
        subtitleYPercent: overlayControls.subtitleYPercent,
        progressScale: overlayControls.progressScale,
        progressYPercent: overlayControls.progressYPercent,
        chapterScale: overlayControls.chapterScale,
        showSubtitles: overlayControls.showSubtitles,
        showHighlights: overlayControls.showHighlights,
        showProgress: overlayControls.showProgress,
        showChapter: overlayControls.showChapter,
        progressLabelMode: overlayControls.progressLabelMode,
      };
      const composition = {
        ...resolvedConfig.composition,
        component: StitchVideoWeb,
        defaultProps: inputProps,
      };

      if (!window.isSecureContext) {
        throw new Error(
          "当前页面不在安全上下文中（需要 HTTPS 或 localhost），浏览器禁用了视频解码器 (VideoDecoder)，无法导出视频。请通过 HTTPS 访问本站，或联系管理员配置 SSL 证书。",
        );
      }

      if (typeof document !== "undefined" && "fonts" in document) {
        try {
          await document.fonts.ready;
        } catch {
          // ignore
        }
      }

      const {renderMediaOnWeb, getEncodableAudioCodecs, getEncodableVideoCodecs} =
        await import("@remotion/web-renderer");

      const mp4AudioCodecs = await getEncodableAudioCodecs("mp4");
      const webmAudioCodecs = await getEncodableAudioCodecs("webm");
      const hasMp4Audio = mp4AudioCodecs.length > 0;
      const hasWebmAudio = webmAudioCodecs.length > 0;

      let container: "mp4" | "webm" = "mp4";
      let videoCodec: WebRenderVideoCodec = "h264";
      if (hasMp4Audio) {
        container = "mp4";
        videoCodec = "h264";
      } else if (hasWebmAudio) {
        container = "webm";
        videoCodec = "vp8";
      } else {
        throw new Error(
          "No audio codec can be encoded by this browser for container mp4 or webm.",
        );
      }

      const audioCodec: WebRenderAudioCodec =
        container === "mp4" ? "aac" : "opus";
      const bitratePlan = buildDynamicRenderBitratePlan({
        meta: sourceMeta,
        fileSizeBytes: sourceFile.size,
        videoCodec,
        audioCodec,
      });

      let resolvedVideoBitrate = bitratePlan.videoBitrate;
      const bitrateCandidates = buildVideoBitrateFallbacks(
        bitratePlan.videoBitrate,
        bitratePlan.fallbackVideoBitrate,
      );

      for (const candidate of bitrateCandidates) {
        const encodableVideoCodecs = await getEncodableVideoCodecs(container, {
          videoBitrate: candidate,
        });
        if (encodableVideoCodecs.includes(videoCodec)) {
          resolvedVideoBitrate = candidate;
          break;
        }
      }

      let resolvedAudioBitrate = bitratePlan.audioBitrate;
      const audioBitrateCandidates = Array.from(
        new Set([
          bitratePlan.audioBitrate,
          audioCodec === "aac" ? 128_000 : 96_000,
        ]),
      );
      let audioCodecSupported = false;
      for (const candidate of audioBitrateCandidates) {
        const encodableAudioCodecs = await getEncodableAudioCodecs(container, {
          audioBitrate: candidate,
        });
        if (encodableAudioCodecs.includes(audioCodec)) {
          resolvedAudioBitrate = candidate;
          audioCodecSupported = true;
          break;
        }
      }
      if (!audioCodecSupported) {
        throw new Error(
          `No audio codec can be encoded by this browser for container ${container}.`,
        );
      }

      setRenderNote("正在渲染视频…");

      const renderOptions: Parameters<typeof renderMediaOnWeb>[0] = {
        composition: composition as Parameters<typeof renderMediaOnWeb>[0]["composition"],
        inputProps,
        container,
        videoCodec,
        audioBitrate: resolvedAudioBitrate,
        videoBitrate: resolvedVideoBitrate,
        delayRenderTimeoutInMilliseconds: WEB_RENDER_DELAY_RENDER_TIMEOUT_MS,
        onProgress: (progress) => {
          const totalFrames = Math.max(
            1,
            Number(resolvedConfig.composition.durationInFrames) || 1,
          );
          const doneFrames =
            typeof progress.encodedFrames === "number" &&
            Number.isFinite(progress.encodedFrames)
              ? progress.encodedFrames
              : progress.renderedFrames;
          const percent = clampPercent((doneFrames / totalFrames) * 100);
          setRenderProgress((previous) => Math.max(previous, percent));
          if (percent < 30) {
            setRenderNote("正在渲染视频…");
          } else if (percent < 70) {
            setRenderNote("正在编码画面…");
          } else if (percent < 95) {
            setRenderNote("正在封装视频…");
          } else {
            setRenderNote("即将完成…");
          }
        },
      };

      const result = await renderMediaOnWeb(renderOptions);
      const baseName = (resolvedConfig.output_name || "output").replace(
        /\.(mp4|webm)$/i,
        "",
      );
      const outputName = `${baseName}.${container}`;
      if (
        bitratePlan.usingSourceBitrate ||
        resolvedVideoBitrate !== bitratePlan.fallbackVideoBitrate
      ) {
        setRenderNote(
          `已按源片码率策略导出，视频约 ${Math.round(resolvedVideoBitrate / 1_000_000)} Mbps，音频约 ${Math.round(
            resolvedAudioBitrate / 1_000,
          )} kbps。`,
        );
      } else {
        setRenderNote("导出完成");
      }
      setRenderFileName(outputName);
      const blob = await result.getBlob();
      const objectUrl = URL.createObjectURL(blob);
      setRenderDownloadUrl((previous) => {
        if (previous) {
          URL.revokeObjectURL(previous);
        }
        return objectUrl;
      });
      setRenderCompletionPending(jobId);
      triggerFileDownload(objectUrl, outputName);
      setRenderProgress(100);
      try {
        const completion = await markRenderSucceeded(jobId, {keepalive: true});
        setJob((previous) => mergeJobSnapshot(previous, completion.job));
        clearRenderCompletionPending(jobId);
        setRenderCompletionMarkerMessage("");
      } catch (syncErr) {
        const message = getFriendlyError(syncErr);
        setRenderCompletionMarkerMessage(
          `视频已导出，但服务端确认失败：${message}。页面刷新后会自动继续重试确认。`,
        );
        setRenderCompletionPending(jobId, message);
      }
    } catch (err) {
      setError(getFriendlyWebRenderErrorMessage(err));
      setRenderNote("");
    } finally {
      if (sourceObjectUrl) {
        URL.revokeObjectURL(sourceObjectUrl);
      }
      setRenderBusy(false);
    }
  }, [
    jobId,
    loadRenderConfigWithMeta,
    loadRenderSourceAsset,
    overlayControls,
    renderConfig,
    resolveSourceRenderMeta,
    setError,
    setJob,
    setRenderSourceCompatibility,
    subtitleTheme,
  ]);

  const handleExportSubtitles = useCallback(async () => {
    setError("");
    setSubtitleExportBusy(true);
    try {
      const resolvedConfig = renderConfig ?? (await getWebRenderConfig(jobId));
      if (!renderConfig) {
        applyRenderPreviewConfig(resolvedConfig);
      }
      const {content, fileName} = buildSrtDownloadFromRenderConfig(resolvedConfig);
      const blob = new Blob([content], {type: "text/plain;charset=utf-8"});
      const objectUrl = URL.createObjectURL(blob);
      setSubtitleFileName(fileName);
      setSubtitleDownloadUrl((previous) => {
        if (previous) {
          URL.revokeObjectURL(previous);
        }
        return objectUrl;
      });
      triggerFileDownload(objectUrl, fileName);
    } catch (err) {
      setError(getFriendlyError(err) || "导出字幕失败，请重试。");
    } finally {
      setSubtitleExportBusy(false);
    }
  }, [applyRenderPreviewConfig, getWebRenderConfig, jobId, renderConfig, setError]);

  const handleReopenEditor = useCallback(async () => {
    if (
      renderBusy ||
      reopenEditorBusy ||
      job?.status !== STATUS.TEST_CONFIRMED
    ) {
      return;
    }
    setError("");
    setRenderSetupError("");
    setReopenEditorBusy(true);
    try {
      const reopenedJob = await reopenTestForEditing(jobId);
      setRenderConfig(null);
      setRenderPreviewProfile(null);
      setRenderDownloadUrl(null);
      setSubtitleDownloadUrl(null);
      setRenderNote("");
      setJob(reopenedJob);
    } catch (err) {
      const message =
        err instanceof ApiClientError && err.status === 404
          ? REOPEN_ROUTE_NOT_READY_MESSAGE
          : getFriendlyError(err);
      setError(message || "返回编辑步骤失败，请重试。");
    } finally {
      setReopenEditorBusy(false);
    }
  }, [
    job?.status,
    jobId,
    reopenEditorBusy,
    renderBusy,
    setError,
    setJob,
  ]);

  useEffect(() => {
    if (renderBusy) {
      return;
    }
    setRenderProgress(0);
  }, [overlayControls, renderBusy, subtitleTheme]);

  const effectiveRenderSourceFile = selectedFile;
  const hasRenderSource = Boolean(effectiveRenderSourceFile);
  const canReopenEditor = job?.status === STATUS.TEST_CONFIRMED;
  const renderActionBusy = renderBusy;
  const renderDisabledReason = (() => {
    if (renderConfigBusy) return "正在生成预览配置，请稍等。";
    if (!hasRenderSource) return MISSING_RENDER_SOURCE_MESSAGE;
    if (busy) return "当前步骤仍在处理中，完成后才能导出。";
    if (renderActionBusy) return "视频正在导出，请保持页面开启。";
    if (renderSourceCompatibility.status === "checking") {
      return "正在检测原始视频是否可直接导出。";
    }
    if (
      renderSourceCompatibility.status === "blocked" ||
      renderSourceCompatibility.status === "incompatible"
    ) {
      return renderSourceCompatibility.message || "当前原始视频暂不能直接导出。";
    }
    return "";
  })();
  const canStartRender = !renderDisabledReason;
  const renderPrimaryButtonLabel = "导出视频";

  // Estimate output file size (very rough)
  const estimatedFileSize = (() => {
    if (!renderConfig || !cachedRenderMeta) return null;
    const duration = getRenderConfigTotalDuration(renderConfig);
    if (!duration || !Number.isFinite(duration)) return null;
    // rough estimate: 4 Mbps default for h264 1080p
    const estBitrate = 4_000_000;
    const bytes = (duration * estBitrate) / 8;
    if (bytes < 1024 * 1024) {
      return `${Math.round(bytes / 1024)} KB`;
    }
    return `${Math.round(bytes / (1024 * 1024))} MB`;
  })();

  return {
    state: {
      canStartRender,
      canReopenEditor,
      estimatedFileSize,
      hasRenderSource,
      overlayControls,
      previewTimeSec,
      reopenEditorBusy,
      progressLabelModeOptions: PROGRESS_LABEL_MODE_OPTIONS,
      renderActionBusy,
      renderBusy,
      renderCompletionMarkerMessage,
      renderConfig,
      renderConfigBusy,
      renderDownloadUrl,
      renderFileName,
      renderDisabledReason,
      renderNote,
      renderPreviewProfile,
      renderPrimaryButtonLabel,
      renderProgress,
      renderSetupError,
      renderSourceCompatibility,
      renderSourceFile: effectiveRenderSourceFile,
      renderSourceMeta: cachedRenderMeta,
      selectedFile,
      subtitleDownloadUrl,
      subtitleExportBusy,
      subtitleFileName,
      subtitleTheme,
      subtitleThemeOptions: SUBTITLE_THEME_OPTIONS,
    },
    actions: {
      clearRenderMessage: () => setRenderCompletionMarkerMessage(""),
      handleExportSubtitles,
      handleReopenEditor,
      handleStartRender,
      prepareRenderPreview,
      resetOverlayControls: () => setOverlayControls({...DEFAULT_OVERLAY_CONTROLS}),
      setOverlayControls,
      setSelectedFile,
      setSubtitleTheme,
    },
  };
}
