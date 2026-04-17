type AnyRecord = Record<string, unknown>;

export type SubtitleRenderV1CaptionToken = {
  text: string;
  start: number;
  end: number;
  sourceWordIndex?: number;
};

export type SubtitleRenderV1Caption = {
  index: number;
  start: number;
  end: number;
  text: string;
  tokens?: SubtitleRenderV1CaptionToken[];
  label?: {
    badgeText?: string;
    emphasisSpans?: Array<{startToken: number; endToken: number}>;
  };
  alignmentMode?: "exact" | "fuzzy" | "degraded" | "missing";
};

export type SubtitleRenderV1Contract = AnyRecord & {
  contract?: string;
  version?: string;
  type?: string;
  output_name?: string;
  outputName?: string;
  src?: string;
  captions?: SubtitleRenderV1Caption[];
  segments?: Array<{start: number; end: number}>;
  topics?: Array<{title: string; start: number; end: number}>;
  chapters?: Array<{title: string; start: number; end: number}>;
  composition?: {
    fps?: number;
    width?: number;
    height?: number;
    durationInFrames?: number;
  };
  video?: {
    src?: string;
    fps?: number;
    width?: number;
    height?: number;
  };
  render?: AnyRecord;
  input_props?: AnyRecord;
  props?: AnyRecord;
  payload?: AnyRecord;
};

const SUBTITLE_RENDER_V1 = "subtitle-render.v1";

const asRecord = (value: unknown): AnyRecord | null =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as AnyRecord)
    : null;

const asNumber = (value: unknown): number | null => {
  const normalized = typeof value === "number" ? value : Number(value);
  return Number.isFinite(normalized) ? normalized : null;
};

const asString = (value: unknown): string => String(value ?? "").trim();

const pickPayload = (contract: SubtitleRenderV1Contract): AnyRecord => {
  const render = asRecord(contract.render);
  if (render) {
    return asRecord(render.input_props) ?? render;
  }
  return (
    asRecord(contract.input_props) ??
    asRecord(contract.props) ??
    asRecord(contract.payload) ??
    contract
  );
};

export const isSubtitleRenderV1Contract = (value: unknown): value is SubtitleRenderV1Contract => {
  const record = asRecord(value);
  if (!record) return false;
  const marker = asString(record.contract ?? record.version ?? record.type);
  return marker === SUBTITLE_RENDER_V1;
};

const normalizeCaptionToken = (value: unknown): SubtitleRenderV1CaptionToken | null => {
  const record = asRecord(value);
  if (!record) return null;
  const text = asString(record.text);
  const start = asNumber(record.start);
  const end = asNumber(record.end);
  if (!text || start === null || end === null || end < start) return null;
  const sourceWordIndex = asNumber(record.sourceWordIndex);
  return {
    text,
    start,
    end,
    ...(sourceWordIndex === null ? {} : {sourceWordIndex: Math.trunc(sourceWordIndex)}),
  };
};

const normalizeCaption = (value: unknown, fallbackIndex: number): SubtitleRenderV1Caption | null => {
  const record = asRecord(value);
  if (!record) return null;
  const text = asString(record.text);
  const start = asNumber(record.start);
  const end = asNumber(record.end);
  if (!text || start === null || end === null || end <= start) return null;
  const index = asNumber(record.index);
  const tokens = Array.isArray(record.tokens)
    ? record.tokens
        .map((item) => normalizeCaptionToken(item))
        .filter((item): item is SubtitleRenderV1CaptionToken => item !== null)
    : [];
  const labelRecord = asRecord(record.label);
  const emphasisSpans = Array.isArray(labelRecord?.emphasisSpans)
    ? labelRecord?.emphasisSpans
        .map((span) => {
          const spanRecord = asRecord(span);
          if (!spanRecord) return null;
          const startToken = asNumber(spanRecord.startToken);
          const endToken = asNumber(spanRecord.endToken);
          if (startToken === null || endToken === null || endToken <= startToken) return null;
          return {startToken: Math.trunc(startToken), endToken: Math.trunc(endToken)};
        })
        .filter((item): item is {startToken: number; endToken: number} => item !== null)
    : [];
  const badgeText = asString(labelRecord?.badgeText);
  const alignmentMode = asString(record.alignmentMode);

  return {
    index: index === null ? fallbackIndex : Math.trunc(index),
    start,
    end,
    text,
    ...(tokens.length ? {tokens} : {}),
    ...(badgeText || emphasisSpans.length
      ? {
          label: {
            ...(badgeText ? {badgeText} : {}),
            ...(emphasisSpans.length ? {emphasisSpans} : {}),
          },
        }
      : {}),
    ...(alignmentMode === "exact" || alignmentMode === "fuzzy" || alignmentMode === "degraded" || alignmentMode === "missing"
      ? {alignmentMode: alignmentMode as SubtitleRenderV1Caption["alignmentMode"]}
      : {}),
  };
};

