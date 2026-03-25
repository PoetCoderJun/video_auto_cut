type MediaInfoFactory = (options: {
  format?: "object" | "JSON" | "XML" | "HTML" | "text";
  locateFile?: (path: string, prefix: string) => string;
}) => Promise<{
  analyzeData: (
    size: (() => number | Promise<number>) | number,
    readChunk: (size: number, offset: number) => Uint8Array | Promise<Uint8Array>
  ) => Promise<any>;
  close: () => void;
}>;

export type ParsedVideoMetadata = {
  width: number | null;
  height: number | null;
  fps: number | null;
  durationSec: number | null;
  overallBitrate: number | null;
  videoBitrate: number | null;
  audioBitrate: number | null;
  videoCodec: string | null;
};

export type PreferredVideoDimensions = {
  width: number | null;
  height: number | null;
  source: "browser" | "metadata";
};

let mediaInfoFactoryPromise: Promise<MediaInfoFactory | null> | null = null;

async function loadMediaInfoFactory(): Promise<MediaInfoFactory | null> {
  if (mediaInfoFactoryPromise) return mediaInfoFactoryPromise;
  mediaInfoFactoryPromise = (async () => {
    if (typeof window === "undefined") return null;

    const existing = (window as any).MediaInfo?.mediaInfoFactory;
    if (typeof existing === "function") return existing as MediaInfoFactory;

    await new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "/vendor/mediainfo/mediainfo.min.js";
      script.async = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error("Failed to load mediainfo.js"));
      document.head.appendChild(script);
    });

    const loaded = (window as any).MediaInfo?.mediaInfoFactory;
    return typeof loaded === "function" ? (loaded as MediaInfoFactory) : null;
  })();
  return mediaInfoFactoryPromise;
}

function normalizePositiveNumber(value: unknown): number | null {
  const numeric = typeof value === "number" ? value : Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : null;
}

function roundFps(value: number | null): number | null {
  if (value === null || value <= 1 || value >= 240) return null;
  return Math.round(value * 1000) / 1000;
}

function pickPositiveNumber(...candidates: unknown[]): number | null {
  for (const candidate of candidates) {
    const value = normalizePositiveNumber(candidate);
    if (value !== null) return value;
  }
  return null;
}

function pickNonEmptyString(...candidates: unknown[]): string | null {
  for (const candidate of candidates) {
    const value = String(candidate || "").trim();
    if (value) return value;
  }
  return null;
}

function nearlySameAspectRatio(
  firstWidth: number,
  firstHeight: number,
  secondWidth: number,
  secondHeight: number
): boolean {
  if (firstWidth <= 0 || firstHeight <= 0 || secondWidth <= 0 || secondHeight <= 0) {
    return false;
  }
  const first = firstWidth / firstHeight;
  const second = secondWidth / secondHeight;
  return Math.abs(first - second) <= 0.02;
}

export function choosePreferredVideoDimensions(options: {
  browserWidth: number | null;
  browserHeight: number | null;
  metadataWidth: number | null;
  metadataHeight: number | null;
}): PreferredVideoDimensions {
  const browserWidth = normalizePositiveNumber(options.browserWidth);
  const browserHeight = normalizePositiveNumber(options.browserHeight);
  const metadataWidth = normalizePositiveNumber(options.metadataWidth);
  const metadataHeight = normalizePositiveNumber(options.metadataHeight);

  if (metadataWidth !== null && metadataHeight !== null) {
    if (browserWidth === null || browserHeight === null) {
      return { width: metadataWidth, height: metadataHeight, source: "metadata" };
    }

    const metadataLooksNominallyLarger =
      metadataWidth >= browserWidth * 1.08 && metadataHeight >= browserHeight * 1.08;
    if (
      metadataLooksNominallyLarger &&
      nearlySameAspectRatio(browserWidth, browserHeight, metadataWidth, metadataHeight)
    ) {
      return { width: metadataWidth, height: metadataHeight, source: "metadata" };
    }
  }

  if (browserWidth !== null && browserHeight !== null) {
    return { width: browserWidth, height: browserHeight, source: "browser" };
  }

  return {
    width: metadataWidth,
    height: metadataHeight,
    source: "metadata",
  };
}

