"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiClientError,
  Chapter,
  createJob,
  Job,
  RenderMeta,
  Step1Line,
  confirmStep1,
  confirmStep2,
  getJob,
  getStep1,
  getStep2,
  getWebRenderConfigWithMeta,
  markRenderSucceeded,
  runStep1,
  runStep2,
  uploadAudioDirectToOss,
} from "../lib/api";
import { extractAudioForAsr } from "../lib/audio-extract";
import { isUnsupportedMobileUploadDevice } from "../lib/device";
import { tryParseFpsWithMediaInfo } from "../lib/media-metadata";
import {
  loadCachedJobSourceVideo,
  saveCachedJobSourceVideo,
} from "../lib/video-cache";
import {
  mergeJobSnapshot,
  mergeJobStatus,
  shouldPollJobStatus,
} from "../lib/job-status";
import { STATUS } from "../lib/workflow";
import {
  StitchVideoWeb,
  type SubtitleTheme,
} from "../lib/remotion/stitch-video-web";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  Loader2,
  UploadCloud,
  CheckCircle2,
  ArrowRight,
  Download,
  FileVideo,
  X,
} from "lucide-react";

function autoResize(target: HTMLTextAreaElement) {
  target.style.height = "auto";
  target.style.height = `${target.scrollHeight}px`;
}

const STEPS = [
  { id: 1, label: "上传视频" },
  { id: 2, label: "编辑字幕" },
  { id: 3, label: "导出视频" },
];

const SUPPORTED_UPLOAD_EXTENSIONS = [
  ".mp4",
  ".mov",
  ".mkv",
  ".webm",
  ".m4v",
  ".ts",
  ".m2ts",
  ".mts",
];
const SUPPORTED_UPLOAD_ACCEPT = SUPPORTED_UPLOAD_EXTENSIONS.join(",");
const SUBTITLE_THEME_OPTIONS: Array<{ value: SubtitleTheme; label: string }> = [
  { value: "box-white-on-black", label: "黑底白字" },
  { value: "box-black-on-white", label: "白底黑字" },
  { value: "text-white", label: "白色" },
  { value: "text-black", label: "黑色" },
];
const MAX_VIDEO_DURATION_SEC = 10 * 60;

