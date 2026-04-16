"use client";

import {useCallback, useEffect, useRef, useState, type ChangeEvent} from "react";

import {
  ApiClientError,
  type ClientUploadIssueStage,
  type Job,
  getJob,
  reportClientUploadIssue,
  runTest,
} from "../../lib/api";
import {
  isUnsupportedLocalVideoBrowser,
  isUnsupportedMobileUploadDevice,
} from "../../lib/device";
import {mergeJobSnapshot, shouldPollJobStatus} from "../../lib/job-status";
import {getFriendlyUploadErrorMessage} from "../../lib/upload-error";
import {
  getVideoDurationLimitMessage,
  MAX_VIDEO_DURATION_SEC,
  readVideoDurationSec,
  runUploadPipeline,
  UploadPipelineError,
} from "../../lib/upload-pipeline";
import {STATUS} from "../../lib/workflow";

import {
  JOB_LOAD_RETRY_DELAY_MS,
  SUPPORTED_UPLOAD_EXTENSIONS,
} from "./constants";

export function useJobLifecycle({
  jobId,
  onBackHome,
  onPreparedSource,
  onSwitchJob,
}: {
  jobId: string;
  onBackHome?: () => void;
  onPreparedSource: (file: File | null) => void;
  onSwitchJob?: (jobId: string) => void;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [jobLoadError, setJobLoadError] = useState("");
  const [isLoadingJob, setIsLoadingJob] = useState(true);
  const [busy, setBusy] = useState(false);
  const [uploadStageMessage, setUploadStageMessage] = useState("");
  const [autoTestTriggered, setAutoTestTriggered] = useState(false);
  const [mobileUploadBlocked, setMobileUploadBlocked] = useState(false);
  const isMountedRef = useRef(true);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    setMobileUploadBlocked(
      isUnsupportedMobileUploadDevice() || isUnsupportedLocalVideoBrowser(),
    );
  }, []);

  const showMobileUploadError = useCallback(() => {
    setError("当前浏览器暂不支持上传视频，请使用桌面版 Chrome。");
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

  const loadJob = useCallback(
    async (options: {background?: boolean} = {}) => {
      const isBackground = Boolean(options.background);
      if (!isBackground && isMountedRef.current) {
        setIsLoadingJob(true);
        setJobLoadError("");
      }

      try {
        const next = await refreshJob();
        if (isMountedRef.current) {
          setJobLoadError("");
          setError((previous) =>
            previous.includes("正在重试") || previous.includes("无法连接 API")
              ? ""
              : previous,
          );
        }
        return next;
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        if (isBackground) {
          if (isMountedRef.current) {
            setError(
              message.includes("无法连接 API")
                ? `${message}，正在重试。`
                : `项目状态刷新失败：${message}，正在重试。`,
            );
          }
          return;
        }

        const isJobMissing =
          (err instanceof ApiClientError && err.code === "NOT_FOUND") ||
          message.includes("job not found");
        if (isJobMissing) {
          if (isMountedRef.current) {
            setJobLoadError("项目不存在或已被清理，已返回首页。");
          }
          return;
        }

        const isUnauthorized =
          (err instanceof ApiClientError && err.code === "UNAUTHORIZED") ||
          message.includes("请先登录") ||
          message.includes("登录状态无效");
        if (isUnauthorized) {
          if (isMountedRef.current) {
            setJobLoadError("登录状态已失效，请重新登录。");
          }
          return;
        }

        if (isMountedRef.current) {
          setJobLoadError(
            message.includes("无法连接 API")
              ? message
              : "无法连接 API，请确认后端服务正在运行。",
          );
        }
      } finally {
        if (!isBackground && isMountedRef.current) {
          setIsLoadingJob(false);
        }
      }
    },
    [refreshJob],
  );

  const handleRetryLoadJob = useCallback(() => {
    void loadJob();
  }, [loadJob]);

  useEffect(() => {
    void loadJob();
  }, [loadJob]);

  useEffect(() => {
    if (job || !jobLoadError || isLoadingJob) {
      return;
    }

    const timer = window.setTimeout(() => {
      if (isMountedRef.current) {
        void loadJob();
      }
    }, JOB_LOAD_RETRY_DELAY_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [isLoadingJob, job, jobLoadError, loadJob]);

  useEffect(() => {
    setJob(null);
    setError("");
    setJobLoadError("");
    setIsLoadingJob(true);
    setBusy(false);
    setUploadStageMessage("");
    setAutoTestTriggered(false);
    onPreparedSource(null);
  }, [jobId, onPreparedSource]);

  const handleUpload = useCallback(
    async (file: File) => {
      if (mobileUploadBlocked) {
        showMobileUploadError();
        return;
      }

      setError("");
      const lowerName = file.name.toLowerCase();
      const hasSupportedExt = SUPPORTED_UPLOAD_EXTENSIONS.some((ext) =>
        lowerName.endsWith(ext),
      );
      if (!hasSupportedExt) {
        setError(
          "这个文件格式暂不支持。请上传 MP4、MOV、MKV、WebM、M4V、TS、M2TS 或 MTS 视频。",
        );
        return;
      }

      const durationSec = await readVideoDurationSec(file);
      if (durationSec >= MAX_VIDEO_DURATION_SEC) {
        setError(getVideoDurationLimitMessage(durationSec));
        return;
      }

      setBusy(true);
      let uploadStage: ClientUploadIssueStage = "source_preflight";
      try {
        const {job: nextJob, uploadedJob} = await runUploadPipeline({
          file,
          onStageMessage: setUploadStageMessage,
          onPreparedSource: (sourceFile) => onPreparedSource(sourceFile),
        });
        onSwitchJob?.(nextJob.job_id);
        setJob((previous) => mergeJobSnapshot(previous, uploadedJob));
      } catch (err) {
        if (err instanceof UploadPipelineError) {
          uploadStage = err.stage;
        }
        const friendlyMessage = getFriendlyUploadErrorMessage(err);
        void reportClientUploadIssue({
          stage: uploadStage,
          page: "/",
          file_name: file.name,
          file_type: file.type,
          file_size_bytes: file.size,
          error_name: err instanceof Error ? err.name : typeof err,
          error_message: err instanceof Error ? err.message : String(err ?? ""),
          friendly_message: friendlyMessage,
          user_agent:
            typeof navigator !== "undefined" ? navigator.userAgent : "",
        }).catch(() => undefined);
        setError(friendlyMessage);
      } finally {
        setUploadStageMessage("");
        setBusy(false);
      }
    },
    [mobileUploadBlocked, onPreparedSource, onSwitchJob, showMobileUploadError],
  );

  const handleUploadFileChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const input = event.currentTarget;
      const file = input.files?.[0];
      input.value = "";
      if (!file) {
        return;
      }
      if (mobileUploadBlocked) {
        showMobileUploadError();
        return;
      }
      void handleUpload(file);
    },
    [handleUpload, mobileUploadBlocked, showMobileUploadError],
  );

  useEffect(() => {
    if (
      !job ||
      job.status !== STATUS.UPLOAD_READY ||
      autoTestTriggered ||
      busy
    ) {
      return;
    }

    let cancelled = false;
    setAutoTestTriggered(true);
    setError("");
    setBusy(true);
    runTest(jobId)
      .then((testResult) => {
        if (cancelled) {
          return;
        }
        setJob((previous) => mergeJobSnapshot(previous, testResult.job));
      })
      .catch((err) => {
        if (cancelled) {
          return;
        }
        setError(err instanceof Error ? err.message : "字幕提取失败，请重试。");
      })
      .finally(() => {
        setBusy(false);
      });

    return () => {
      cancelled = true;
    };
  }, [job, autoTestTriggered, jobId, busy]);

  const handleRetryTestAutoRun = useCallback(() => {
    if (!job || job.status !== STATUS.UPLOAD_READY || busy) {
      return;
    }
    setError("");
    setAutoTestTriggered(false);
  }, [busy, job]);

  useEffect(() => {
    if (!job || !shouldPollJobStatus(job.status)) {
      return;
    }

    const timer = window.setInterval(() => {
      void loadJob({background: true}).catch(() => undefined);
    }, 2500);
    return () => {
      window.clearInterval(timer);
    };
  }, [job?.status, loadJob]);

  return {
    state: {
      autoTestTriggered,
      busy,
      error,
      isLoadingJob,
      job,
      jobLoadError,
      mobileUploadBlocked,
      uploadStageMessage,
    },
    actions: {
      handleRetryLoadJob,
      handleRetryTestAutoRun,
      handleUpload,
      handleUploadFileChange,
      setBusy,
      setError,
      setJob,
      showMobileUploadError,
    },
  };
}
