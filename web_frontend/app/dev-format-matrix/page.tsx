"use client";

import React from "react";
import { useEffect, useMemo, useState } from "react";
import { AbsoluteFill } from "remotion";
import { Video } from "@remotion/media";

import { WEB_RENDER_DELAY_RENDER_TIMEOUT_MS } from "@/lib/remotion/rendering";
import {
  buildDynamicRenderBitratePlan,
  buildVideoBitrateFallbacks,
  type WebRenderAudioCodec,
  type WebRenderVideoCodec,
} from "@/lib/remotion/export-bitrate";
import {
  choosePreferredVideoDimensions,
  tryParseVideoMetadataWithMediaInfo,
} from "@/lib/media-metadata";
import { inspectRenderSourceCompatibility } from "@/lib/video-render-compatibility";
import { transcodeVideoToBrowserCompatibleMp4 } from "@/lib/video-transcode";

type FormatProbeResult = {
  sample: string;
  input: {
    fileName: string;
    mimeType: string;
    width: number | null;
    height: number | null;
    fps: number | null;
    codec: string | null;
    overallBitrate: number | null;
    videoBitrate: number | null;
    audioBitrate: number | null;
  };
  compatibility: {
    status: string;
    videoCodec: string | null;
    audioCodec: string | null;
    message: string;
  };
  transcode?: {
    applied: boolean;
    fileName: string;
  };
  output?: {
    container: string;
    videoCodec: string;
    audioCodec: string;
    width: number | null;
    height: number | null;
    fps: number | null;
    codec: string | null;
    overallBitrate: number | null;
    videoBitrate: number | null;
    audioBitrate: number | null;
    blobSize: number;
  };
  error?: string;
};

const SAMPLE_FILES = [
  "small_h264_aac_mp4.mp4",
  "small_hevc_aac_mp4.mp4",
  "small_hevc_aac_mov.mov",
  "small_vp9_opus_webm.webm",
] as const;

type ProbePhase =
  | "fetch"
  | "parse-input"
  | "compatibility"
  | "transcode"
  | "resolve-render-meta"
  | "render"
  | "parse-output";

type ProbeLogEntry = {
  sample: string;
  phase: ProbePhase;
  detail: string;
};

const UploadRenderProbeVideo: React.FC<{ src: string }> = ({ src }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#000000" }}>
      <Video src={src} />
    </AbsoluteFill>
  );
};