function getActiveStep(status: Job["status"]): number {
  switch (status) {
    case STATUS.CREATED:
    case STATUS.UPLOAD_READY:
      return 1;
    case STATUS.STEP1_RUNNING:
    case STATUS.STEP1_READY:
      return 2;
    case STATUS.STEP1_CONFIRMED:
    case STATUS.STEP2_RUNNING:
    case STATUS.STEP2_READY:
    case STATUS.STEP2_CONFIRMED:
    case STATUS.SUCCEEDED:
      return 3;
    default:
      return 1;
  }
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function formatDuration(seconds: number): string {
  if (!seconds || Number.isNaN(seconds)) return "00:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

function getOriginalDurationFromLines(lines: Step1Line[]): number {
  return lines.reduce((max, line) => {
    const end = Number(line.end);
    if (!Number.isFinite(end) || end <= max) return max;
    return end;
  }, 0);
}

function getEstimatedDurationFromLines(lines: Step1Line[]): number {
  const intervals = lines
    .filter((line) => !line.user_final_remove)
    .filter((line) => String(line.optimized_text || "").trim().length > 0)
    .map((line) => ({
      start: Number(line.start),
      end: Number(line.end),
    }))
    .filter(
      (line) =>
        Number.isFinite(line.start) &&
        Number.isFinite(line.end) &&
        line.end > line.start
    )
    .sort((a, b) => a.start - b.start);

  if (intervals.length === 0) {
    return 0;
  }

  let total = 0;
  let currentStart = intervals[0].start;
  let currentEnd = intervals[0].end;

  for (let idx = 1; idx < intervals.length; idx += 1) {
    const item = intervals[idx];
    if (item.start <= currentEnd) {
      currentEnd = Math.max(currentEnd, item.end);
      continue;
    }
    total += currentEnd - currentStart;
    currentStart = item.start;
    currentEnd = item.end;
  }

  total += currentEnd - currentStart;
  return Math.max(0, total);
}

export default function JobWorkspace({
  jobId,
  onBackHome,
  onSwitchJob,
}: {
  jobId: string;
  onBackHome?: () => void;
  onSwitchJob?: (jobId: string) => void;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [lines, setLines] = useState<Step1Line[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [error, setError] = useState("");
  const [renderNote, setRenderNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [renderBusy, setRenderBusy] = useState(false);
  const [renderProgress, setRenderProgress] = useState(0);
  const [renderDownloadUrl, setRenderDownloadUrl] = useState<string | null>(
    null
  );
  const [renderFileName, setRenderFileName] = useState("output.mp4");
  const [subtitleTheme, setSubtitleTheme] = useState<SubtitleTheme>(
    "box-white-on-black"
  );
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadStageMessage, setUploadStageMessage] = useState("");
  const [autoStep1Triggered, setAutoStep1Triggered] = useState(false);
  const [autoStep2Triggered, setAutoStep2Triggered] = useState(false);
  const [autoStep2ConfirmTriggered, setAutoStep2ConfirmTriggered] = useState(false);
  const [autoRenderTriggered, setAutoRenderTriggered] = useState(false);
  const [mobileUploadBlocked, setMobileUploadBlocked] = useState(false);

  useEffect(() => {
    setMobileUploadBlocked(isUnsupportedMobileUploadDevice());
  }, []);

  const showMobileUploadError = useCallback(() => {
    setError("移动端暂不支持上传视频，请在电脑浏览器使用（建议 Chrome）。");
  }, []);

  const refreshJob = useCallback(async () => {
    try {
      const next = await getJob(jobId);
      setJob((previous) => mergeJobSnapshot(previous, next));
      return next;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      const isJobMissing =
        (err instanceof ApiClientError && err.code === "NOT_FOUND") ||
        message.includes("job not found");

      if (isJobMissing) {
        onBackHome?.();
      }
      throw err;
    }
  }, [jobId, onBackHome]);

  useEffect(() => {
    let active = true;
    refreshJob()
      .then(() => {
        if (!active) return;
        setError((prev) => (prev.startsWith("无法连接 API") ? "" : prev));
      })
      .catch((err) => {
        if (!active) return;
        const message = err instanceof Error ? err.message : String(err);
        if (
          (err instanceof ApiClientError && err.code === "NOT_FOUND") ||
          message.includes("job not found")
        ) {
          setError("项目不存在或已被清理，已返回首页。");
          return;
        }
        if (
          (err instanceof ApiClientError && err.code === "UNAUTHORIZED") ||
          message.includes("请先登录") ||
          message.includes("登录状态无效")
        ) {
          setError("登录状态已失效，请重新登录。");
          return;
        }
        setError(message.includes("无法连接 API") ? message : "无法连接 API，请确认后端服务正在运行。");
      });
    return () => {
      active = false;
    };
  }, [refreshJob]);

  useEffect(() => {
    if (!job) return;
    if (job.status === STATUS.STEP1_READY && lines.length === 0) {
      getStep1(jobId).then(setLines).catch(() => undefined);
    }
  }, [job, lines.length, jobId]);

  useEffect(() => {
    if (!job) return;
    if (job.status === STATUS.STEP2_READY) {
      if (chapters.length === 0) {
        getStep2(jobId).then(setChapters).catch(() => undefined);
      }
    }
  }, [job, chapters.length, jobId]);

  useEffect(() => {
    if (
      !job ||
      job.status !== STATUS.STEP2_READY ||
      chapters.length === 0 ||
      autoStep2ConfirmTriggered ||
      busy
    ) {
      return;
    }

    let cancelled = false;
    setAutoStep2ConfirmTriggered(true);
    setError("");
    setBusy(true);
    confirmStep2(jobId, chapters)
      .then((status) => {
        if (cancelled) return;
        setJob((previous) => mergeJobStatus(previous, status));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "自动确认章节失败，请重试。");
      })
      .finally(() => {
        if (!cancelled) {
          setBusy(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [job, chapters, autoStep2ConfirmTriggered, jobId, busy]);

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
    setAutoStep1Triggered(false);
    setAutoStep2Triggered(false);
    setAutoStep2ConfirmTriggered(false);
    setAutoRenderTriggered(false);
    setRenderDownloadUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return null;
    });
    setRenderFileName("output.mp4");
    setSubtitleTheme("box-white-on-black");
    setUploadStageMessage("");
  }, [jobId]);

  useEffect(() => {
    let active = true;
    loadCachedJobSourceVideo(jobId)
      .then((file) => {
        if (!active || !file) return;
        setSelectedFile((previous) => previous ?? file);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [jobId]);

  const handleUpload = useCallback(
    async (file: File) => {
      if (mobileUploadBlocked) {
        showMobileUploadError();
        return;
      }
      setError("");
      const lowerName = file.name.toLowerCase();
      const hasSupportedExt = SUPPORTED_UPLOAD_EXTENSIONS.some((ext) =>
        lowerName.endsWith(ext)
      );
      if (!hasSupportedExt) {
        setError(
          "这个文件格式暂不支持。请上传 MP4、MOV、MKV、WebM、M4V、TS、M2TS 或 MTS 视频。"
        );
        return;
      }
      const durationSec = await new Promise<number>((resolve) => {
        const url = URL.createObjectURL(file);
        const video = document.createElement("video");
        video.preload = "metadata";
        video.onloadedmetadata = () => {
          URL.revokeObjectURL(url);
          resolve(video.duration);
        };
        video.onerror = () => {
          URL.revokeObjectURL(url);
          resolve(0);
        };
        video.src = url;
      });
      if (durationSec >= MAX_VIDEO_DURATION_SEC) {
        const mins = Math.floor(durationSec / 60);
        const secs = Math.round(durationSec % 60);
        setError(
          `视频时长 ${mins} 分 ${secs} 秒，已达到 10 分钟限制，请上传更短的视频。`
        );
        return;
      }
      setBusy(true);
      try {
        setUploadStageMessage("正在提取音频...");
        const nextJob = await createJob();
        const audioFile = await extractAudioForAsr(file);
        setUploadStageMessage("正在上传音频...");
        const uploadedJob = await uploadAudioDirectToOss(nextJob.job_id, audioFile);
        await saveCachedJobSourceVideo(nextJob.job_id, file).catch(() => undefined);
        onSwitchJob?.(nextJob.job_id);
        setJob((previous) => mergeJobSnapshot(previous, uploadedJob));
      } catch (err) {
        setError(err instanceof Error ? err.message : "音频提取或上传失败，请重试。");
      } finally {
        setUploadStageMessage("");
        setBusy(false);
      }
    },
    [mobileUploadBlocked, onSwitchJob, showMobileUploadError]
  );

  useEffect(() => {
    if (
      !job ||
      job.status !== STATUS.UPLOAD_READY ||
      autoStep1Triggered ||
      busy
    )
      return;

    let cancelled = false;
    setAutoStep1Triggered(true);
    setError("");
    setBusy(true);
    runStep1(jobId)
      .then((step1Result) => {
        if (cancelled) return;
        setJob((previous) => mergeJobSnapshot(previous, step1Result.job));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "字幕提取失败，请重试。");
      })
      .finally(() => {
        setBusy(false);
      });

    return () => {
      cancelled = true;
    };
  }, [job, autoStep1Triggered, jobId, busy]);

  const handleRetryStep1AutoRun = useCallback(() => {
    if (!job || job.status !== STATUS.UPLOAD_READY || busy) return;
    setError("");
    setAutoStep1Triggered(false);
  }, [job, busy]);

  useEffect(() => {
    if (
      !job ||
      job.status !== STATUS.STEP1_CONFIRMED ||
      autoStep2Triggered ||
      busy
    )
      return;

    let cancelled = false;
    setAutoStep2Triggered(true);
    setError("");
    setBusy(true);
    runStep2(jobId)
      .then((step2Result) => {
        if (cancelled) return;
        setJob((previous) => mergeJobSnapshot(previous, step2Result.job));
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "章节生成失败，请重试。");
      })
      .finally(() => {
        setBusy(false);
      });

    return () => {
      cancelled = true;
    };
  }, [job, autoStep2Triggered, jobId, busy]);

  const handleRetryStep2AutoRun = useCallback(() => {
    if (!job || job.status !== STATUS.STEP1_CONFIRMED || busy) return;
    setError("");
    setAutoStep2Triggered(false);
  }, [job, busy]);

  const handleRetryStep2ConfirmAutoRun = useCallback(() => {
    if (!job || job.status !== STATUS.STEP2_READY || busy) return;
    setError("");
    setAutoStep2ConfirmTriggered(false);
  }, [job, busy]);

  useEffect(() => {
    if (!job) return;
    if (!shouldPollJobStatus(job.status)) return;

    const timer = setInterval(() => {
      refreshJob().catch(() => undefined);
    }, 2500);
    return () => {
      clearInterval(timer);
    };
  }, [job?.status, refreshJob]);

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (file) {
      if (mobileUploadBlocked) {
        showMobileUploadError();
        return;
      }
      setSelectedFile(file);
      void handleUpload(file);
    }
  };

  const handleConfirmStep1 = async () => {
    setError("");
    setBusy(true);
    try {
      const status = await confirmStep1(jobId, lines);
      setJob((previous) => mergeJobStatus(previous, status));
      const step2Result = await runStep2(jobId);
      setJob((previous) => mergeJobSnapshot(previous, step2Result.job));
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败，请重试。");
    } finally {
      setBusy(false);
    }
  };

  const handleStartRender = useCallback(async () => {
    setError("");
    setRenderNote("");
    setRenderBusy(true);
    setRenderProgress(0);
    setRenderDownloadUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return null;
    });
    let sourceObjectUrl: string | null = null;
    try {
      const resolveMetaFromFile = async (file: File): Promise<RenderMeta> => {
        const url = URL.createObjectURL(file);
        try {
          const meta = await new Promise<{
            width: number;
            height: number;
            duration: number;
          }>((resolve, reject) => {
            const video = document.createElement("video");
            video.preload = "metadata";
            video.muted = true;
            video.onloadedmetadata = () => {
              resolve({
                width: video.videoWidth,
                height: video.videoHeight,
                duration: video.duration,
              });
            };
            video.onerror = () =>
              reject(new Error("无法读取本地视频元数据，请重新选择文件。"));
            video.src = url;
          });

          const estimateFps = async (): Promise<number> => {
            // Best-effort estimation using requestVideoFrameCallback.
            // This avoids pulling in heavy parsers (mp4box/mediainfo) and works offline.
            const probeUrl = URL.createObjectURL(file);
            const video = document.createElement("video");
            video.muted = true;
            video.playsInline = true;
            video.preload = "auto";
            video.src = probeUrl;

            try {
              await video.play();
            } catch {
              // If autoplay is blocked or decoding fails, fallback.
              URL.revokeObjectURL(probeUrl);
              return 30;
            }

            return await new Promise<number>((resolve) => {
              let firstMediaTime: number | null = null;
              let lastMediaTime: number | null = null;
              let frames = 0;
              const maxFrames = 45;
              const maxMs = 1200;
              const startAt = performance.now();

              const finish = () => {
                try {
                  video.pause();
                } catch {
                  // ignore
                }
                URL.revokeObjectURL(probeUrl);
                const dt =
                  firstMediaTime !== null && lastMediaTime !== null
                    ? lastMediaTime - firstMediaTime
                    : 0;
                const fps = dt > 0 ? frames / dt : 0;
                if (Number.isFinite(fps) && fps > 1 && fps < 240) {
                  resolve(Math.round(fps * 1000) / 1000);
                } else {
                  resolve(30);
                }
              };

              const onFrame = (_now: number, frame: { mediaTime: number }) => {
                const t = typeof frame?.mediaTime === "number" ? frame.mediaTime : NaN;
                if (Number.isFinite(t)) {
                  if (firstMediaTime === null) firstMediaTime = t;
                  lastMediaTime = t;
                  frames += 1;
                }

                if (
                  frames >= maxFrames ||
                  performance.now() - startAt >= maxMs
                ) {
                  finish();
                  return;
                }
                const requestCb = (video as any).requestVideoFrameCallback;
                if (typeof requestCb === "function") requestCb.call(video, onFrame);
                else finish();
              };

              const requestCb = (video as any).requestVideoFrameCallback;
              if (typeof requestCb === "function") requestCb.call(video, onFrame);
              else finish();
            });
          };

          const fps = (await tryParseFpsWithMediaInfo(file)) ?? (await estimateFps());
          return {
            width: meta.width,
            height: meta.height,
            duration_sec:
              typeof meta.duration === "number" && Number.isFinite(meta.duration)
                ? meta.duration
                : undefined,
            fps,
          };
        } finally {
          URL.revokeObjectURL(url);
        }
      };

      let config;
      let sourceFile = selectedFile;
      if (!sourceFile) {
        sourceFile = await loadCachedJobSourceVideo(jobId);
        if (sourceFile) setSelectedFile(sourceFile);
      }
      if (!sourceFile) {
        throw new Error("当前会话缺少本地原始视频，请先重新上传后再导出。");
      }
      const meta = await resolveMetaFromFile(sourceFile);
      config = await getWebRenderConfigWithMeta(jobId, meta);
      sourceObjectUrl = URL.createObjectURL(sourceFile);
      const inputProps = {
        ...config.input_props,
        src: sourceObjectUrl,
        subtitleTheme,
      };
      const composition = {
        ...config.composition,
        component: StitchVideoWeb,
        defaultProps: inputProps,
      };

      if (!window.isSecureContext) {
        throw new Error(
          "当前页面不在安全上下文中（需要 HTTPS 或 localhost），浏览器禁用了视频解码器 (VideoDecoder)，无法导出视频。请通过 HTTPS 访问本站，或联系管理员配置 SSL 证书。"
        );
      }

      const { renderMediaOnWeb, getEncodableAudioCodecs } = await import("@remotion/web-renderer");

      // Determine the best available container+codec for this browser.
      // On non-cross-origin-isolated pages (missing COOP/COEP headers), audio
      // encoders are restricted by the browser. We probe MP4 first, then WebM,
      // and as a last resort render muted (no audio) inside MP4 so the export
      // never hard-crashes.
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
        // Neither container can encode audio — render muted and warn the user.
        // The proper fix is to deploy COOP/COEP response headers so the page
        // becomes cross-origin isolated (window.crossOriginIsolated === true).
        container = "mp4";
        videoCodec = "h264";
        muted = true;
      }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const renderOptions: Parameters<typeof renderMediaOnWeb>[0] = {
        composition: composition as any,
        inputProps,
        container,
        videoCodec,
        videoBitrate: "high",
        ...(muted ? { muted: true } : {}),
        onProgress: (progress) => {
          const totalFrames = Math.max(
            1,
            Number(config.composition.durationInFrames) || 1
          );
          const doneFrames =
            typeof progress.encodedFrames === "number" &&
            Number.isFinite(progress.encodedFrames)
              ? progress.encodedFrames
              : progress.renderedFrames;
          setRenderProgress((previous) =>
            Math.max(previous, clampPercent((doneFrames / totalFrames) * 100))
          );
        },
      };

      // Try the probed container first; if rendering itself reports no audio
      // codec (browser capability detection can lag behind actual support),
      // retry once with muted=true so the user always gets a file.
      let result: Awaited<ReturnType<typeof renderMediaOnWeb>>;
      try {
        result = await renderMediaOnWeb(renderOptions);
      } catch (renderErr) {
        const msg = renderErr instanceof Error ? renderErr.message : String(renderErr);
        if (msg.includes("No audio codec can be encoded")) {
          result = await renderMediaOnWeb({ ...renderOptions, muted: true });
          muted = true;
        } else {
          throw renderErr;
        }
      }

      const baseName = (config.output_name || "output").replace(/\.(mp4|webm)$/i, "");
      const outputName = `${baseName}.${container}`;
      if (muted) {
        setRenderNote("导出成功，但当前浏览器环境不支持音频编码，导出文件无声音。建议使用 Chrome / Edge 浏览器，或联系管理员确认服务器已配置 COOP/COEP 响应头。");
      }
      setRenderFileName(outputName);
      const blob = await result.getBlob();
      const objectUrl = URL.createObjectURL(blob);
      setRenderDownloadUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return objectUrl;
      });
      // Try auto-download after export; keep the manual button as fallback.
      const autoDownloadLink = document.createElement("a");
      autoDownloadLink.href = objectUrl;
      autoDownloadLink.download = outputName;
      autoDownloadLink.style.display = "none";
      document.body.appendChild(autoDownloadLink);
      autoDownloadLink.click();
      document.body.removeChild(autoDownloadLink);
      setRenderProgress(100);
      try {
        const completion = await markRenderSucceeded(jobId);
        setJob((previous) => mergeJobSnapshot(previous, completion.job));
      } catch (syncErr) {
        const message =
          syncErr instanceof Error ? syncErr.message : "服务端确认失败，请刷新后重试。";
        setError(`视频已导出，但服务端确认失败：${message}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "浏览器导出失败，请重试。");
    } finally {
      if (sourceObjectUrl) {
        URL.revokeObjectURL(sourceObjectUrl);
      }
      setRenderBusy(false);
    }
  }, [jobId, selectedFile, subtitleTheme]);

  useEffect(() => {
    if (
      !job ||
      job.status !== STATUS.STEP2_CONFIRMED ||
      autoRenderTriggered ||
      renderBusy ||
      renderDownloadUrl
    ) {
      return;
    }

    setAutoRenderTriggered(true);
    void handleStartRender();
  }, [
    autoRenderTriggered,
    handleStartRender,
    job,
    renderBusy,
    renderDownloadUrl,
  ]);

  useEffect(() => {
    if (renderBusy) return;
    setRenderDownloadUrl((previous) => {
      if (!previous) return previous;
      URL.revokeObjectURL(previous);
      return null;
    });
    setRenderProgress(0);
  }, [subtitleTheme]);

  const updateLine = (lineId: number, patch: Partial<Step1Line>) => {
    setLines((prev) =>
      prev.map((line) => (line.line_id === lineId ? { ...line, ...patch } : line))
    );
  };

  const { originalDuration, estimatedDuration } = useMemo(() => {
    return {
      originalDuration: getOriginalDurationFromLines(lines),
      estimatedDuration: getEstimatedDurationFromLines(lines),
    };
  }, [lines]);

  if (!job) {
    return (
      <main className="container mx-auto flex h-[50vh] flex-col items-center justify-center gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-muted-foreground">正在加载项目数据...</p>
      </main>
    );
  }

  const activeStep = getActiveStep(job.status);
  return (
    <main className="container mx-auto animate-in fade-in zoom-in-95 duration-500 max-w-4xl px-4 py-8">
      {/* Stepper */}
      <div className="mb-12 border-b pb-8">
        <div className="flex flex-wrap items-center justify-center gap-4 md:justify-between">
          <div className="flex flex-wrap items-center gap-2 md:gap-4">
            {STEPS.map((step, idx) => {
              const isCompleted =
                step.id < activeStep ||
                (step.id === 3 && job.status === STATUS.SUCCEEDED);
              const isActive =
                step.id === activeStep && job.status !== STATUS.SUCCEEDED;
              return (
                <div key={step.id} className="flex items-center gap-2 md:gap-4">
                  <div
                    className={cn(
                      "flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-primary text-primary-foreground"
                        : isCompleted
                        ? "bg-muted text-foreground"
                        : "text-muted-foreground opacity-50"
                    )}
                  >
                    <div
                      className={cn(
                        "flex h-5 w-5 items-center justify-center rounded-full border text-[10px]",
                        isActive
                          ? "border-primary-foreground"
                          : "border-current"
                      )}
                    >
                      {isCompleted ? <CheckCircle2 className="h-3 w-3" /> : step.id}
                    </div>
                    <span className="hidden sm:inline">{step.label}</span>
                  </div>
                  {idx < STEPS.length - 1 && (
                    <div className="text-muted-foreground/30">›</div>
                  )}
                </div>
              );
            })}
          </div>
          {onBackHome && (
            <Button type="button" variant="ghost" size="sm" onClick={onBackHome}>
              重新上传
            </Button>
          )}
        </div>
      </div>

      {(job.error || error) && (
        <div className="mb-6 rounded-md bg-destructive/10 p-4 text-sm font-medium text-destructive border border-destructive/20">
          {job.error?.message || error}
        </div>
      )}

      {renderNote && (
        <div className="mb-6 rounded-md bg-amber-50 p-4 text-sm font-medium text-amber-800 border border-amber-200">
          {renderNote}
        </div>
      )}

      {/* Step 1: Upload */}
      {job.status === STATUS.CREATED && (
        <Card className="mx-auto max-w-xl text-center">
          <CardHeader>
            <CardTitle>上传原始视频</CardTitle>
            <CardDescription>
              请选择您要剪辑的视频文件。支持 MP4, MOV, MKV 等格式。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div
              onClick={() => {
                if (mobileUploadBlocked) showMobileUploadError();
              }}
              className={cn(
                "relative group w-full rounded-xl border-2 border-dashed border-muted-foreground/25 bg-muted/50 p-10 transition-all hover:border-primary/50 hover:bg-muted",
                selectedFile && "border-primary bg-primary/5",
                busy || mobileUploadBlocked
                  ? "opacity-70 cursor-not-allowed"
                  : "cursor-pointer"
              )}
            >
              <input
                type="file"
                accept={SUPPORTED_UPLOAD_ACCEPT}
                onChange={onFileChange}
                disabled={busy || mobileUploadBlocked}
                className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
              />
              <div className="flex flex-col items-center justify-center gap-4">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-background shadow-sm">
                  {busy ? (
                    <Loader2 className="h-8 w-8 animate-spin text-primary" />
                  ) : (
                    <UploadCloud className="h-8 w-8 text-primary" />
                  )}
                </div>
                <div className="space-y-1">
                  <h3 className="font-semibold text-lg text-foreground">
                    {busy
                      ? uploadStageMessage || "正在上传..."
                      : mobileUploadBlocked
                      ? "移动端暂不支持上传"
                      : selectedFile
                      ? selectedFile.name
                      : "点击或拖拽上传视频"}
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    {mobileUploadBlocked
                      ? "请在电脑浏览器使用，建议 Chrome"
                      : busy
                      ? "请保持页面开启，我们会自动继续处理。"
                      : "AI 将自动提取字幕并进行智能分析"}
                  </p>
                </div>
              </div>
            </div>
            {mobileUploadBlocked && (
              <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm font-medium text-amber-800">
                移动端暂不支持上传视频，请在电脑浏览器使用（建议 Chrome）。
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Loading States */}
      {(job.status === STATUS.UPLOAD_READY ||
        job.status === STATUS.STEP1_RUNNING) && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Loader2 className="mb-4 h-12 w-12 animate-spin text-primary" />
          <h2 className="text-xl font-semibold">
            {job.stage?.message || "正在提取字幕"}
          </h2>
          <p className="text-muted-foreground">
            {job.stage?.code === "OPTIMIZING_TEXT"
              ? "AI 正在优化字幕文本，请稍候..."
              : "AI 正在解析视频语音，这可能需要几分钟..."}
          </p>
          {job.status === STATUS.UPLOAD_READY && !busy && autoStep1Triggered && (
            <Button
              type="button"
              variant="outline"
              className="mt-4"
              onClick={handleRetryStep1AutoRun}
            >
              重新尝试启动字幕任务
            </Button>
          )}
        </div>
      )}

      {(job.status === STATUS.STEP1_CONFIRMED ||
        job.status === STATUS.STEP2_RUNNING ||
        job.status === STATUS.STEP2_READY) && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Loader2 className="mb-4 h-12 w-12 animate-spin text-primary" />
          <h2 className="text-xl font-semibold">
            {job.stage?.message ||
              (job.status === STATUS.STEP2_READY ? "正在准备导出" : "正在生成章节")}
          </h2>
          <p className="text-muted-foreground">
            {job.status === STATUS.STEP2_READY
              ? "章节处理已完成，正在切换到导出阶段..."
              : "系统会自动采用 AI 章节结果，并直接进入导出步骤。"}
          </p>
          {job.status === STATUS.STEP1_CONFIRMED && !busy && autoStep2Triggered && (
            <Button
              type="button"
              variant="outline"
              className="mt-4"
              onClick={handleRetryStep2AutoRun}
            >
              重新尝试启动章节任务
            </Button>
          )}
          {job.status === STATUS.STEP2_READY && !busy && autoStep2ConfirmTriggered && (
            <Button
              type="button"
              variant="outline"
              className="mt-4"
              onClick={handleRetryStep2ConfirmAutoRun}
            >
              重新尝试进入导出
            </Button>
          )}
        </div>
      )}

      {/* Step 2: Edit Subtitles */}
      {job.status === STATUS.STEP1_READY && (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold tracking-tight">用字幕编辑视频</h2>
              <p className="text-muted-foreground">
                直接修改字幕，点击句尾“×”可剔除该句。
              </p>
            </div>
            <div className="hidden md:block">
              <Badge variant="outline" className="text-sm">
                共 {lines.length} 行字幕
              </Badge>
            </div>
          </div>

          <div className="relative min-h-[500px] w-full rounded-md bg-white border border-[#e2e8f0] shadow-sm py-12 px-8 md:px-16 overflow-hidden mt-6">
            <div className="max-w-3xl mx-auto flex flex-col gap-[6px]">
              {lines.map((line) => {
                const isRemoved = line.user_final_remove;
                const isNoSpeech = !line.optimized_text || line.optimized_text.trim() === "";
                const lineTime = formatDuration(Number(line.start) || 0);
                
                return (
                  <div 
                    key={line.line_id} 
                    className="group relative flex items-start gap-3"
                  >
                    <span className="mt-[2px] select-none font-mono text-[12px] leading-[1.7] text-[#94a3b8]">
                      {lineTime}
                    </span>
                    <div className="flex-1 min-w-0">
                      {isRemoved ? (
                        <div
                          className="text-[12px] text-[#94a3b8] line-through cursor-pointer select-none py-[2px]"
                          onClick={() => updateLine(line.line_id, { user_final_remove: false })}
                          title="点击恢复此行"
                        >
                          {isNoSpeech ? "<No Speech>" : line.optimized_text}
                        </div>
                      ) : (
                        <Textarea
                          value={line.optimized_text}
                          onChange={(e) =>
                            updateLine(line.line_id, {
                              optimized_text: e.target.value,
                            })
                          }
                          rows={1}
                          onInput={(e) =>
                            autoResize(e.target as HTMLTextAreaElement)
                          }
                          ref={(el) => {
                            if (el) autoResize(el);
                          }}
                          className="min-h-0 block w-full resize-none border-0 bg-transparent p-0 text-[15px] text-[#334155] leading-[1.7] shadow-none focus-visible:ring-0 rounded-none m-0 overflow-hidden placeholder:text-[#cbd5e1]"
                          placeholder={isNoSpeech ? "<No Speech>" : ""}
                        />
                      )}
                    </div>
                    {!isRemoved && (
                      <div
                        className="opacity-0 group-hover:opacity-100 shrink-0 ml-2 text-[#cbd5e1] hover:text-[#ef4444] cursor-pointer flex items-center h-6 px-1 transition-opacity"
                        onClick={() => updateLine(line.line_id, { user_final_remove: true })}
                        title="剔除此行"
                      >
                        <X className="h-4 w-4" />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="sticky bottom-6 z-10 mx-auto max-w-2xl">
            <Card className="border-t-4 border-t-primary shadow-xl">
              <CardContent className="flex items-center justify-between p-6">
                <div className="flex items-center gap-8">
                  <div>
                    <div className="text-sm font-medium text-muted-foreground">
                      原始时长
                    </div>
                    <div className="text-2xl font-bold font-mono">
                      {formatDuration(originalDuration)}
                    </div>
                  </div>
                  <ArrowRight className="h-6 w-6 text-muted-foreground/50" />
                  <div>
                    <div className="text-sm font-medium text-muted-foreground">
                      预计时长
                    </div>
                    <div className="text-2xl font-bold font-mono text-emerald-600">
                      {formatDuration(estimatedDuration)}
                    </div>
                  </div>
                </div>
                <Button
                  size="lg"
                  onClick={handleConfirmStep1}
                  disabled={lines.length === 0 || busy}
                >
                  {busy ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      正在保存...
                    </>
                  ) : (
                    "确认无误，开始导出准备"
                  )}
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      )}

      {/* Step 3: Export */}
      {(job.status === STATUS.STEP2_CONFIRMED || job.status === STATUS.SUCCEEDED) && (
        <div className="mx-auto max-w-lg text-center animate-in fade-in slide-in-from-bottom-4 duration-500 space-y-8">
          <div>
            <h2 className="text-2xl font-bold tracking-tight mb-2">导出视频</h2>
            <p className="text-muted-foreground">
              系统会自动开始导出，您也可以调整字幕样式后重新导出。
            </p>
          </div>

          <Card>
            <CardHeader className="text-left">
              <CardTitle className="text-base">导出设置</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between gap-4">
                <label className="text-sm font-medium">字幕样式</label>
                <Select
                  value={subtitleTheme}
                  onValueChange={(v) => setSubtitleTheme(v as SubtitleTheme)}
                  disabled={renderBusy}
                >
                  <SelectTrigger className="w-[180px]">
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

              <div className="rounded-md bg-amber-50 p-3 text-left text-xs text-amber-800 border border-amber-200">
                <p>• 优先使用 Chrome 浏览器导出。</p>
                <p>• 导出期间请保持当前页面前台运行。</p>
              </div>

              {renderBusy && (
                <div className="space-y-2">
                  <div className="flex justify-between text-xs text-muted-foreground">
                    <span>导出进度</span>
                    <span>{Math.round(renderProgress)}%</span>
                  </div>
                  <Progress value={renderProgress} className="h-2" />
                  <p className="text-xs text-muted-foreground animate-pulse">
                    正在处理视频，请勿关闭页面...
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="flex flex-col gap-3">
            {!renderBusy && (
              <Button
                size="lg"
                className="w-full"
                onClick={() => void handleStartRender()}
                disabled={busy}
              >
                {renderDownloadUrl ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4" /> 重新导出
                  </>
                ) : (
                  <>
                    <FileVideo className="mr-2 h-4 w-4" /> 开始导出
                  </>
                )}
              </Button>
            )}

            {!renderBusy && renderDownloadUrl && (
              <a
                href={renderDownloadUrl}
                download={renderFileName}
                className="w-full"
              >
                <Button variant="secondary" size="lg" className="w-full">
                  <Download className="mr-2 h-4 w-4" /> 下载视频成品
                </Button>
              </a>
            )}
          </div>
        </div>
      )}

    </main>
  );
}
