import type { FFmpeg } from "@ffmpeg/ffmpeg";
import { fetchFile } from "@ffmpeg/util";

import { getBrowserFfmpeg, resetBrowserFfmpeg } from "./ffmpeg-browser";

const RESET_FFMPEG_AFTER_SOURCE_BYTES = 512 * 1024 * 1024;

export const LARGE_FILE_AUDIO_EXTRACT_BYTES = 512 * 1024 * 1024;

export type AudioExtractErrorCode =
  | "AUDIO_CONTEXT_UNSUPPORTED"
  | "LARGE_FILE_RESOURCE_LIMIT"
  | "AUDIO_DECODE_FAILED"
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

function toMonoChannelData(decoded: AudioBuffer): Float32Array {
  const channels = decoded.numberOfChannels;
  if (channels <= 1) {
    return new Float32Array(decoded.getChannelData(0));
  }
  const length = decoded.length;
  const mono = new Float32Array(length);
  for (let channel = 0; channel < channels; channel += 1) {
    const src = decoded.getChannelData(channel);
    for (let i = 0; i < length; i += 1) {
      mono[i] += src[i];
    }
  }
  const inv = 1 / channels;
  for (let i = 0; i < length; i += 1) {
    mono[i] *= inv;
  }
  return mono;
}

function resampleLinear(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (!Number.isFinite(fromRate) || !Number.isFinite(toRate) || fromRate <= 0 || toRate <= 0) {
    return input;
  }
  if (Math.round(fromRate) === Math.round(toRate)) {
    return input;
  }
  const ratio = fromRate / toRate;
  const outLength = Math.max(1, Math.round(input.length / ratio));
  const out = new Float32Array(outLength);
  for (let i = 0; i < outLength; i += 1) {
    const pos = i * ratio;
    const left = Math.floor(pos);
    const right = Math.min(left + 1, input.length - 1);
    const weight = pos - left;
    const l = input[left] ?? 0;
    const r = input[right] ?? l;
    out[i] = l + (r - l) * weight;
  }
  return out;
}

function encodeWavPcm16Mono(samples: Float32Array, sampleRate: number): Blob {
  const bytesPerSample = 2;
  const dataSize = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  let offset = 0;
  const writeString = (value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset, value.charCodeAt(i));
      offset += 1;
    }
  };

  writeString("RIFF");
  view.setUint32(offset, 36 + dataSize, true);
  offset += 4;
  writeString("WAVE");
  writeString("fmt ");
  view.setUint32(offset, 16, true);
  offset += 4;
  view.setUint16(offset, 1, true);
  offset += 2;
  view.setUint16(offset, 1, true);
  offset += 2;
  view.setUint32(offset, sampleRate, true);
  offset += 4;
  view.setUint32(offset, sampleRate * bytesPerSample, true);
  offset += 4;
  view.setUint16(offset, bytesPerSample, true);
  offset += 2;
  view.setUint16(offset, 16, true);
  offset += 2;
  writeString("data");
  view.setUint32(offset, dataSize, true);
  offset += 4;

  for (let i = 0; i < samples.length; i += 1) {
    const value = Math.max(-1, Math.min(1, samples[i] ?? 0));
    view.setInt16(offset, value < 0 ? value * 0x8000 : value * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

function getOutputName(sourceName: string, ext: "wav" | "mp3"): string {
  const idx = sourceName.lastIndexOf(".");
  const stem = idx > 0 ? sourceName.slice(0, idx) : sourceName;
  return `${stem || "audio"}.${ext}`;
}

export type ExtractAudioFormat = "wav" | "mp3";

/**
 * Extract audio for ASR.
 * MP3 path uses ffmpeg.wasm directly from source media. Fallback is WAV.
 */
export async function extractAudioForAsr(
  sourceFile: File,
  sampleRate = 16000,
  format: ExtractAudioFormat = "mp3"
): Promise<File> {
  let mp3ExtractError: unknown = null;
  try {
    if (format === "mp3") {
      try {
        const mp3 = await encodeMp3WithFfmpeg(sourceFile, sampleRate, 64);
        return new File([mp3], getOutputName(sourceFile.name, "mp3"), {
          type: "audio/mpeg",
        });
      } catch (err) {
        mp3ExtractError = err;
        console.warn("[audio-extract] MP3 encode failed, fallback to WAV", err);
      }
    }

    const Ctx = (window as any).AudioContext || (window as any).webkitAudioContext;
    if (!Ctx) {
      throw new AudioExtractError(
        "AUDIO_CONTEXT_UNSUPPORTED",
        "当前浏览器不支持本地音频提取，请使用桌面版 Chrome，Edge 暂不支持。",
        {
          causeMessage:
            mp3ExtractError instanceof Error ? mp3ExtractError.message : null,
          fileSizeBytes: sourceFile.size,
        }
      );
    }

    const audioCtx: AudioContext = new Ctx();
    try {
      let input: ArrayBuffer;
      try {
        input = await sourceFile.arrayBuffer();
      } catch (error) {
        throw new AudioExtractError(
          sourceFile.size >= LARGE_FILE_AUDIO_EXTRACT_BYTES
            ? "LARGE_FILE_RESOURCE_LIMIT"
            : "UNKNOWN",
          sourceFile.size >= LARGE_FILE_AUDIO_EXTRACT_BYTES
            ? "当前视频文件较大，浏览器在本地读取时资源不足。请先压缩视频或截短后再试。"
            : "浏览器读取当前视频失败，请重新选择文件后重试。",
          {
            causeMessage: error instanceof Error ? error.message : null,
            fileSizeBytes: sourceFile.size,
          }
        );
      }

      let decoded: AudioBuffer;
      try {
        decoded = await audioCtx.decodeAudioData(input.slice(0));
      } catch (error) {
        throw new AudioExtractError(
          sourceFile.size >= LARGE_FILE_AUDIO_EXTRACT_BYTES
            ? "LARGE_FILE_RESOURCE_LIMIT"
            : "AUDIO_DECODE_FAILED",
          sourceFile.size >= LARGE_FILE_AUDIO_EXTRACT_BYTES
            ? "当前视频文件较大，浏览器在本地提取音频时资源不足。请先压缩视频或截短后再试。"
            : "当前视频的音频轨无法在浏览器中读取。可能是音频编码不兼容或文件异常，建议先转成 H.264/AAC 的 MP4 后再上传。",
          {
            causeMessage: error instanceof Error ? error.message : null,
            fileSizeBytes: sourceFile.size,
          }
        );
      }

      const mono = toMonoChannelData(decoded);
      const resampled = resampleLinear(mono, decoded.sampleRate, sampleRate);
      const wav = encodeWavPcm16Mono(resampled, sampleRate);
      return new File([wav], getOutputName(sourceFile.name, "wav"), {
        type: "audio/wav",
      });
    } finally {
      try {
        await audioCtx.close();
      } catch {
        // ignore close failures
      }
    }
  } catch (error) {
    if (error instanceof AudioExtractError) {
      throw error;
    }
    throw new AudioExtractError(
      "UNKNOWN",
      "浏览器本地音频提取失败，请使用桌面版 Chrome，或更换更标准的视频格式后重试。",
      {
        causeMessage: error instanceof Error ? error.message : null,
        fileSizeBytes: sourceFile.size,
      }
    );
  }
}
