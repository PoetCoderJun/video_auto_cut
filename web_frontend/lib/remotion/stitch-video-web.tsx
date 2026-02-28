import React, {useMemo} from "react";
import {AbsoluteFill, Sequence, useCurrentFrame} from "remotion";
import {Video} from "@remotion/media";

export type RenderCaption = {
  index: number;
  start: number;
  end: number;
  text: string;
};

export type RenderTopic = {
  title: string;
  summary: string;
  start: number;
  end: number;
};

export type RenderSegment = {
  start: number;
  end: number;
};

export type SubtitleTheme =
  | "text-black"
  | "text-white"
  | "box-white-on-black"
  | "box-black-on-white";

export type StitchVideoWebProps = {
  src: string;
  captions: RenderCaption[];
  topics: RenderTopic[];
  segments: RenderSegment[];
  fps: number;
  width: number;
  height: number;
  subtitleTheme?: SubtitleTheme;
};

type TimelineSegment = {
  from: number;
  durationInFrames: number;
  trimBefore: number;
  cutStart: number;
  cutEnd: number;
};

const clamp = (value: number, min = 0, max = 1): number => {
  if (value < min) return min;
  if (value > max) return max;
  return value;
};

/** Typography scales by short edge so portrait / high-res variants remain readable. */
const BASE_SHORT_EDGE = 1080;
const MIN_UI_SCALE = 0.6;
const MAX_UI_SCALE = 2.4;
const SUBTITLE_FONT_SIZE_BASE = 44;
const SUBTITLE_MAX_WIDTH_RATIO = 0.9;
const SUBTITLE_SAFE_WIDTH_RATIO = 0.86;
const CJK_RE = /[\u2E80-\u9FFF\uF900-\uFAFF\u3040-\u30FF\uAC00-\uD7AF]/;
const BREAK_PUNCT_RE = /[，。！？；：、,.!?;:]/;

const charUnits = (char: string): number => {
  if (char === " " || char === "\t") return 0.35;
  if (BREAK_PUNCT_RE.test(char)) return 0.6;
  if (/[0-9A-Za-z]/.test(char)) return 0.56;
  if (CJK_RE.test(char)) return 1;
  return 0.75;
};

const measureUnits = (text: string): number => {
  let total = 0;
  for (const char of text) total += charUnits(char);
  return total;
};

const findLastBreakPos = (text: string): number => {
  for (let i = text.length - 1; i >= 0; i -= 1) {
    if (BREAK_PUNCT_RE.test(text[i])) return i + 1;
  }
  return -1;
};

const wrapSoftLine = (text: string, maxUnits: number): string[] => {
  if (!text) return [""];

  const wrapped: string[] = [];
  let line = "";
  let units = 0;
  let lastBreakPos = -1;
  const minBreakPrefix = Math.max(4, Math.floor(maxUnits * 0.45));

  for (const char of text) {
    const nextUnits = charUnits(char);
    if (line && BREAK_PUNCT_RE.test(char) && units + nextUnits > maxUnits) {
      line += char;
      units += nextUnits;
      lastBreakPos = line.length;
      wrapped.push(line);
      line = "";
      units = 0;
      lastBreakPos = -1;
      continue;
    }
    while (line && units + nextUnits > maxUnits) {
      const breakPos = lastBreakPos >= minBreakPrefix ? lastBreakPos : -1;
      if (breakPos > 0 && breakPos < line.length) {
        wrapped.push(line.slice(0, breakPos));
        line = line.slice(breakPos).trimStart();
      } else {
        wrapped.push(line);
        line = "";
      }
      units = measureUnits(line);
      lastBreakPos = findLastBreakPos(line);
    }

    if (!line && char === " ") continue;
    line += char;
    units += nextUnits;
    if (BREAK_PUNCT_RE.test(char)) lastBreakPos = line.length;
  }

  if (line) wrapped.push(line);
  return wrapped.length > 0 ? wrapped : [""];
};