const normalizeTimelineItems = (values: unknown, titleKey: "title" | null) => {
  if (!Array.isArray(values)) return [];
  return values
    .map((value) => {
      const record = asRecord(value);
      if (!record) return null;
      const start = asNumber(record.start);
      const end = asNumber(record.end);
      if (start === null || end === null || end <= start) return null;
      if (titleKey) {
        const title = asString(record[titleKey]);
        if (!title) return null;
        return {title, start, end};
      }
      return {start, end};
    })
    .filter((item): item is {start: number; end: number} | {title: string; start: number; end: number} => item !== null);
};

const computeDurationInFrames = (
  fps: number,
  captions: SubtitleRenderV1Caption[],
  segments: Array<{start: number; end: number}>
): number => {
  const explicit = segments.reduce((sum, segment) => {
    const trimBefore = Math.max(0, Math.floor(segment.start * fps));
    const trimAfter = Math.max(trimBefore + 1, Math.ceil(segment.end * fps));
    return sum + Math.max(1, trimAfter - trimBefore);
  }, 0);
  if (explicit > 0) return explicit;
  const lastCaptionEnd = captions.reduce((max, caption) => Math.max(max, caption.end), 0);
  return Math.max(1, Math.ceil(Math.max(lastCaptionEnd, 1 / fps) * fps));
};

export const coerceWebRenderConfig = <T extends AnyRecord>(value: T): T => {
  if (!isSubtitleRenderV1Contract(value)) return value;

  const payload = pickPayload(value);
  const composition = asRecord(payload.composition) ?? asRecord(value.composition) ?? {};
  const video = asRecord(payload.video) ?? asRecord(value.video) ?? {};
  const fps = asNumber(composition.fps ?? video.fps ?? payload.fps) ?? 30;
  const width = asNumber(composition.width ?? video.width ?? payload.width) ?? 1080;
  const height = asNumber(composition.height ?? video.height ?? payload.height) ?? 1920;
  const normalizedCaptions = (Array.isArray(payload.captions) ? payload.captions : [])
    .map((item, index) => normalizeCaption(item, index + 1))
    .filter((item): item is SubtitleRenderV1Caption => item !== null);
  const normalizedSegments = normalizeTimelineItems(payload.segments, null) as Array<{start: number; end: number}>;
  const normalizedTopics = normalizeTimelineItems(payload.topics ?? payload.chapters, "title") as Array<{title: string; start: number; end: number}>;
  const durationInFrames =
    asNumber(composition.durationInFrames) ??
    computeDurationInFrames(fps, normalizedCaptions, normalizedSegments);

  const inputProps: AnyRecord = {
    src: asString(payload.src ?? video.src),
    captions: normalizedCaptions,
    segments: normalizedSegments,
    topics: normalizedTopics,
    fps,
    width,
    height,
  };
  for (const key of [
    "subtitleTheme",
    "subtitleScale",
    "subtitleYPercent",
    "progressScale",
    "progressYPercent",
    "chapterScale",
    "showSubtitles",
    "showProgress",
    "showChapter",
    "progressLabelMode",
  ] as const) {
    const candidate = payload[key];
    if (candidate !== undefined && candidate !== null) {
      inputProps[key] = candidate;
    }
  }

  return {
    output_name: asString(value.output_name ?? value.outputName) || "subtitle-render_export.mp4",
    composition: {
      id: "StitchVideoWeb",
      fps,
      width,
      height,
      durationInFrames: Math.max(1, Math.ceil(durationInFrames)),
    },
    input_props: inputProps,
  } as unknown as T;
};

export const coerceStitchVideoWebProps = <T extends AnyRecord>(value: T): T => {
  if (!isSubtitleRenderV1Contract(value)) return value;
  return (coerceWebRenderConfig(value) as AnyRecord).input_props as T;
};
