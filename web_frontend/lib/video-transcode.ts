import { fetchFile } from "@ffmpeg/util";

import { getBrowserFfmpeg } from "./ffmpeg-browser";
import { getBrowserCompatibleOutputName } from "./video-transcode-name";

export type BrowserCompatibleTranscodeOptions = {
  onProgress?: (progress: number) => void;
};

export async function transcodeVideoToBrowserCompatibleMp4(
  sourceFile: File,
  options: BrowserCompatibleTranscodeOptions = {}
): Promise<File> {
  const ffmpeg = await getBrowserFfmpeg();
  const nonce = Math.random().toString(36).slice(2, 10);
  const inputName = `input_${nonce}.${(sourceFile.name.split(".").pop() || "bin").toLowerCase()}`;
  const outputName = `output_${nonce}.mp4`;
  const handleProgress = ({ progress }: { progress: number }) => {
    options.onProgress?.(
      Math.max(0, Math.min(1, Number.isFinite(progress) ? progress : 0))
    );
  };

  try {
    ffmpeg.on("progress", handleProgress);
    await ffmpeg.writeFile(inputName, await fetchFile(sourceFile));
    const exitCode = await ffmpeg.exec([
      "-i",
      inputName,
      "-map",
      "0:v:0",
      "-map",
      "0:a?:0",
      "-c:v",
      "libx264",
      "-preset",
      "veryfast",
      "-pix_fmt",
      "yuv420p",
      "-movflags",
      "+faststart",
      "-c:a",
      "aac",
      "-b:a",
      "128k",
      outputName,
    ]);
    if (exitCode !== 0) {
      throw new Error(`ffmpeg exited with code ${exitCode}`);
    }

    const data = await ffmpeg.readFile(outputName);
    if (!(data instanceof Uint8Array)) {
      throw new Error("ffmpeg output is not Uint8Array");
    }

    options.onProgress?.(1);
    return new File([data], getBrowserCompatibleOutputName(sourceFile.name), {
      type: "video/mp4",
      lastModified: Date.now(),
    });
  } catch (error) {
    throw new Error(
      error instanceof Error
        ? `前端转码失败：${error.message}`
        : "前端转码失败，请重试。"
    );
  } finally {
    ffmpeg.off("progress", handleProgress);
    await Promise.allSettled([
      ffmpeg.deleteFile(inputName),
      ffmpeg.deleteFile(outputName),
    ]);
  }
}
