type AnyRecord = Record<string, unknown>;

export type SubtitleRenderV1CaptionToken = {
  text: string;
  start: number;
  end: number;
  sourceWordIndex?: number;
};

export type SubtitleRenderV1CaptionHighlight = {
  text?: string;
  startToken?: number;
  endToken?: number;
  color?: string;
  fontScale?: number;
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
    highlights?: SubtitleRenderV1CaptionHighlight[];
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

const TIMECODE_RE = /^(?<hh>\d{2}):(?<mm>\d{2}):(?<ss>\d{2})\.(?<ms>\d{3})$/;

const asTimeSeconds = (value: unknown): number | null => {
  const numeric = asNumber(value);
  if (numeric !== null) return numeric;
  const text = asString(value);
  const match = TIMECODE_RE.exec(text);
  if (!match?.groups) return null;
  const hours = Number(match.groups.hh);
  const minutes = Number(match.groups.mm);
  const seconds = Number(match.groups.ss);
  const milliseconds = Number(match.groups.ms);
  if ([hours, minutes, seconds, milliseconds].some((item) => !Number.isFinite(item))) {
    return null;
  }
  return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000;
};

const asString = (value: unknown): string => String(value ?? "").trim();

const normalizeSubtitleTheme = (value: unknown): "black" | "white" | null => {
  const raw = asString(value);
  switch (raw) {
    case "black":
    case "box-white-on-black":
    case "text-white":
      return "black";
    case "white":
    case "box-black-on-white":
    case "text-black":
      return "white";
    default:
      return null;
  }
};

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
  const start = asTimeSeconds(record.start);
  const end = asTimeSeconds(record.end);
  if (!text || start === null || end === null || end < start) return null;
  const sourceWordIndex = asNumber(record.sourceWordIndex);
  return {
    text,
    start,
    end,
    ...(sourceWordIndex === null ? {} : {sourceWordIndex: Math.trunc(sourceWordIndex)}),
  };
};

type GeneratedCaptionToken = SubtitleRenderV1CaptionToken & {
  charStart: number;
  charEnd: number;
};

