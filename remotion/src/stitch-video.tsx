import React, {useMemo} from 'react';
import {Video} from '@remotion/media';
import {AbsoluteFill, Sequence, staticFile, useCurrentFrame} from 'remotion';

export type Caption = {
  start: number;
  end: number;
  text: string;
};

export type StitchVideoProps = {
  src: string;
  captions: Caption[];
  segments: Segment[];
  topics: Topic[];
  fps: number;
  width: number;
  height: number;
};

export type Topic = {
  title: string;
  summary: string;
  start: number;
  end: number;
};

export type Segment = {
  start: number;
  end: number;
};

type TimelineSegment = {
  from: number;
  durationInFrames: number;
  trimBefore: number;
};

const clamp = (value: number, min = 0, max = 1): number => {
  if (value < min) {
    return min;
  }
  if (value > max) {
    return max;
  }
  return value;
};

const SUBTITLE_FONT_SIZE = 44;
const SUBTITLE_MAX_WIDTH_RATIO = 0.9;
const SUBTITLE_SAFE_WIDTH_RATIO = 0.86;
const CJK_RE = /[\u2E80-\u9FFF\uF900-\uFAFF\u3040-\u30FF\uAC00-\uD7AF]/;
const BREAK_PUNCT_RE = /[，。！？；：、,.!?;:]/;

const charUnits = (char: string): number => {
  if (char === ' ' || char === '\t') {
    return 0.35;
  }
  if (BREAK_PUNCT_RE.test(char)) {
    return 0.6;
  }
  if (/[0-9A-Za-z]/.test(char)) {
    return 0.56;
  }
  if (CJK_RE.test(char)) {
    return 1;
  }
  return 0.75;
};

const measureUnits = (text: string): number => {
  let total = 0;
  for (const char of text) {
    total += charUnits(char);
  }
  return total;
};

const findLastBreakPos = (text: string): number => {
  for (let i = text.length - 1; i >= 0; i -= 1) {
    if (BREAK_PUNCT_RE.test(text[i])) {
      return i + 1;
    }
  }
  return -1;
};

const wrapSoftLine = (text: string, maxUnits: number): string[] => {
  if (!text) {
    return [''];
  }

  const wrapped: string[] = [];
  let line = '';
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
      line = '';
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
        line = '';
      }
      units = measureUnits(line);
      lastBreakPos = findLastBreakPos(line);
    }

    if (!line && char === ' ') {
      continue;
    }
    line += char;
    units += nextUnits;
    if (BREAK_PUNCT_RE.test(char)) {
      lastBreakPos = line.length;
    }
  }

  if (line) {
    wrapped.push(line);
  }
  return wrapped.length > 0 ? wrapped : [''];
};

const wrapCaptionText = (rawText: string, width: number): string => {
  const normalized = (rawText || '').replace(/\r\n?/g, '\n').trim();
  if (!normalized) {
    return '';
  }

  const usableWidth = Math.max(280, width * SUBTITLE_MAX_WIDTH_RATIO);
  const maxUnits = Math.max(
    10,
    Math.floor((usableWidth * SUBTITLE_SAFE_WIDTH_RATIO) / SUBTITLE_FONT_SIZE)
  );

  const finalLines: string[] = [];
  for (const hardLine of normalized.split('\n')) {
    const trimmed = hardLine.trim();
    if (!trimmed) {
      continue;
    }
    finalLines.push(...wrapSoftLine(trimmed, maxUnits));
  }

  return finalLines.join('\n');
};

const subtitleWrap: React.CSSProperties = {
  position: 'absolute',
  left: 0,
  right: 0,
  bottom: 86,
  display: 'flex',
  justifyContent: 'center',
  pointerEvents: 'none',
  paddingLeft: 24,
  paddingRight: 24,
};

const subtitleBox: React.CSSProperties = {
  color: '#ffffff',
  fontSize: SUBTITLE_FONT_SIZE,
  fontWeight: 700,
  lineHeight: 1.35,
  textAlign: 'center',
  textShadow: '0 2px 10px rgba(0, 0, 0, 0.8)',
  whiteSpace: 'pre',
  wordBreak: 'keep-all',
  overflowWrap: 'normal',
  maxWidth: '90%',
};

const chapterWrap: React.CSSProperties = {
  position: 'absolute',
  top: 30,
  left: 30,
  right: 30,
  pointerEvents: 'none',
  display: 'flex',
  justifyContent: 'flex-start',
};

const chapterCard: React.CSSProperties = {
  display: 'inline-flex',
  flexDirection: 'column',
  gap: 6,
  minWidth: 320,
  maxWidth: '68%',
  padding: '14px 16px 14px 18px',
  borderRadius: 14,
  background: 'linear-gradient(125deg, rgba(9, 13, 25, 0.88), rgba(9, 13, 25, 0.62))',
  border: '1px solid rgba(255, 255, 255, 0.14)',
  boxShadow: '0 10px 40px rgba(0, 0, 0, 0.35)',
};

const chapterMeta: React.CSSProperties = {
  fontSize: 20,
  fontWeight: 700,
  color: '#8ee0ff',
  letterSpacing: 0.5,
};

const chapterTitle: React.CSSProperties = {
  fontSize: 34,
  lineHeight: 1.2,
  fontWeight: 800,
  color: '#ffffff',
  textShadow: '0 2px 8px rgba(0,0,0,0.45)',
};

