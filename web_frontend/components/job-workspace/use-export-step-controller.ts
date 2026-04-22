"use client";

import {
  useCallback,
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";

import {
  clearRenderCompletionPending,
  downloadRenderSourceVideo,
  getRenderCompletionPending,
  getWebRenderConfig,
  getWebRenderConfigWithMeta,
  markRenderSucceeded,
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
  SUPPORTED_UPLOAD_EXTENSIONS,
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

const RENDER_META_TIMEOUT_MS = 60_000;
const RENDER_CONFIG_TIMEOUT_MS = 90_000;

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
  const [renderConfig, setRenderConfig] = useState<WebRenderConfig | null>(null);
  const [renderConfigBusy, setRenderConfigBusy] = useState(false);
  const [renderSourceFile, setRenderSourceFile] = useState<File | null>(null);
  const [renderSetupError, setRenderSetupError] = useState("");
  const [previewTimeSec, setPreviewTimeSec] = useState(0);
  const [cachedRenderMeta, setCachedRenderMeta] = useState<RenderMeta | null>(null);
  const [subtitleTheme, setSubtitleTheme] =
    useState<SubtitleTheme>("white");
  const [overlayControls, setOverlayControls] = useState<OverlayScaleControls>({
    ...DEFAULT_OVERLAY_CONTROLS,
  });
  const {renderSourceCompatibility, setRenderSourceCompatibility} =
    useRenderSourceCompatibility(selectedFile);

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
    if (renderSourceFile) {
      return {sourceFile: renderSourceFile, renderMeta: null};
    }

    if (renderConfig?.input_props.sourceKind === "cut-proxy") {
      const downloaded = await downloadRenderSourceVideo(jobId);
      setRenderSourceFile(downloaded);
      return {sourceFile: downloaded, renderMeta: null};
    }

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
    downloadRenderSourceVideo,
    jobId,
    renderConfig?.input_props.sourceKind,
    renderSourceFile,
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
        "读取本地视频元数据超时。当前源片较大，请稍后重试，或重新选择文件后再试。",
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
        if (config.input_props.sourceKind === "cut-proxy") {
          const proxyFile = await downloadRenderSourceVideo(jobId);
          setRenderSourceFile(proxyFile);
        }
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
    [applyRenderPreviewConfig, downloadRenderSourceVideo, jobId, loadRenderConfigWithMeta, resolveSourceRenderMeta],
  );

  const prepareRenderPreview = useCallback(async (): Promise<WebRenderConfig | null> => {
    if (renderBusy) {
      return null;
    }

    try {
      if (!selectedFile) {
        const config = await getWebRenderConfig(jobId);
        applyRenderPreviewConfig(config);
        if (config.input_props.sourceKind === "cut-proxy") {
          const sourceFile = await downloadRenderSourceVideo(jobId);
          setRenderSourceFile(sourceFile);
          const meta = await resolveSourceRenderMeta(sourceFile, null, {persistCache: false});
          const previewMeta = buildPreviewRenderMeta(meta);
          setRenderPreviewProfile({
            width: previewMeta.width,
            height: previewMeta.height,
            fps: previewMeta.fps,
            isReduced: isPreviewRenderMetaReduced(meta, previewMeta),
          });
        }
        return config;
      }

      const {sourceFile, renderMeta} = await loadRenderSourceAsset();
      if (!sourceFile) {
        throw new Error("当前会话缺少本地原始视频，请先重新选择当前任务对应的源文件。");
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
    downloadRenderSourceVideo,
    getWebRenderConfig,
    jobId,
    loadRenderSourceAsset,
    prepareRenderPreviewForFile,
    renderBusy,
    resolveSourceRenderMeta,
    selectedFile,
  ]);

  useEffect(() => {
    return () => {
      if (renderDownloadUrl) {
        URL.revokeObjectURL(renderDownloadUrl);
      }
    };
  }, [renderDownloadUrl]);

  useEffect(() => {
    setRenderBusy(false);
    setRenderProgress(0);
    setRenderConfig(null);
    setRenderPreviewProfile(null);
    setRenderConfigBusy(false);
    setRenderSourceFile(null);
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
    setSubtitleTheme("white");
    setOverlayControls({...DEFAULT_OVERLAY_CONTROLS});
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

  const handleSourceFileChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      const input = event.currentTarget;
      const file = input.files?.[0];
      input.value = "";
      if (!file) {
        return;
      }

      const lowerName = file.name.toLowerCase();
      const hasSupportedExt = SUPPORTED_UPLOAD_EXTENSIONS.some((ext) =>
        lowerName.endsWith(ext),
      );
      if (!hasSupportedExt) {
        setRenderSetupError(
          "这个文件格式暂不支持。请上传 MP4、MOV、MKV、WebM、M4V、TS、M2TS 或 MTS 视频。",
        );
        return;
      }

      setSelectedFile(file);
      setCachedRenderMeta(null);
      setRenderSetupError("");
      setRenderCompletionMarkerMessage("");
      if (selectedFile?.name !== file.name || selectedFile?.size !== file.size) {
        setRenderFileName("output.mp4");
      }
      void saveCachedJobSourceVideo(jobId, file).catch(() => undefined);
      void prepareRenderPreviewForFile(file, null);
    },
    [jobId, prepareRenderPreviewForFile, selectedFile, setSelectedFile],
  );

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
    setRenderNote("");
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
        throw new Error("当前会话缺少本地原始视频，请先选择对应的源文件后再导出。");
      }

      const sourceFile = initialSourceFile;
      const config =
        renderConfig?.input_props.sourceKind === "cut-proxy"
          ? renderConfig ?? (await getWebRenderConfig(jobId))
          : null;
      const sourceMeta = await resolveSourceRenderMeta(
        sourceFile,
        initialRenderMeta,
        {persistCache: config?.input_props.sourceKind !== "cut-proxy"},
      );
      const resolvedConfig =
        config ?? (await loadRenderConfigWithMeta(sourceFile, sourceMeta));

      if (resolvedConfig.input_props.sourceKind !== "cut-proxy") {
        const compatibility =
          await inspectRenderSourceCompatibility(initialSourceFile);
        setRenderSourceCompatibility(compatibility);
        const compatibilityError = getRenderSourceDirectExportErrorMessage(
          compatibility,
        );
        if (compatibilityError) {
          throw new Error(compatibilityError);
        }
      }

      sourceObjectUrl =
        resolvedConfig.input_props.sourceKind === "cut-proxy"
          ? null
          : URL.createObjectURL(sourceFile);
      const inputProps = {
        ...resolvedConfig.input_props,
        src: sourceObjectUrl || resolvedConfig.input_props.src,
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
          setRenderProgress((previous) =>
            Math.max(previous, clampPercent((doneFrames / totalFrames) * 100)),
          );
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

  useEffect(() => {
    if (renderBusy) {
      return;
    }
    setRenderProgress(0);
  }, [overlayControls, renderBusy, subtitleTheme]);

  const effectiveRenderSourceFile = renderSourceFile ?? selectedFile;
  const hasRenderSource = Boolean(effectiveRenderSourceFile || renderConfig?.input_props.sourceKind === "cut-proxy");
  const renderActionBusy = renderBusy;
  const canStartRender =
    hasRenderSource &&
    !busy &&
    !renderActionBusy &&
    (renderConfig?.input_props.sourceKind === "cut-proxy" ||
      (renderSourceCompatibility.status !== "checking" &&
        renderSourceCompatibility.status !== "blocked"));
  const renderPrimaryButtonLabel = "导出视频";

  return {
    state: {
      canStartRender,
      hasRenderSource,
      overlayControls,
      previewTimeSec,
      progressLabelModeOptions: PROGRESS_LABEL_MODE_OPTIONS,
      renderActionBusy,
      renderBusy,
      renderCompletionMarkerMessage,
      renderConfig,
      renderConfigBusy,
      renderDownloadUrl,
      renderFileName,
      renderNote,
      renderPreviewProfile,
      renderPrimaryButtonLabel,
      renderProgress,
      renderSetupError,
      renderSourceCompatibility,
      renderSourceFile: effectiveRenderSourceFile,
      selectedFile,
      supportedUploadAccept: SUPPORTED_UPLOAD_EXTENSIONS.join(","),
      subtitleTheme,
      subtitleThemeOptions: SUBTITLE_THEME_OPTIONS,
    },
    actions: {
      clearRenderMessage: () => setRenderCompletionMarkerMessage(""),
      handleSourceFileChange,
      handleStartRender,
      prepareRenderPreview,
      setOverlayControls,
      setSelectedFile,
      setSubtitleTheme,
    },
  };
}