const tokenizeCaptionText = (
  text: string,
  start: number,
  end: number
): GeneratedCaptionToken[] => {
  if (!text) return [];
  const total = text.length;
  if (total <= 0) return [];
  const duration = Math.max(0, end - start);
  const tokens: GeneratedCaptionToken[] = [];
  let cursor = 0;
  while (cursor < text.length) {
    const remaining = text.slice(cursor);
    const asciiWord = remaining.match(/^[A-Za-z0-9]+(?:['._:-][A-Za-z0-9]+)*/);
    const tokenText = asciiWord?.[0] ?? text[cursor];
    const charStart = cursor;
    const charEnd = cursor + tokenText.length;
    const tokenStart = start + duration * (charStart / total);
    const tokenEnd = start + duration * (charEnd / total);
    tokens.push({
      text: tokenText,
      start: tokenStart,
      end: tokenEnd,
      charStart,
      charEnd,
    });
    cursor = charEnd;
  }
  return tokens;
};

const buildTokenMetaFromTokens = (tokens: SubtitleRenderV1CaptionToken[]): GeneratedCaptionToken[] => {
  let cursor = 0;
  return tokens.map((token) => {
    const text = String(token.text || "");
    const charStart = cursor;
    const charEnd = cursor + text.length;
    cursor = charEnd;
    return {
      ...token,
      charStart,
      charEnd,
    };
  });
};

const findHighlightTokenRange = (
  tokenMeta: GeneratedCaptionToken[],
  highlightText: string,
  usedCharStarts: Set<number>
): {startToken: number; endToken: number} | null => {
  const joined = tokenMeta.map((token) => token.text).join("");
  if (!highlightText || !joined) return null;
  let searchFrom = 0;
  while (searchFrom < joined.length) {
    const charStart = joined.indexOf(highlightText, searchFrom);
    if (charStart < 0) return null;
    if (usedCharStarts.has(charStart)) {
      searchFrom = charStart + Math.max(1, highlightText.length);
      continue;
    }
    const charEnd = charStart + highlightText.length;
    const startToken = tokenMeta.findIndex((token) => token.charStart <= charStart && token.charEnd > charStart);
    const endTokenExclusive = tokenMeta.findIndex((token) => token.charStart < charEnd && token.charEnd >= charEnd);
    if (startToken >= 0 && endTokenExclusive >= startToken) {
      usedCharStarts.add(charStart);
      return {startToken, endToken: endTokenExclusive + 1};
    }
    searchFrom = charStart + Math.max(1, highlightText.length);
  }
  return null;
};

const normalizeCaptionHighlights = (
  value: unknown,
  tokenMeta: GeneratedCaptionToken[]
): SubtitleRenderV1CaptionHighlight[] => {
  if (!Array.isArray(value)) return [];
  const usedCharStarts = new Set<number>();
  const normalized: SubtitleRenderV1CaptionHighlight[] = [];
  for (const item of value) {
      const record = asRecord(item);
      if (!record) continue;
      const text = asString(record.text);
      const startToken = asNumber(record.startToken);
      const endToken = asNumber(record.endToken);
      const resolvedRange =
        startToken !== null &&
        endToken !== null &&
        Math.trunc(endToken) > Math.trunc(startToken)
          ? {startToken: Math.trunc(startToken), endToken: Math.trunc(endToken)}
          : text
            ? findHighlightTokenRange(tokenMeta, text, usedCharStarts)
            : null;
      if (!resolvedRange) continue;
      const color = asString(record.color);
      const fontScale = asNumber(record.fontScale);
      normalized.push({
        ...(text ? {text} : {}),
        startToken: resolvedRange.startToken,
        endToken: resolvedRange.endToken,
        ...(color ? {color} : {}),
        ...(fontScale !== null && fontScale > 0 ? {fontScale} : {}),
      });
  }
  return normalized;
};

const normalizeCaption = (value: unknown, fallbackIndex: number): SubtitleRenderV1Caption | null => {
  const record = asRecord(value);
  if (!record) return null;
  const text = asString(record.text);
  const start = asTimeSeconds(record.start);
  const end = asTimeSeconds(record.end);
  if (!text || start === null || end === null || end <= start) return null;
  const index = asNumber(record.index);
  let tokens = Array.isArray(record.tokens)
    ? record.tokens
        .map((item) => normalizeCaptionToken(item))
        .filter((item): item is SubtitleRenderV1CaptionToken => item !== null)
    : [];
  const labelRecord = asRecord(record.label);
  const generatedTokenMeta = tokenizeCaptionText(text, start, end);
  if (tokens.length === 0 && Array.isArray(labelRecord?.highlights) && generatedTokenMeta.length > 0) {
    tokens = generatedTokenMeta.map(({charStart: _charStart, charEnd: _charEnd, ...token}) => token);
  }
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
  const highlightSourceTokens = tokens.length > 0
    ? buildTokenMetaFromTokens(tokens)
    : generatedTokenMeta;
  const highlights = normalizeCaptionHighlights(labelRecord?.highlights, highlightSourceTokens);
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
            ...(highlights.length ? {highlights} : {}),
          },
        }
      : highlights.length
        ? {
            label: {
              highlights,
            },
          }
        : {}
    ),
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
      const start = asTimeSeconds(record.start);
      const end = asTimeSeconds(record.end);
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
  const explicitSegments = normalizeTimelineItems(payload.segments, null) as Array<{start: number; end: number}>;
  const normalizedSegments = explicitSegments.length
    ? explicitSegments
    : normalizedCaptions.map((caption) => ({start: caption.start, end: caption.end}));
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
  const subtitleTheme = normalizeSubtitleTheme(payload.subtitleTheme);
  if (subtitleTheme) {
    inputProps.subtitleTheme = subtitleTheme;
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
