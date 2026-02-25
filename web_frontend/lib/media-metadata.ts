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

export async function tryParseFpsWithMediaInfo(file: File): Promise<number | null> {
  try {
    const factory = await loadMediaInfoFactory();
    if (!factory) return null;

    const mediainfo = await factory({
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
    mediainfo.close();

    const tracks: any[] = result?.media?.track;
    if (!Array.isArray(tracks)) return null;
    const videoTrack = tracks.find((t) => t && t["@type"] === "Video") || null;
    if (!videoTrack) return null;

    const candidates: Array<number | null> = [
      typeof videoTrack.FrameRate === "number" ? videoTrack.FrameRate : null,
      typeof videoTrack.FrameRate_Real === "number" ? videoTrack.FrameRate_Real : null,
      typeof videoTrack.FrameRate_Nominal === "number" ? videoTrack.FrameRate_Nominal : null,
      typeof videoTrack.FrameRate_Original === "number" ? videoTrack.FrameRate_Original : null,
    ];
    const fromRatio =
      typeof videoTrack.FrameRate_Num === "number" &&
      typeof videoTrack.FrameRate_Den === "number" &&
      videoTrack.FrameRate_Den > 0
        ? videoTrack.FrameRate_Num / videoTrack.FrameRate_Den
        : null;
    candidates.push(fromRatio);

    for (const fps of candidates) {
      if (typeof fps !== "number") continue;
      if (!Number.isFinite(fps) || fps <= 1 || fps >= 240) continue;
      return Math.round(fps * 1000) / 1000;
    }
    return null;
  } catch {
    return null;
  }
}