const wrapCaptionText = (rawText: string, width: number, fontSize: number): string => {
  const normalized = (rawText || "").replace(/\r\n?/g, "\n").trim();
  if (!normalized) return "";

  const usableWidth = Math.max(280, width * SUBTITLE_MAX_WIDTH_RATIO);
  const maxUnits = Math.max(
    10,
    Math.floor((usableWidth * SUBTITLE_SAFE_WIDTH_RATIO) / fontSize)
  );

  const lines: string[] = [];
  for (const hardLine of normalized.split("\n")) {
    const trimmed = hardLine.trim();
    if (!trimmed) continue;
    lines.push(...wrapSoftLine(trimmed, maxUnits));
  }
  return lines.join("\n");
};

const round = (n: number) => Math.round(n);

export const StitchVideoWeb: React.FC<StitchVideoWebProps> = ({
  src,
  captions,
  topics,
  segments,
  fps,
  width,
  height,
  subtitleTheme = "box-white-on-black",
}) => {
  const frame = useCurrentFrame();
  const shortEdge = Math.max(1, Math.min(width, height));
  const scale = clamp(shortEdge / BASE_SHORT_EDGE, MIN_UI_SCALE, MAX_UI_SCALE);
  const subtitleFontSize = round(SUBTITLE_FONT_SIZE_BASE * scale);

  const scaledStyles = useMemo(() => {
    return {
      subtitleWrap: {
        position: "absolute" as const,
        left: 0,
        right: 0,
        bottom: round(80 * scale),
        display: "flex" as const,
        justifyContent: "center" as const,
        pointerEvents: "none" as const,
        paddingLeft: round(24 * scale),
        paddingRight: round(24 * scale),
      },
      subtitleBox: {
        color: "#ffffff",
        fontSize: subtitleFontSize,
        fontWeight: 700,
        lineHeight: 1.35,
        textAlign: "center" as const,
        textShadow: "0 1px 1px rgba(0, 0, 0, 0.75), 0 0 2px rgba(0, 0, 0, 0.55)",
        whiteSpace: "pre" as const,
        wordBreak: "keep-all" as const,
        overflowWrap: "normal" as const,
        maxWidth: "90%",
      },
      chapterWrap: {
        position: "absolute" as const,
        top: round(28 * scale),
        left: round(28 * scale),
        right: round(28 * scale),
        pointerEvents: "none" as const,
      },
      chapterCard: {
        display: "inline-flex" as const,
        flexDirection: "column" as const,
        gap: round(6 * scale),
        minWidth: round(300 * scale),
        maxWidth: "70%",
        padding: `${round(12 * scale)}px ${round(14 * scale)}px`,
        borderRadius: round(12 * scale),
        backgroundColor: "rgba(8, 12, 20, 0.74)",
        border: "1px solid rgba(255, 255, 255, 0.2)",
      },
      chapterMeta: {
        fontSize: round(18 * scale),
        fontWeight: 700,
        color: "#8ee0ff",
      },
      chapterTitle: {
        fontSize: round(32 * scale),
        lineHeight: 1.2,
        fontWeight: 800,
        color: "#ffffff",
      },
      progressWrap: {
        position: "absolute" as const,
        left: round(28 * scale),
        right: round(28 * scale),
        bottom: round(14 * scale),
        height: round(42 * scale),
        pointerEvents: "none" as const,
      },
      progressTrack: {
        position: "relative" as const,
        width: "100%",
        height: "100%",
        borderRadius: round(12 * scale),
        overflow: "hidden" as const,
        backgroundColor: "rgba(16, 22, 30, 0.42)",
        border: "1px solid rgba(255, 255, 255, 0.22)",
      },
      progressFill: {
        position: "absolute" as const,
        left: 0,
        top: 0,
        bottom: 0,
        width: "0%",
        background: "linear-gradient(90deg, rgba(29, 217, 255, 0.58), rgba(66, 240, 180, 0.45))",
      },
      progressSegment: {
        position: "absolute" as const,
        top: 0,
        bottom: 0,
        display: "flex" as const,
        alignItems: "center" as const,
        justifyContent: "center" as const,
        overflow: "hidden" as const,
        borderRight: "1px solid rgba(255, 255, 255, 0.2)",
      },
      progressSegmentLabel: {
        maxWidth: "94%",
        padding: `0 ${round(4 * scale)}px`,
        fontSize: round(13 * scale),
        fontWeight: 700,
        lineHeight: 1.2,
        whiteSpace: "nowrap" as const,
        overflow: "hidden" as const,
        textOverflow: "ellipsis" as const,
        color: "rgba(238, 244, 255, 0.9)",
      },
    };
  }, [scale, subtitleFontSize]);

  const wrappedCaptions = useMemo(
    () =>
      captions.map((caption) => ({
        ...caption,
        wrappedText: wrapCaptionText(caption.text, width, subtitleFontSize),
      })),
    [captions, width, subtitleFontSize]
  );

  const timelineSegments = useMemo((): TimelineSegment[] => {
    const normalized = (segments || [])
      .filter((segment) => Number.isFinite(segment.start) && Number.isFinite(segment.end) && segment.end > segment.start)
      .slice()
      .sort((a, b) => a.start - b.start);
    let cursorFrames = 0;
    let cursorCutSec = 0;
    return normalized.map((segment) => {
      const trimBefore = Math.max(0, Math.floor(segment.start * fps));
      const trimAfterFrame = Math.max(trimBefore + 1, Math.ceil(segment.end * fps));
      const durationInFrames = Math.max(1, trimAfterFrame - trimBefore);
      const exactDurationSec = Math.max(0, segment.end - segment.start);
      const item = {
        from: cursorFrames,
        durationInFrames,
        trimBefore,
        cutStart: cursorCutSec,
        cutEnd: cursorCutSec + exactDurationSec,
      };
      cursorFrames += durationInFrames;
      cursorCutSec += exactDurationSec;
      return item;
    });
  }, [segments, fps]);

  const mappedTimelineTime = useMemo(() => {
    if (timelineSegments.length === 0) {
      return frame / fps;
    }
    const last = timelineSegments[timelineSegments.length - 1];
    const totalFrames = last.from + last.durationInFrames;
    if (frame <= 0) return 0;
    if (frame >= totalFrames) return last.cutEnd;

    for (const seg of timelineSegments) {
      const segEndFrame = seg.from + seg.durationInFrames;
      if (frame < segEndFrame) {
        const inSegFrame = frame - seg.from;
        const ratio = seg.durationInFrames > 0 ? inSegFrame / seg.durationInFrames : 0;
        return seg.cutStart + (seg.cutEnd - seg.cutStart) * clamp(ratio, 0, 1);
      }
    }
    return last.cutEnd;
  }, [frame, fps, timelineSegments]);

  const t = mappedTimelineTime;
  const activeCaption = wrappedCaptions.find((caption) => t >= caption.start && t < caption.end);

  const normalizedTopics = useMemo(() => {
    return (topics || [])
      .filter((topic) => Number.isFinite(topic.start) && Number.isFinite(topic.end) && topic.end > topic.start)
      .slice()
      .sort((a, b) => a.start - b.start);
  }, [topics]);

  const activeTopicIndex = normalizedTopics.findIndex((topic, index) => {
    const isLast = index === normalizedTopics.length - 1;
    if (isLast) {
      return t >= topic.start && t <= topic.end;
    }
    return t >= topic.start && t < topic.end;
  });
  const activeTopic = activeTopicIndex >= 0 ? normalizedTopics[activeTopicIndex] : null;
  const activeTopicLabel = activeTopic ? `${activeTopicIndex + 1}/${normalizedTopics.length}` : "";

  const topicDurationEnd = normalizedTopics.reduce((max, item) => Math.max(max, item.end), 0);
  const captionDurationEnd = captions.reduce((max, item) => Math.max(max, item.end), 0);
  const segmentDurationEnd =
    timelineSegments.length > 0 ? timelineSegments[timelineSegments.length - 1].cutEnd : 0;
  const totalDuration = Math.max(1, topicDurationEnd, captionDurationEnd, segmentDurationEnd);
  const progress = clamp(t / totalDuration);

  const topicSegments = useMemo(() => {
    return normalizedTopics
      .map((topic, index) => {
        const startRatio = clamp(topic.start / totalDuration);
        const endRatio = clamp(topic.end / totalDuration);
        if (endRatio <= startRatio) {
          return null;
        }
        return {
          title: topic.title,
          startRatio,
          endRatio,
          index,
        };
      })
      .filter((item): item is {title: string; startRatio: number; endRatio: number; index: number} => item !== null);
  }, [normalizedTopics, totalDuration]);

  const subtitleStyleOverrides = useMemo(() => {
    const p = round(8 * scale);
    const px = round(14 * scale);
    const br = round(10 * scale);
    switch (subtitleTheme) {
      case "text-black":
        return {
          color: "#111111",
          backgroundColor: "transparent",
          padding: "0",
          borderRadius: 0,
          textShadow: "0 1px 1px rgba(255, 255, 255, 0.45)",
        } as React.CSSProperties;
      case "text-white":
        return {
          color: "#ffffff",
          backgroundColor: "transparent",
          padding: "0",
          borderRadius: 0,
          textShadow: "0 1px 2px rgba(0, 0, 0, 0.75)",
        } as React.CSSProperties;
      case "box-black-on-white":
        return {
          color: "#111111",
          backgroundColor: "rgba(255, 255, 255, 0.92)",
          padding: `${p}px ${px}px`,
          borderRadius: br,
          maxWidth: "90%",
          textShadow: "none",
        } as React.CSSProperties;
      case "box-white-on-black":
      default:
        return {
          color: "#ffffff",
          backgroundColor: "rgba(0, 0, 0, 0.82)",
          padding: `${p}px ${px}px`,
          borderRadius: br,
          maxWidth: "90%",
          textShadow: "none",
        } as React.CSSProperties;
    }
  }, [subtitleTheme, scale]);

  return (
    <AbsoluteFill style={{backgroundColor: "black"}}>
      {timelineSegments.map((segment) => (
        <Sequence key={`${segment.from}-${segment.trimBefore}`} from={segment.from} durationInFrames={segment.durationInFrames}>
          <Video src={src} trimBefore={segment.trimBefore} style={{width: "100%", height: "100%", objectFit: "contain"}} />
        </Sequence>
      ))}

      {activeTopic ? (
        <div style={scaledStyles.chapterWrap}>
          <div style={scaledStyles.chapterCard}>
            <div style={scaledStyles.chapterMeta}>CHAPTER {activeTopicLabel}</div>
            <div style={scaledStyles.chapterTitle}>{activeTopic.title}</div>
          </div>
        </div>
      ) : null}

      <div style={scaledStyles.subtitleWrap}>
        <div style={{...scaledStyles.subtitleBox, ...subtitleStyleOverrides}}>{activeCaption ? activeCaption.wrappedText : ""}</div>
      </div>

      <div style={scaledStyles.progressWrap}>
        <div style={scaledStyles.progressTrack}>
          <div style={{...scaledStyles.progressFill, width: `${progress * 100}%`}} />
          {topicSegments.map((segment) => (
            <div
              key={`segment-${segment.index}-${segment.startRatio}-${segment.endRatio}`}
              style={{
                ...scaledStyles.progressSegment,
                left: `${segment.startRatio * 100}%`,
                width: `${(segment.endRatio - segment.startRatio) * 100}%`,
                backgroundColor:
                  segment.index === activeTopicIndex ? "rgba(255, 255, 255, 0.08)" : "rgba(255, 255, 255, 0.02)",
              }}
            >
              <div
                style={{
                  ...scaledStyles.progressSegmentLabel,
                  color: segment.index === activeTopicIndex ? "#ffffff" : "rgba(238, 244, 255, 0.84)",
                }}
              >
                {segment.title}
              </div>
            </div>
          ))}
        </div>
      </div>
    </AbsoluteFill>
  );
};
