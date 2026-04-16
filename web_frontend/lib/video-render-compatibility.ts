import { ALL_FORMATS, BlobSource, Input } from "mediabunny";

export const MOCK_CAN_DECODE_FALSE_MARKER = "__mock_can_decode_false__";

export type RenderSourceCompatibility = {
  status: "compatible" | "incompatible" | "blocked" | "unknown";
  message: string;
  videoCodec: string | null;
  audioCodec: string | null;
};

function formatCodec(codec: string | null): string {
  const normalized = String(codec || "").trim();
  return normalized || "未知编码";
}

export function isMockCanDecodeFalseFileName(
  fileName: string | null | undefined
): boolean {
  return String(fileName || "")
    .toLowerCase()
    .includes(MOCK_CAN_DECODE_FALSE_MARKER);
}

export function getRenderSourceDirectExportErrorMessage(
  compatibility: RenderSourceCompatibility
): string | null {
  if (
    compatibility.status === "blocked" ||
    compatibility.status === "incompatible"
  ) {
    return compatibility.message;
  }

  return null;
}

export async function inspectRenderSourceCompatibility(
  file: File
): Promise<RenderSourceCompatibility> {
  if (isMockCanDecodeFalseFileName(file.name)) {
    return {
      status: "incompatible",
      message:
        "当前文件命中了 canDecode=false mock 标记，已强制视为不兼容。会先转成兼容 MP4 再导出。",
      videoCodec: "mock-undecodable-video",
      audioCodec: null,
    };
  }

  if (typeof window === "undefined") {
    return {
      status: "blocked",
      message: "当前环境不支持浏览器端兼容性检查。",
      videoCodec: null,
      audioCodec: null,
    };
  }

  if (typeof VideoDecoder === "undefined") {
    return {
      status: "blocked",
      message:
        "当前浏览器不支持 VideoDecoder，前端转码后也无法继续浏览器导出。请改用最新版 Chrome / Edge。",
      videoCodec: null,
      audioCodec: null,
    };
  }

  const input = new Input({
    formats: ALL_FORMATS,
    source: new BlobSource(file),
  });

  try {
    const videoTrack = await input.getPrimaryVideoTrack();
    if (!videoTrack) {
      return {
        status: "blocked",
        message: "当前文件没有可读取的视频轨道，请重新选择原始视频。",
        videoCodec: null,
        audioCodec: null,
      };
    }

    const audioTrack = await input.getPrimaryAudioTrack();
    const videoCodec =
      String((await videoTrack.getCodecParameterString()) || videoTrack.codec || "").trim() || null;
    const audioCodec =
      audioTrack
        ? String((await audioTrack.getCodecParameterString()) || audioTrack.codec || "").trim() || null
        : null;

    const videoCanDecode = await videoTrack.canDecode();
    if (!videoCanDecode) {
      return {
        status: "incompatible",
        message: `当前浏览器无法解码该视频轨，检测到视频编码为 ${formatCodec(videoCodec)}。需要先转成兼容 MP4 后再导出。`,
        videoCodec,
        audioCodec,
      };
    }

    if (audioTrack) {
      const audioCanDecode = await audioTrack.canDecode();
      if (!audioCanDecode) {
        return {
          status: "incompatible",
          message: `当前浏览器无法解码该音频轨，检测到音频编码为 ${formatCodec(audioCodec)}。需要先转成兼容 MP4 后再导出。`,
          videoCodec,
          audioCodec,
        };
      }
    }

    return {
      status: "compatible",
      message: "当前源视频可直接用于浏览器导出。",
      videoCodec,
      audioCodec,
    };
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "无法读取视频轨信息。";
    return {
      status: "unknown",
      message: `当前文件暂时无法完成兼容性检查：${message}。将继续允许直接导出。`,
      videoCodec: null,
      audioCodec: null,
    };
  } finally {
    input.dispose();
  }
}
