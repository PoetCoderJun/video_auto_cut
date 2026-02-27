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

function floatToInt16(samples: Float32Array): Int16Array {
  const out = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i += 1) {
    const s = Math.max(-1, Math.min(1, samples[i] ?? 0));
    out[i] = Math.round(s * (s < 0 ? 0x8000 : 0x7fff));
  }
  return out;
}

async function encodeMp3FromInt16(
  samples: Int16Array,
  sampleRate: number,
  kbps: number
): Promise<Blob> {
  // lamejs is published as a CommonJS module; under ESM bundlers the
  // actual exports live on the `default` property.
  const imported = await import("lamejs");
  const lame: any = (imported as any).default ?? imported;
  const Mp3Encoder = lame.Mp3Encoder as
    | (new (channels: number, sampleRate: number, kbps: number) => {
        encodeBuffer(input: Int16Array): Uint8Array;
        flush(): Uint8Array;
      })
    | undefined;

  if (typeof Mp3Encoder !== "function") {
    throw new Error("Mp3Encoder is not available from lamejs module");
  }

  const mp3encoder = new Mp3Encoder(1, sampleRate, kbps);
  const mp3Data: Uint8Array[] = [];
  const maxSamples = 1152;
  for (let i = 0; i < samples.length; i += maxSamples) {
    const chunk = samples.subarray(i, Math.min(i + maxSamples, samples.length));
    const mp3buf = mp3encoder.encodeBuffer(chunk);
    if (mp3buf.length > 0) {
      mp3Data.push(mp3buf);
    }
  }
  const last = mp3encoder.flush();
  if (last.length > 0) {
    mp3Data.push(last);
  }
  return new Blob(mp3Data, { type: "audio/mp3" });
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
 * Extract audio for ASR. Prefer MP3 (64kbps) for smaller upload; fallback to WAV if MP3 fails.
 */
export async function extractAudioForAsr(
  sourceFile: File,
  sampleRate = 16000,
  format: ExtractAudioFormat = "mp3"
): Promise<File> {
  const Ctx = (window as any).AudioContext || (window as any).webkitAudioContext;
  if (!Ctx) {
    throw new Error("当前浏览器不支持 AudioContext，无法提取音频。");
  }

  const audioCtx: AudioContext = new Ctx();
  try {
    const input = await sourceFile.arrayBuffer();
    const decoded = await audioCtx.decodeAudioData(input.slice(0));
    const mono = toMonoChannelData(decoded);
    const resampled = resampleLinear(mono, decoded.sampleRate, sampleRate);

    if (format === "mp3") {
      try {
        const int16 = floatToInt16(resampled);
        const mp3 = await encodeMp3FromInt16(int16, sampleRate, 64);
        return new File([mp3], getOutputName(sourceFile.name, "mp3"), {
          type: "audio/mp3",
        });
      } catch {
        // lamejs 可能在某些情况下失败，回退到 WAV
        const wav = encodeWavPcm16Mono(resampled, sampleRate);
        return new File([wav], getOutputName(sourceFile.name, "wav"), {
          type: "audio/wav",
        });
      }
    }
    const wav = encodeWavPcm16Mono(resampled, sampleRate);
    return new File([wav], getOutputName(sourceFile.name, "wav"), {
      type: "audio/wav",
    });
  } catch (error) {
    throw new Error("浏览器音频提取失败，请尝试使用 Chrome 或更换视频格式。");
  } finally {
    try {
      await audioCtx.close();
    } catch {
      // ignore close failures
    }
  }
}

