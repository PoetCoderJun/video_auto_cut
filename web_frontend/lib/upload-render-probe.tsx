import React from "react";
import { AbsoluteFill } from "remotion";
import { Video } from "@remotion/media";

import { WEB_RENDER_DELAY_RENDER_TIMEOUT_MS, getFriendlyWebRenderErrorMessage } from "./remotion/rendering";

type ProbeCompositionProps = {
  src: string;
};

const UploadRenderProbeVideo: React.FC<ProbeCompositionProps> = ({ src }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#000000" }}>
      <Video src={src} />
    </AbsoluteFill>
  );
};

type ProbeSourceMetadata = {
  width: number;
  height: number;
};

async function loadProbeSourceMetadata(sourceUrl: string): Promise<ProbeSourceMetadata> {
  return await new Promise<ProbeSourceMetadata>((resolve, reject) => {
    const video = document.createElement("video");
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      resolve({
        width: Math.max(1, video.videoWidth || 1280),
        height: Math.max(1, video.videoHeight || 720),
      });
    };
    video.onerror = () => {
      reject(new Error("浏览器无法读取当前源视频的元数据。"));
    };
    video.src = sourceUrl;
  });
}

export async function probeBrowserRenderability(sourceFile: File): Promise<void> {
  if (typeof window === "undefined") {
    return;
  }

  if (!window.isSecureContext) {
    throw new Error(
      "当前页面不在安全上下文中（需要 HTTPS 或 localhost），浏览器禁用了视频解码器，无法提前验证导出能力。请通过 HTTPS 访问本站。"
    );
  }

  const sourceUrl = URL.createObjectURL(sourceFile);
  try {
    const metadata = await loadProbeSourceMetadata(sourceUrl);
    const { renderMediaOnWeb, getEncodableAudioCodecs } = await import("@remotion/web-renderer");

    const mp4AudioCodecs = await getEncodableAudioCodecs("mp4");
    const webmAudioCodecs = await getEncodableAudioCodecs("webm");
    const hasMp4Audio = mp4AudioCodecs.length > 0;
    const hasWebmAudio = webmAudioCodecs.length > 0;

    let container: "mp4" | "webm" = "mp4";
    let videoCodec: "h264" | "vp8" = "h264";
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

    const composition = {
      id: "UploadRenderProbeVideo",
      width: metadata.width,
      height: metadata.height,
      fps: 30,
      durationInFrames: 1,
      defaultProps: {
        src: sourceUrl,
      },
      component: UploadRenderProbeVideo,
    };

    const renderOptions: Parameters<typeof renderMediaOnWeb>[0] = {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      composition: composition as any,
      inputProps: {
        src: sourceUrl,
      },
      container,
      videoCodec,
      videoBitrate: 2_000_000,
      audioBitrate: container === "mp4" ? 128_000 : 96_000,
      delayRenderTimeoutInMilliseconds: Math.min(
        WEB_RENDER_DELAY_RENDER_TIMEOUT_MS,
        20_000
      ),
      ...(muted ? { muted: true } : {}),
    };

    let result: Awaited<ReturnType<typeof renderMediaOnWeb>>;
    try {
      result = await renderMediaOnWeb(renderOptions);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes("No audio codec can be encoded")) {
        result = await renderMediaOnWeb({ ...renderOptions, muted: true });
      } else {
        throw error;
      }
    }

    await result.getBlob();
  } catch (error) {
    throw new Error(getFriendlyWebRenderErrorMessage(error));
  } finally {
    URL.revokeObjectURL(sourceUrl);
  }
}
