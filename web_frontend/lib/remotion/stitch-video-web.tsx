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
};

const clamp = (value: number, min = 0, max = 1): number => {
  if (value < min) return min;
  if (value > max) return max;
  return value;
};

const SUBTITLE_FONT_SIZE = 44;
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

const wrapCaptionText = (rawText: string, width: number): string => {
  const normalized = (rawText || "").replace(/\r\n?/g, "\n").trim();
  if (!normalized) return "";

  const usableWidth = Math.max(280, width * SUBTITLE_MAX_WIDTH_RATIO);
  const maxUnits = Math.max(
    10,
    Math.floor((usableWidth * SUBTITLE_SAFE_WIDTH_RATIO) / SUBTITLE_FONT_SIZE)
  );

  const lines: string[] = [];
  for (const hardLine of normalized.split("\n")) {
    const trimmed = hardLine.trim();
    if (!trimmed) continue;
    lines.push(...wrapSoftLine(trimmed, maxUnits));
  }
  return lines.join("\n");
};

const subtitleWrap: React.CSSProperties = {
  position: "absolute",
  left: 0,
  right: 0,
  bottom: 80,
  display: "flex",
  justifyContent: "center",
  pointerEvents: "none",
  paddingLeft: 24,
  paddingRight: 24,
};

const subtitleBox: React.CSSProperties = {
  color: "#ffffff",
  fontSize: SUBTITLE_FONT_SIZE,
  fontWeight: 700,
  lineHeight: 1.35,
  textAlign: "center",
  textShadow: "0 1px 1px rgba(0, 0, 0, 0.75), 0 0 2px rgba(0, 0, 0, 0.55)",
  whiteSpace: "pre",
  wordBreak: "keep-all",
  overflowWrap: "normal",
  maxWidth: "90%",
};

const chapterWrap: React.CSSProperties = {
  position: "absolute",
  top: 28,
  left: 28,
  right: 28,
  pointerEvents: "none",
};

const chapterCard: React.CSSProperties = {
  display: "inline-flex",
  flexDirection: "column",
  gap: 6,
  minWidth: 300,
  maxWidth: "70%",
  padding: "12px 14px",
  borderRadius: 12,
  backgroundColor: "rgba(8, 12, 20, 0.74)",
  border: "1px solid rgba(255, 255, 255, 0.2)",
};

const chapterMeta: React.CSSProperties = {
  fontSize: 18,
  fontWeight: 700,
  color: "#8ee0ff",
};

const chapterTitle: React.CSSProperties = {
  fontSize: 32,
  lineHeight: 1.2,
  fontWeight: 800,
  color: "#ffffff",
};

const progressWrap: React.CSSProperties = {
  position: "absolute",
  left: 28,
  right: 28,
  bottom: 14,
  height: 42,
  pointerEvents: "none",
};

const progressTrack: React.CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
  borderRadius: 12,
  overflow: "hidden",
  backgroundColor: "rgba(16, 22, 30, 0.42)",
  border: "1px solid rgba(255, 255, 255, 0.22)",
};

const progressFill: React.CSSProperties = {
  position: "absolute",
  left: 0,
  top: 0,
  bottom: 0,
  width: "0%",
  background: "linear-gradient(90deg, rgba(29, 217, 255, 0.58), rgba(66, 240, 180, 0.45))",
};

const progressSegment: React.CSSProperties = {
  position: "absolute",
  top: 0,
  bottom: 0,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  overflow: "hidden",
  borderRight: "1px solid rgba(255, 255, 255, 0.2)",
};

const progressSegmentLabel: React.CSSProperties = {
  maxWidth: "94%",
  padding: "0 4px",
  fontSize: 13,
  fontWeight: 700,
  lineHeight: 1.2,
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
  color: "rgba(238, 244, 255, 0.9)",
};

export const StitchVideoWeb: React.FC<StitchVideoWebProps> = ({
  src,
  captions,
  topics,
  segments,
  fps,
  width,
  subtitleTheme = "box-white-on-black",
}) => {
  const frame = useCurrentFrame();
  const t = frame / fps;

  const wrappedCaptions = useMemo(
    () =>
      captions.map((caption) => ({
        ...caption,
        wrappedText: wrapCaptionText(caption.text, width),
      })),
    [captions, width]
  );
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

  const timelineSegments = useMemo((): TimelineSegment[] => {
    const normalized = (segments || [])
      .filter((segment) => Number.isFinite(segment.start) && Number.isFinite(segment.end) && segment.end > segment.start)
      .slice()
      .sort((a, b) => a.start - b.start);
    let cursor = 0;
    return normalized.map((segment) => {
      const trimBefore = Math.max(0, Math.floor(segment.start * fps));
      const trimAfterFrame = Math.max(trimBefore + 1, Math.ceil(segment.end * fps));
      const durationInFrames = Math.max(1, trimAfterFrame - trimBefore);
      const item = {
        from: cursor,
        durationInFrames,
        trimBefore,
      };
      cursor += durationInFrames;
      return item;
    });
  }, [segments, fps]);

  const topicDurationEnd = normalizedTopics.length > 0 ? normalizedTopics[normalizedTopics.length - 1].end : 0;
  const captionDurationEnd = captions.length > 0 ? captions[captions.length - 1].end : 0;
  const totalDuration = Math.max(1, topicDurationEnd, captionDurationEnd);
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

  const subtitleStyle = useMemo(() => {
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
          padding: "8px 14px",
          borderRadius: 10,
          maxWidth: "90%",
          textShadow: "none",
        } as React.CSSProperties;
      case "box-white-on-black":
      default:
        return {
          color: "#ffffff",
          backgroundColor: "rgba(0, 0, 0, 0.82)",
          padding: "8px 14px",
          borderRadius: 10,
          maxWidth: "90%",
          textShadow: "none",
        } as React.CSSProperties;
    }
  }, [subtitleTheme]);

  return (
    <AbsoluteFill style={{backgroundColor: "black"}}>
      {timelineSegments.map((segment) => (
        <Sequence key={`${segment.from}-${segment.trimBefore}`} from={segment.from} durationInFrames={segment.durationInFrames}>
          <Video src={src} trimBefore={segment.trimBefore} style={{width: "100%", height: "100%", objectFit: "contain"}} />
        </Sequence>
      ))}

      {activeTopic ? (
        <div style={chapterWrap}>
          <div style={chapterCard}>
            <div style={chapterMeta}>CHAPTER {activeTopicLabel}</div>
            <div style={chapterTitle}>{activeTopic.title}</div>
          </div>
        </div>
      ) : null}

      <div style={subtitleWrap}>
        <div style={{...subtitleBox, ...subtitleStyle}}>{activeCaption ? activeCaption.wrappedText : ""}</div>
      </div>

      <div style={progressWrap}>
        <div style={progressTrack}>
          <div style={{...progressFill, width: `${progress * 100}%`}} />
          {topicSegments.map((segment) => (
            <div
              key={`segment-${segment.index}-${segment.startRatio}-${segment.endRatio}`}
              style={{
                ...progressSegment,
                left: `${segment.startRatio * 100}%`,
                width: `${(segment.endRatio - segment.startRatio) * 100}%`,
                backgroundColor:
                  segment.index === activeTopicIndex ? "rgba(255, 255, 255, 0.08)" : "rgba(255, 255, 255, 0.02)",
              }}
            >
              <div
                style={{
                  ...progressSegmentLabel,
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