const progressWrap: React.CSSProperties = {
  position: 'absolute',
  left: 30,
  right: 30,
  bottom: 16,
  height: 60,
  display: 'flex',
  alignItems: 'center',
  pointerEvents: 'none',
};

const progressGlass: React.CSSProperties = {
  position: 'relative',
  width: '100%',
  height: 46,
  borderRadius: 16,
  overflow: 'hidden',
  background: 'linear-gradient(110deg, rgba(18, 24, 34, 0.45), rgba(18, 24, 34, 0.25))',
  border: '1px solid rgba(255, 255, 255, 0.2)',
  boxShadow: '0 8px 20px rgba(0,0,0,0.28), inset 0 0 20px rgba(255,255,255,0.06)',
  backdropFilter: 'blur(6px)',
};

const progressGlassFill: React.CSSProperties = {
  position: 'absolute',
  left: 0,
  top: 0,
  bottom: 0,
  width: '0%',
  transformOrigin: 'left center',
  background: 'linear-gradient(90deg, rgba(29, 217, 255, 0.58), rgba(66, 240, 180, 0.45))',
  boxShadow: '0 0 20px rgba(29, 217, 255, 0.34)',
  pointerEvents: 'none',
};

const progressSegment: React.CSSProperties = {
  position: 'absolute',
  top: 0,
  bottom: 0,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  overflow: 'hidden',
  borderRight: '1px solid rgba(255,255,255,0.18)',
};

const progressSegmentLabel: React.CSSProperties = {
  maxWidth: '94%',
  padding: '0px 4px',
  fontSize: 14,
  fontWeight: 700,
  lineHeight: 1.2,
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  letterSpacing: 0.15,
  color: 'rgba(238, 244, 255, 0.9)',
  textShadow: '0 1px 3px rgba(0,0,0,0.45)',
};

export const StitchVideo: React.FC<StitchVideoProps> = ({src, captions, segments, topics, fps, width}) => {
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
  const active = wrappedCaptions.find((c) => t >= c.start && t < c.end);
  const videoSrc = src ? staticFile(src) : '';
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

  const normalizedTopics = useMemo(() => {
    return (topics || [])
      .filter((topic) => Number.isFinite(topic.start) && Number.isFinite(topic.end) && topic.end > topic.start)
      .slice()
      .sort((a, b) => a.start - b.start);
  }, [topics]);

  const topicDurationEnd = normalizedTopics.length > 0 ? normalizedTopics[normalizedTopics.length - 1].end : 0;
  const captionDurationEnd = captions.length > 0 ? captions[captions.length - 1].end : 0;
  const totalDuration = Math.max(1, topicDurationEnd, captionDurationEnd);
  const progress = clamp(t / totalDuration);

  const activeTopicIndex = normalizedTopics.findIndex((topic, index) => {
    const isLast = index === normalizedTopics.length - 1;
    if (isLast) {
      return t >= topic.start && t <= topic.end;
    }
    return t >= topic.start && t < topic.end;
  });
  const activeTopic = activeTopicIndex >= 0 ? normalizedTopics[activeTopicIndex] : null;
  const activeTopicLabel = activeTopic ? `${activeTopicIndex + 1}/${normalizedTopics.length}` : '';
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

  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      {videoSrc ? (
        timelineSegments.length > 0 ? (
          timelineSegments.map((segment) => (
            <Sequence
              key={`${segment.from}-${segment.trimBefore}`}
              from={segment.from}
              durationInFrames={segment.durationInFrames}
            >
              <Video
                src={videoSrc}
                trimBefore={segment.trimBefore}
                style={{width: '100%', height: '100%', objectFit: 'contain'}}
              />
            </Sequence>
          ))
        ) : (
          <Video src={videoSrc} style={{width: '100%', height: '100%', objectFit: 'contain'}} />
        )
      ) : null}
      {activeTopic ? (
        <div style={chapterWrap}>
          <div style={chapterCard}>
            <div style={chapterMeta}>CHAPTER {activeTopicLabel}</div>
            <div style={chapterTitle}>{activeTopic.title}</div>
          </div>
        </div>
      ) : null}
      <div style={subtitleWrap}>
        <div style={subtitleBox}>{active ? active.wrappedText : ''}</div>
      </div>
      <div style={progressWrap}>
        <div style={progressGlass}>
          <div style={{...progressGlassFill, width: `${progress * 100}%`}} />
          {topicSegments.map((segment) => {
            const left = segment.startRatio * 100;
            const width = (segment.endRatio - segment.startRatio) * 100;
            const isActive = segment.index === activeTopicIndex;
            return (
              <div
                key={`segment-${segment.index}-${segment.startRatio}-${segment.endRatio}`}
                style={{
                  ...progressSegment,
                  left: `${left}%`,
                  width: `${width}%`,
                  background: isActive
                    ? 'linear-gradient(90deg, rgba(255, 255, 255, 0.08), rgba(255,255,255,0.04))'
                    : 'linear-gradient(90deg, rgba(255, 255, 255, 0.035), rgba(255,255,255,0.015))',
                  borderRightColor: 'rgba(255,255,255,0.22)',
                  zIndex: 1,
                }}
              >
                <div
                  style={{
                    ...progressSegmentLabel,
                    color: isActive ? '#ffffff' : 'rgba(238, 244, 255, 0.84)',
                    fontWeight: isActive ? 800 : 700,
                  }}
                >
                  {segment.title}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
