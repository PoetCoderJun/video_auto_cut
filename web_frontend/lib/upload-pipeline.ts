import {
  createJob,
  type ClientUploadIssueStage,
  type Job,
  uploadAudio,
} from "./api";
import { extractAudioForAsr } from "./audio-extract";
import { validateBrowserRenderCapability } from "./upload-render-validation";
import { prepareUploadSourceFile } from "./upload-source-preflight";
import { saveCachedJobSourceVideo } from "./video-cache";

export const MAX_VIDEO_DURATION_SEC = 10 * 60;

export class UploadPipelineError extends Error {
  stage: ClientUploadIssueStage;
  cause: unknown;

  constructor(stage: ClientUploadIssueStage, cause: unknown) {
    const message =
      cause instanceof Error ? cause.message : String(cause ?? "Upload failed");
    super(message);
    this.name = "UploadPipelineError";
    this.stage = stage;
    this.cause = cause;
  }
}

export function getVideoDurationLimitMessage(
  durationSec: number,
  maxDurationSec = MAX_VIDEO_DURATION_SEC,
): string {
  const mins = Math.floor(durationSec / 60);
  const secs = Math.round(durationSec % 60);
  const limitMinutes = Math.floor(maxDurationSec / 60);
  return `视频时长 ${mins} 分 ${secs} 秒，已达到 ${limitMinutes} 分钟限制，请上传更短的视频。`;
}

export async function readVideoDurationSec(file: File): Promise<number> {
  return new Promise<number>((resolve) => {
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
}

export async function runUploadPipeline(options: {
  file: File;
  onStageMessage?: (message: string) => void;
  onPreparedSource?: (file: File) => void;
}): Promise<{
  job: Job;
  uploadedJob: Job;
  preparedSourceFile: File;
}> {
  const { file, onStageMessage, onPreparedSource } = options;
  let stage: ClientUploadIssueStage = "source_preflight";

  try {
    onStageMessage?.("正在检查源视频兼容性...");
    const preparedSource = await prepareUploadSourceFile(file, {
      onStageChange: (nextStage) => {
        if (nextStage === "checking") {
          onStageMessage?.("正在检查源视频兼容性...");
          return;
        }
        onStageMessage?.("");
      },
    });

    onPreparedSource?.(preparedSource.file);

    stage = "render_validation";
    onStageMessage?.("正在校验浏览器导出能力...");
    await validateBrowserRenderCapability(preparedSource.file);

    stage = "job_create";
    const job = await createJob();

    stage = "audio_extract";
    onStageMessage?.("正在提取音频...");
    const audioFile = await extractAudioForAsr(preparedSource.file);

    stage = "audio_upload";
    onStageMessage?.("正在上传音频...");
    const uploadedJob = await uploadAudio(job.job_id, audioFile);

    stage = "source_cache";
    await saveCachedJobSourceVideo(job.job_id, preparedSource.file).catch(
      () => undefined,
    );

    return {
      job,
      uploadedJob,
      preparedSourceFile: preparedSource.file,
    };
  } catch (error) {
    throw new UploadPipelineError(stage, error);
  } finally {
    onStageMessage?.("");
  }
}