async function readVideoElementMetadata(file: File): Promise<{
  width: number;
  height: number;
  duration: number;
}> {
  const url = URL.createObjectURL(file);
  try {
    return await new Promise((resolve, reject) => {
      const video = document.createElement("video");
      video.preload = "metadata";
      video.muted = true;
      video.onloadedmetadata = () => {
        resolve({
          width: Math.round(video.videoWidth || 0),
          height: Math.round(video.videoHeight || 0),
          duration: video.duration,
        });
      };
      video.onerror = () => reject(new Error("failed to read video element metadata"));
      video.src = url;
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function readVideoElementMetadataWithTimeout(
  file: File,
  timeoutMs: number
): Promise<{
  width: number;
  height: number;
  duration: number;
} | null> {
  let timer: ReturnType<typeof setTimeout> | null = null;
  try {
    return await Promise.race([
      readVideoElementMetadata(file),
      new Promise<null>((resolve) => {
        timer = setTimeout(() => resolve(null), timeoutMs);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

async function estimateFps(file: File): Promise<number> {
  const url = URL.createObjectURL(file);
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.preload = "auto";
  video.src = url;

  try {
    await video.play();
  } catch {
    URL.revokeObjectURL(url);
    return 30;
  }

  return await new Promise((resolve) => {
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
      URL.revokeObjectURL(url);
      const dt =
        firstMediaTime !== null && lastMediaTime !== null
          ? lastMediaTime - firstMediaTime
          : 0;
      const fps = dt > 0 ? frames / dt : 0;
      resolve(Number.isFinite(fps) && fps > 1 && fps < 240 ? Math.round(fps * 1000) / 1000 : 30);
    };

    const onFrame = (_now: number, frame: { mediaTime: number }) => {
      const t = typeof frame?.mediaTime === "number" ? frame.mediaTime : NaN;
      if (Number.isFinite(t)) {
        if (firstMediaTime === null) firstMediaTime = t;
        lastMediaTime = t;
        frames += 1;
      }

      if (frames >= maxFrames || performance.now() - startAt >= maxMs) {
        finish();
        return;
      }
      const requestCb = (video as unknown as { requestVideoFrameCallback?: typeof window.requestAnimationFrame })
        .requestVideoFrameCallback;
      if (typeof requestCb === "function") {
        requestCb.call(video, onFrame as never);
      } else {
        finish();
      }
    };

    const requestCb = (video as unknown as { requestVideoFrameCallback?: typeof window.requestAnimationFrame })
      .requestVideoFrameCallback;
    if (typeof requestCb === "function") {
      requestCb.call(video, onFrame as never);
    } else {
      finish();
    }
  });
}

async function resolveRenderMeta(file: File) {
  const mediaInfoMeta = await tryParseVideoMetadataWithMediaInfo(file);
  const needsBrowserMeta = !(
    typeof mediaInfoMeta?.width === "number" &&
    mediaInfoMeta.width > 0 &&
    typeof mediaInfoMeta?.height === "number" &&
    mediaInfoMeta.height > 0 &&
    typeof mediaInfoMeta?.durationSec === "number" &&
    mediaInfoMeta.durationSec > 0
  );
  const browserMeta = needsBrowserMeta ? await readVideoElementMetadataWithTimeout(file, 4_000) : null;
  const preferred = choosePreferredVideoDimensions({
    browserWidth: browserMeta?.width ?? null,
    browserHeight: browserMeta?.height ?? null,
    metadataWidth: mediaInfoMeta?.width ?? null,
    metadataHeight: mediaInfoMeta?.height ?? null,
  });

  return {
    width: preferred.width ?? browserMeta?.width ?? 360,
    height: preferred.height ?? browserMeta?.height ?? 640,
    durationSec:
      typeof mediaInfoMeta?.durationSec === "number" && Number.isFinite(mediaInfoMeta.durationSec)
        ? mediaInfoMeta.durationSec
        : typeof browserMeta?.duration === "number" && Number.isFinite(browserMeta.duration) && browserMeta.duration > 0
          ? browserMeta.duration
          : 2,
    fps: mediaInfoMeta?.fps ?? (await estimateFps(file)),
    overallBitrate: mediaInfoMeta?.overallBitrate ?? null,
    videoBitrate: mediaInfoMeta?.videoBitrate ?? null,
    audioBitrate: mediaInfoMeta?.audioBitrate ?? null,
    videoCodec: mediaInfoMeta?.videoCodec ?? null,
  };
}

async function fetchSample(name: string): Promise<File> {
  const response = await fetch(`/generated-format-samples/${name}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`failed to fetch sample ${name}: HTTP ${response.status}`);
  }
  const blob = await response.blob();
  return new File([blob], name, { type: blob.type || "video/*" });
}

async function probeSample(
  name: string,
  onProgress?: (entry: ProbeLogEntry) => void
): Promise<FormatProbeResult> {
  onProgress?.({ sample: name, phase: "fetch", detail: "fetch sample" });
  const inputFile = await fetchSample(name);
  onProgress?.({ sample: name, phase: "parse-input", detail: "parse input metadata" });
  const inputMeta = await tryParseVideoMetadataWithMediaInfo(inputFile);
  onProgress?.({ sample: name, phase: "compatibility", detail: "inspect browser compatibility" });
  const compatibility = await inspectRenderSourceCompatibility(inputFile);

  let sourceFile = inputFile;
  let transcodeInfo: FormatProbeResult["transcode"];
  if (compatibility.status === "incompatible") {
    onProgress?.({ sample: name, phase: "transcode", detail: "transcode to browser-compatible mp4" });
    sourceFile = await transcodeVideoToBrowserCompatibleMp4(inputFile);
    transcodeInfo = {
      applied: true,
      fileName: sourceFile.name,
    };
  }

  onProgress?.({ sample: name, phase: "resolve-render-meta", detail: "resolve render metadata" });
  const sourceMeta = await resolveRenderMeta(sourceFile);
  const shouldUseObjectUrl = Boolean(transcodeInfo?.applied);
  const objectUrl = shouldUseObjectUrl ? URL.createObjectURL(sourceFile) : null;
  const renderSrc = objectUrl ?? `/generated-format-samples/${name}`;

  try {
    onProgress?.({ sample: name, phase: "render", detail: "render via web renderer" });
    const {
      renderMediaOnWeb,
      getEncodableAudioCodecs,
      getEncodableVideoCodecs,
    } = await import("@remotion/web-renderer");

    const mp4AudioCodecs = await getEncodableAudioCodecs("mp4");
    const webmAudioCodecs = await getEncodableAudioCodecs("webm");
    const hasMp4Audio = mp4AudioCodecs.length > 0;
    const hasWebmAudio = webmAudioCodecs.length > 0;

    let container: "mp4" | "webm" = "mp4";
    let videoCodec: WebRenderVideoCodec = "h264";
    let muted = false;

    if (hasMp4Audio) {
      container = "mp4";
      videoCodec = "h264";
    } else if (hasWebmAudio) {
      container = "webm";
      videoCodec = "vp8";
    } else {
      container = "mp4";
      videoCodec = "h264";
      muted = true;
    }

    const audioCodec: WebRenderAudioCodec = container === "mp4" ? "aac" : "opus";
    const bitratePlan = buildDynamicRenderBitratePlan({
      meta: {
        width: sourceMeta.width,
        height: sourceMeta.height,
        fps: sourceMeta.fps,
        duration_sec: sourceMeta.durationSec,
        source_overall_bitrate: sourceMeta.overallBitrate ?? undefined,
        source_video_bitrate: sourceMeta.videoBitrate ?? undefined,
        source_audio_bitrate: sourceMeta.audioBitrate ?? undefined,
        source_video_codec: sourceMeta.videoCodec ?? undefined,
      },
      fileSizeBytes: sourceFile.size,
      videoCodec,
      audioCodec,
    });

    let resolvedVideoBitrate = bitratePlan.videoBitrate;
    for (const candidate of buildVideoBitrateFallbacks(
      bitratePlan.videoBitrate,
      bitratePlan.fallbackVideoBitrate
    )) {
      const encodable = await getEncodableVideoCodecs(container, { videoBitrate: candidate });
      if (encodable.includes(videoCodec)) {
        resolvedVideoBitrate = candidate;
        break;
      }
    }

    let resolvedAudioBitrate = bitratePlan.audioBitrate;
    if (!muted) {
      const encodableAudio = await getEncodableAudioCodecs(container, {
        audioBitrate: resolvedAudioBitrate,
      });
      if (!encodableAudio.includes(audioCodec)) {
        resolvedAudioBitrate = audioCodec === "aac" ? 128_000 : 96_000;
      }
    }

    const durationSec = Math.max(0.5, Math.min(sourceMeta.durationSec, 0.8));
    const fps = Math.max(1, sourceMeta.fps || 30);
    const composition = {
      id: `format-probe-${name}`,
      component: UploadRenderProbeVideo,
      fps,
      width: sourceMeta.width,
      height: sourceMeta.height,
      durationInFrames: Math.max(1, Math.ceil(durationSec * fps)),
      defaultProps: {
        src: renderSrc,
      },
    };
    const inputProps = {
      src: renderSrc,
    };

    const renderOptions: Parameters<typeof renderMediaOnWeb>[0] = {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      composition: composition as any,
      inputProps,
      container,
      videoCodec,
      audioBitrate: resolvedAudioBitrate,
      videoBitrate: resolvedVideoBitrate,
      delayRenderTimeoutInMilliseconds: WEB_RENDER_DELAY_RENDER_TIMEOUT_MS,
      ...(muted ? { muted: true } : {}),
    };

    let result: Awaited<ReturnType<typeof renderMediaOnWeb>>;
    try {
      result = await renderMediaOnWeb(renderOptions);
    } catch (renderErr) {
      const message = renderErr instanceof Error ? renderErr.message : String(renderErr);
      if (!muted && message.includes("No audio codec can be encoded")) {
        result = await renderMediaOnWeb({ ...renderOptions, muted: true });
        muted = true;
      } else {
        throw renderErr;
      }
    }

    const outputBlob = await result.getBlob();
    const outputFile = new File([outputBlob], `${name}.${container}`, {
      type: outputBlob.type || (container === "mp4" ? "video/mp4" : "video/webm"),
    });
    onProgress?.({ sample: name, phase: "parse-output", detail: "parse output metadata" });
    const outputMeta = await tryParseVideoMetadataWithMediaInfo(outputFile);

    return {
      sample: name,
      input: {
        fileName: inputFile.name,
        mimeType: inputFile.type || "video/*",
        width: inputMeta?.width ?? null,
        height: inputMeta?.height ?? null,
        fps: inputMeta?.fps ?? null,
        codec: inputMeta?.videoCodec ?? null,
        overallBitrate: inputMeta?.overallBitrate ?? null,
        videoBitrate: inputMeta?.videoBitrate ?? null,
        audioBitrate: inputMeta?.audioBitrate ?? null,
      },
      compatibility: {
        status: compatibility.status,
        videoCodec: compatibility.videoCodec,
        audioCodec: compatibility.audioCodec,
        message: compatibility.message,
      },
      transcode: transcodeInfo,
      output: {
        container,
        videoCodec,
        audioCodec: muted ? "muted" : audioCodec,
        width: outputMeta?.width ?? null,
        height: outputMeta?.height ?? null,
        fps: outputMeta?.fps ?? null,
        codec: outputMeta?.videoCodec ?? null,
        overallBitrate: outputMeta?.overallBitrate ?? null,
        videoBitrate: outputMeta?.videoBitrate ?? null,
        audioBitrate: outputMeta?.audioBitrate ?? null,
        blobSize: outputBlob.size,
      },
    };
  } finally {
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
    }
  }
}

export default function DevFormatMatrixPage() {
  const [status, setStatus] = useState("idle");
  const [results, setResults] = useState<FormatProbeResult[]>([]);
  const [logs, setLogs] = useState<ProbeLogEntry[]>([]);
  const selectedSamples = useMemo(() => {
    if (typeof window === "undefined") {
      return [...SAMPLE_FILES];
    }
    const params = new URLSearchParams(window.location.search);
    const sample = params.get("sample");
    if (sample && SAMPLE_FILES.includes(sample as (typeof SAMPLE_FILES)[number])) {
      return [sample as (typeof SAMPLE_FILES)[number]];
    }
    return [...SAMPLE_FILES];
  }, []);

  useEffect(() => {
    let cancelled = false;
    const pushLog = (entry: ProbeLogEntry) => {
      if (cancelled) return;
      setLogs((current) => [...current, entry]);
      setStatus(`${entry.sample}: ${entry.phase} - ${entry.detail}`);
    };
    const withTimeout = async <T,>(promise: Promise<T>, ms: number, label: string): Promise<T> => {
      let timer: ReturnType<typeof setTimeout> | null = null;
      try {
        return await Promise.race([
          promise,
          new Promise<T>((_, reject) => {
            timer = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms);
          }),
        ]);
      } finally {
        if (timer) clearTimeout(timer);
      }
    };

    const run = async () => {
      setStatus("running");
      const nextResults: FormatProbeResult[] = [];
      for (const sample of selectedSamples) {
        if (cancelled) return;
        try {
          nextResults.push(await withTimeout(probeSample(sample, pushLog), 180_000, sample));
        } catch (error) {
          nextResults.push({
            sample,
            input: {
              fileName: sample,
              mimeType: "video/*",
              width: null,
              height: null,
              fps: null,
              codec: null,
              overallBitrate: null,
              videoBitrate: null,
              audioBitrate: null,
            },
            compatibility: {
              status: "error",
              videoCodec: null,
              audioCodec: null,
              message: error instanceof Error ? error.message : String(error),
            },
            error: error instanceof Error ? error.message : String(error),
          });
        }
        setResults([...nextResults]);
      }
      if (!cancelled) {
        setStatus("done");
      }
    };

    run().catch((error) => {
      if (!cancelled) {
        setStatus(`error: ${error instanceof Error ? error.message : String(error)}`);
      }
    });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main style={{ padding: 24, fontFamily: "monospace", whiteSpace: "pre-wrap" }}>
      <h1>Dev Format Matrix</h1>
      <div id="status">{status}</div>
      <pre id="logs">{JSON.stringify(logs, null, 2)}</pre>
      <pre id="results">{JSON.stringify(results, null, 2)}</pre>
    </main>
  );
}
