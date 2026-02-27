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

/** 1080p 基准，横竖屏统一用短边约束，竖屏时不会因 height 放大而溢出 */
const BASE_WIDTH = 1920;
const BASE_HEIGHT = 1080;
const SUBTITLE_FONT_SIZE_BASE = 44;
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

const wrapCaptionText = (rawText: string, width: number, fontSize: number): string => {
  const normalized = (rawText || '').replace(/\r\n?/g, '\n').trim();
  if (!normalized) {
    return '';
  }

  const usableWidth = Math.max(280, width * SUBTITLE_MAX_WIDTH_RATIO);
  const maxUnits = Math.max(
    10,
    Math.floor((usableWidth * SUBTITLE_SAFE_WIDTH_RATIO) / fontSize)
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

const round = (n: number) => Math.round(n);

export const StitchVideo: React.FC<StitchVideoProps> = ({src, captions, segments, topics, fps, width, height}) => {
  const frame = useCurrentFrame();
  const t = frame / fps;
  const scale = Math.min(width / BASE_WIDTH, height / BASE_HEIGHT);
  const subtitleFontSize = round(SUBTITLE_FONT_SIZE_BASE * scale);

  const scaledStyles = useMemo(() => {
    return {
      subtitleWrap: {
        position: 'absolute' as const,
        left: 0,
        right: 0,
        bottom: round(86 * scale),
        display: 'flex' as const,
        justifyContent: 'center' as const,
        pointerEvents: 'none' as const,
        paddingLeft: round(24 * scale),
        paddingRight: round(24 * scale),
      },
      subtitleBox: {
        color: '#ffffff',
        fontSize: subtitleFontSize,
        fontWeight: 700,
        lineHeight: 1.35,
        textAlign: 'center' as const,
        textShadow: '0 2px 10px rgba(0, 0, 0, 0.8)',
        whiteSpace: 'pre' as const,
        wordBreak: 'keep-all' as const,
        overflowWrap: 'normal' as const,
        maxWidth: '90%',
      },
      chapterWrap: {
        position: 'absolute' as const,
        top: round(30 * scale),
        left: round(30 * scale),
        right: round(30 * scale),
        pointerEvents: 'none' as const,
        display: 'flex' as const,
        justifyContent: 'flex-start' as const,
      },
      chapterCard: {
        display: 'inline-flex' as const,
        flexDirection: 'column' as const,
        gap: round(6 * scale),
        minWidth: round(320 * scale),
        maxWidth: '68%',
        padding: `${round(14 * scale)}px ${round(16 * scale)}px ${round(14 * scale)}px ${round(18 * scale)}px`,
        borderRadius: round(14 * scale),
        background: 'linear-gradient(125deg, rgba(9, 13, 25, 0.88), rgba(9, 13, 25, 0.62))',
        border: '1px solid rgba(255, 255, 255, 0.14)',
        boxShadow: '0 10px 40px rgba(0, 0, 0, 0.35)',
      },
      chapterMeta: {
        fontSize: round(20 * scale),
        fontWeight: 700,
        color: '#8ee0ff',
        letterSpacing: 0.5,
      },
      chapterTitle: {
        fontSize: round(34 * scale),
        lineHeight: 1.2,
        fontWeight: 800,
        color: '#ffffff',
        textShadow: '0 2px 8px rgba(0,0,0,0.45)',
      },
      progressWrap: {
        position: 'absolute' as const,
        left: round(30 * scale),
        right: round(30 * scale),
        bottom: round(16 * scale),
        height: round(60 * scale),
        display: 'flex' as const,
        alignItems: 'center' as const,
        pointerEvents: 'none' as const,
      },
      progressGlass: {
        position: 'relative' as const,
        width: '100%',
        height: round(46 * scale),
        borderRadius: round(16 * scale),
        overflow: 'hidden' as const,
        background: 'linear-gradient(110deg, rgba(18, 24, 34, 0.45), rgba(18, 24, 34, 0.25))',
        border: '1px solid rgba(255, 255, 255, 0.2)',
        boxShadow: '0 8px 20px rgba(0,0,0,0.28), inset 0 0 20px rgba(255,255,255,0.06)',
        backdropFilter: 'blur(6px)',
      },
      progressGlassFill: {
        position: 'absolute' as const,
        left: 0,
        top: 0,
        bottom: 0,
        width: '0%',
        transformOrigin: 'left center',
        background: 'linear-gradient(90deg, rgba(29, 217, 255, 0.58), rgba(66, 240, 180, 0.45))',
        boxShadow: '0 0 20px rgba(29, 217, 255, 0.34)',
        pointerEvents: 'none' as const,
      },
      progressSegment: {
        position: 'absolute' as const,
        top: 0,
        bottom: 0,
        display: 'flex' as const,
        alignItems: 'center' as const,
        justifyContent: 'center' as const,
        overflow: 'hidden' as const,
        borderRight: '1px solid rgba(255,255,255,0.18)',
      },
      progressSegmentLabel: {
        maxWidth: '94%',
        padding: `0px ${round(4 * scale)}px`,
        fontSize: round(14 * scale),
        fontWeight: 700,
        lineHeight: 1.2,
        whiteSpace: 'nowrap' as const,
        overflow: 'hidden' as const,
        textOverflow: 'ellipsis' as const,
        letterSpacing: 0.15,
        color: 'rgba(238, 244, 255, 0.9)',
        textShadow: '0 1px 3px rgba(0,0,0,0.45)',
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
        <div style={scaledStyles.chapterWrap}>
          <div style={scaledStyles.chapterCard}>
            <div style={scaledStyles.chapterMeta}>CHAPTER {activeTopicLabel}</div>
            <div style={scaledStyles.chapterTitle}>{activeTopic.title}</div>
          </div>
        </div>
      ) : null}
      <div style={scaledStyles.subtitleWrap}>
        <div style={scaledStyles.subtitleBox}>{active ? active.wrappedText : ''}</div>
      </div>
      <div style={scaledStyles.progressWrap}>
        <div style={scaledStyles.progressGlass}>
          <div style={{...scaledStyles.progressGlassFill, width: `${progress * 100}%`}} />
          {topicSegments.map((segment) => {
            const left = segment.startRatio * 100;
            const segWidth = (segment.endRatio - segment.startRatio) * 100;
            const isActive = segment.index === activeTopicIndex;
            return (
              <div
                key={`segment-${segment.index}-${segment.startRatio}-${segment.endRatio}`}
                style={{
                  ...scaledStyles.progressSegment,
                  left: `${left}%`,
                  width: `${segWidth}%`,
                  background: isActive
                    ? 'linear-gradient(90deg, rgba(255, 255, 255, 0.08), rgba(255,255,255,0.04))'
                    : 'linear-gradient(90deg, rgba(255, 255, 255, 0.035), rgba(255,255,255,0.015))',
                  borderRightColor: 'rgba(255,255,255,0.22)',
                  zIndex: 1,
                }}
              >
                <div
                  style={{
                    ...scaledStyles.progressSegmentLabel,
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
