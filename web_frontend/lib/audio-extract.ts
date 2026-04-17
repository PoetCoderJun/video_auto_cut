import type { FFmpeg } from "@ffmpeg/ffmpeg";
import { fetchFile } from "@ffmpeg/util";

import { getBrowserFfmpeg, resetBrowserFfmpeg } from "./ffmpeg-browser";

const RESET_FFMPEG_AFTER_SOURCE_BYTES = 512 * 1024 * 1024;

export const LARGE_FILE_AUDIO_EXTRACT_BYTES = 512 * 1024 * 1024;

export type AudioExtractErrorCode =
  | "LARGE_FILE_RESOURCE_LIMIT"
  | "MP3_EXTRACT_FAILED"
  | "UNKNOWN";

export class AudioExtractError extends Error {
  code: AudioExtractErrorCode;
  causeMessage: string | null;
  fileSizeBytes: number;

  constructor(
    code: AudioExtractErrorCode,
    message: string,
    options: {
      causeMessage?: string | null;
      fileSizeBytes?: number;
    } = {}
  ) {
    super(message);
    this.name = "AudioExtractError";
    this.code = code;
    this.causeMessage = options.causeMessage ?? null;
    this.fileSizeBytes = options.fileSizeBytes ?? 0;
  }
}

function getFileExt(name: string): string {
  const idx = name.lastIndexOf(".");
  if (idx <= 0 || idx >= name.length - 1) return ".bin";
  return name.slice(idx).toLowerCase();
}

async function encodeMp3WithFfmpeg(
  sourceFile: File,
  sampleRate: number,
  kbps: number
): Promise<Blob> {
  const ffmpeg: FFmpeg = await getBrowserFfmpeg();
  const nonce = Math.random().toString(36).slice(2, 10);
  const inputName = `input_${nonce}${getFileExt(sourceFile.name)}`;
  const outputName = `output_${nonce}.mp3`;
  let shouldResetFfmpeg = sourceFile.size >= RESET_FFMPEG_AFTER_SOURCE_BYTES;

  try {
    await ffmpeg.writeFile(inputName, await fetchFile(sourceFile));
    const exitCode = await ffmpeg.exec([
      "-i",
      inputName,
      "-vn",
      "-ac",
      "1",
      "-ar",
      String(sampleRate),
      "-b:a",
      `${Math.max(16, Math.trunc(kbps))}k`,
      outputName,
    ]);
    if (exitCode !== 0) {
      throw new Error(`ffmpeg exited with code ${exitCode}`);
    }

    const data = await ffmpeg.readFile(outputName);
    if (!(data instanceof Uint8Array)) {
      throw new Error("ffmpeg output is not Uint8Array");
    }
    return new Blob([data], { type: "audio/mpeg" });
  } catch (error) {
    shouldResetFfmpeg = true;
    throw error;
  } finally {
    await Promise.allSettled([
      ffmpeg.deleteFile(inputName),
      ffmpeg.deleteFile(outputName),
    ]);
    if (shouldResetFfmpeg) {
      resetBrowserFfmpeg();
    }
  }
}

function getOutputName(sourceName: string): string {
  const idx = sourceName.lastIndexOf(".");
  const stem = idx > 0 ? sourceName.slice(0, idx) : sourceName;
  return `${stem || "audio"}.mp3`;
}

/**
 * Extract audio for ASR as MP3 in the browser before direct upload.
 */
export async function extractAudioForAsr(
  sourceFile: File,
  sampleRate = 16000
): Promise<File> {
  try {
    const mp3 = await encodeMp3WithFfmpeg(sourceFile, sampleRate, 64);
    return new File([mp3], getOutputName(sourceFile.name), {
      type: "audio/mpeg",
    });
  } catch (error) {
    if (error instanceof AudioExtractError) {
      throw error;
    }
    if (sourceFile.size >= LARGE_FILE_AUDIO_EXTRACT_BYTES) {
      throw new AudioExtractError(
        "LARGE_FILE_RESOURCE_LIMIT",
        "当前视频文件较大，浏览器在本地转 MP3 时资源不足。请先压缩视频或截短后再试。",
        {
          causeMessage: error instanceof Error ? error.message : null,
          fileSizeBytes: sourceFile.size,
        }
      );
    }
    throw new AudioExtractError(
      "MP3_EXTRACT_FAILED",
      "浏览器本地 MP3 提取失败。请刷新页面后重试；如果仍失败，请改用最新版 Chrome，或先转成 H.264/AAC 的 MP4 后再上传。",
      {
        causeMessage: error instanceof Error ? error.message : null,
        fileSizeBytes: sourceFile.size,
      }
    );
  }
}