function extractFps(videoTrack: Record<string, unknown> | null): number | null {
  if (!videoTrack) return null;
  const ratio =
    typeof videoTrack.FrameRate_Num === "number" &&
    typeof videoTrack.FrameRate_Den === "number" &&
    videoTrack.FrameRate_Den > 0
      ? videoTrack.FrameRate_Num / videoTrack.FrameRate_Den
      : null;
  return roundFps(
    pickPositiveNumber(
      videoTrack.FrameRate,
      videoTrack.FrameRate_Real,
      videoTrack.FrameRate_Nominal,
      videoTrack.FrameRate_Original,
      ratio
    )
  );
}

export function parseMediaInfoVideoMetadata(result: any): ParsedVideoMetadata | null {
  const tracks: any[] = result?.media?.track;
  if (!Array.isArray(tracks)) return null;

  const videoTrack =
    (tracks.find((track) => track && track["@type"] === "Video") as Record<string, unknown> | undefined) ||
    null;
  if (!videoTrack) return null;
  const generalTrack =
    (tracks.find((track) => track && track["@type"] === "General") as Record<string, unknown> | undefined) ||
    null;
  const audioTrack =
    (tracks.find((track) => track && track["@type"] === "Audio") as Record<string, unknown> | undefined) ||
    null;

  return {
    width: pickPositiveNumber(
      videoTrack.Width,
      videoTrack.Stored_Width,
      videoTrack.Sampled_Width,
      videoTrack.Width_Original
    ),
    height: pickPositiveNumber(
      videoTrack.Height,
      videoTrack.Stored_Height,
      videoTrack.Sampled_Height,
      videoTrack.Height_Original
    ),
    fps: extractFps(videoTrack),
    durationSec: pickPositiveNumber(
      videoTrack.Duration,
      generalTrack?.Duration,
      videoTrack.Source_Duration
     ),
    overallBitrate: pickPositiveNumber(
      generalTrack?.OverallBitRate,
      generalTrack?.OverallBitRate_Nominal,
      generalTrack?.BitRate,
      generalTrack?.BitRate_Nominal
    ),
    videoBitrate: pickPositiveNumber(
      videoTrack.BitRate,
      videoTrack.BitRate_Nominal,
      videoTrack.BitRate_Encoded
    ),
    audioBitrate: pickPositiveNumber(
      audioTrack?.BitRate,
      audioTrack?.BitRate_Nominal,
      audioTrack?.BitRate_Encoded
    ),
    videoCodec: pickNonEmptyString(
      videoTrack.Format_Commercial_IfAny,
      videoTrack.CodecID,
      videoTrack.Format,
      videoTrack.CodecID_Hint
    ),
  };
}

export async function tryParseVideoMetadataWithMediaInfo(
  file: File
): Promise<ParsedVideoMetadata | null> {
  let mediainfo:
    | Awaited<ReturnType<MediaInfoFactory>>
    | null = null;
  try {
    const factory = await loadMediaInfoFactory();
    if (!factory) return null;

    mediainfo = await factory({
      format: "object",
      locateFile: (path: string) => `/vendor/mediainfo/${path}`,
    });

    const result = await mediainfo.analyzeData(
      () => file.size,
      async (size: number, offset: number) => {
        const slice = file.slice(offset, offset + size);
        const buf = await slice.arrayBuffer();
        return new Uint8Array(buf);
      }
    );

    return parseMediaInfoVideoMetadata(result);
  } catch {
    return null;
  } finally {
    mediainfo?.close();
  }
}

export async function tryParseFpsWithMediaInfo(file: File): Promise<number | null> {
  const metadata = await tryParseVideoMetadataWithMediaInfo(file);
  return metadata?.fps ?? null;
}
