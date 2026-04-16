"use client";

import React, {useCallback, useEffect, useMemo, useRef, useState} from "react";

import type {WebRenderConfig} from "@/lib/api";
import {clamp} from "@/lib/utils";
import type {SubtitleTheme} from "@/lib/remotion/stitch-video-web";
import {type OverlayScaleControls} from "@/lib/remotion/overlay-controls";
import {getRenderConfigTotalDuration} from "@/lib/remotion/utils";

import {OverlayLayer} from "./export-frame-preview/overlay-layer";
import {PreviewPlayer} from "./export-frame-preview/preview-player";
import {useOverlayLayout} from "./export-frame-preview/use-overlay-layout";

type ExportFramePreviewProps = {
  config: WebRenderConfig | null;
  sourceFile: File | null;
  sourceUrlOverride?: string | null;
  emptyStateMode?: "message" | "blank";
  subtitleTheme: SubtitleTheme;
  previewTimeSec: number;
  onPreviewTimeChange?: (timeSec: number) => void;
  overlayControls: OverlayScaleControls;
};

type TimelineSegment = {
  start: number;
  end: number;
  cutStart: number;
  cutEnd: number;
};

const formatClockTime = (timeSec: number): string => {
  const safe = Math.max(0, Number.isFinite(timeSec) ? timeSec : 0);
  const minutes = Math.floor(safe / 60);
  const seconds = Math.floor(safe % 60);
  const tenths = Math.floor((safe % 1) * 10);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${tenths}`;
};

const STANDARD_ASPECT_RATIO_LABELS: Record<string, string> = {
  "1:1": "1:1",
  "9:16": "9:16",
  "17:30": "9:16",
  "16:9": "16:9",
  "427:240": "16:9",
  "21:9": "21:9",
  "43:18": "21:9",
  "64:27": "21:9",
};

const getGreatestCommonDivisor = (left: number, right: number): number => {
  let a = Math.abs(Math.round(left));
  let b = Math.abs(Math.round(right));
  while (b !== 0) {
    const next = a % b;
    a = b;
    b = next;
  }
  return Math.max(1, a);
};

const formatAspectRatio = (width: number, height: number): string => {
  if (!(width > 0) || !(height > 0)) return "Preview";
  const divisor = getGreatestCommonDivisor(width, height);
  const normalizedLabel = `${Math.round(width / divisor)}:${Math.round(height / divisor)}`;
  return STANDARD_ASPECT_RATIO_LABELS[normalizedLabel] ?? normalizedLabel;
};

const findActiveTopicIndexByStart = (
  topics: Array<{start: number}>,
  timeSec: number
): number => {
  if (!Number.isFinite(timeSec) || topics.length === 0) return -1;
  let activeIndex = -1;
  for (let index = 0; index < topics.length; index += 1) {
    if (timeSec >= topics[index].start) {
      activeIndex = index;
    } else {
      break;
    }
  }
  return activeIndex;
};

const buildTimelineSegments = (config: WebRenderConfig): TimelineSegment[] => {
  let cursor = 0;
  return config.input_props.segments
    .filter((segment) => Number.isFinite(segment.start) && Number.isFinite(segment.end) && segment.end > segment.start)
    .slice()
    .sort((a, b) => a.start - b.start)
    .map((segment) => {
      const duration = Math.max(0, segment.end - segment.start);
      const item = {
        start: segment.start,
        end: segment.end,
        cutStart: cursor,
        cutEnd: cursor + duration,
      };
      cursor += duration;
      return item;
    });
};

const mapPreviewTimeToSourceTime = (segments: TimelineSegment[], previewTimeSec: number): number => {
  if (segments.length === 0) return Math.max(0, previewTimeSec);
  const clamped = Math.max(0, previewTimeSec);
  for (const segment of segments) {
    if (clamped < segment.cutEnd) {
      return segment.start + (clamped - segment.cutStart);
    }
  }
  const last = segments[segments.length - 1];
  return last.end;
};

const getCenteredVideoStyle = (
  sourceDimensions: {width: number; height: number} | null,
  compositionWidth: number,
  compositionHeight: number
): React.CSSProperties => {
  const fallback: React.CSSProperties = {
    width: "100%",
    height: "100%",
    objectFit: "contain",
    objectPosition: "center center",
    display: "block",
    backgroundColor: "#020617",
  };

  if (!sourceDimensions) return fallback;

  const sourceAspect = sourceDimensions.width / sourceDimensions.height;
  const compositionAspect = compositionWidth / compositionHeight;
  if (!Number.isFinite(sourceAspect) || sourceAspect <= 0) return fallback;

  if (sourceAspect >= compositionAspect) {
    return {
      position: "absolute",
      left: 0,
      top: "50%",
      width: "100%",
      height: Math.round(compositionWidth / sourceAspect),
      transform: "translateY(-50%)",
      display: "block",
      backgroundColor: "#020617",
    };
  }

  return {
    position: "absolute",
    left: "50%",
    top: 0,
    width: Math.round(compositionHeight * sourceAspect),
    height: "100%",
    transform: "translateX(-50%)",
    display: "block",
    backgroundColor: "#020617",
  };
};

export default function ExportFramePreview({
  config,
  sourceFile,
  sourceUrlOverride = null,
  emptyStateMode = "message",
  subtitleTheme,
  previewTimeSec,
  onPreviewTimeChange,
  overlayControls,
}: ExportFramePreviewProps) {
  const [sourceUrl, setSourceUrl] = useState<string | null>(null);
  const [sourceDimensions, setSourceDimensions] = useState<{width: number; height: number} | null>(null);
  const [frameSize, setFrameSize] = useState({width: 0, height: 0});
  const [localPreviewTimeSec, setLocalPreviewTimeSec] = useState(previewTimeSec);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isScrubbing, setIsScrubbing] = useState(false);
  const [scrubTimeSec, setScrubTimeSec] = useState(previewTimeSec);
  const frameRef = useRef<HTMLDivElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const playbackFrameRef = useRef<number | null>(null);
  const wasPlayingBeforeScrubRef = useRef(false);

  useEffect(() => {
    if (!onPreviewTimeChange) {
      setLocalPreviewTimeSec(previewTimeSec);
    }
  }, [onPreviewTimeChange, previewTimeSec]);

  useEffect(() => {
    if (sourceUrlOverride) {
      setSourceUrl(sourceUrlOverride);
      return;
    }
    if (!sourceFile) {
      setSourceDimensions(null);
      setSourceUrl((previous) => {
        if (previous && previous.startsWith("blob:")) URL.revokeObjectURL(previous);
        return null;
      });
      return;
    }

    const nextUrl = URL.createObjectURL(sourceFile);
    setSourceUrl((previous) => {
      if (previous && previous.startsWith("blob:")) URL.revokeObjectURL(previous);
      return nextUrl;
    });

    return () => {
      URL.revokeObjectURL(nextUrl);
    };
  }, [sourceFile, sourceUrlOverride]);

  useEffect(() => {
    const element = frameRef.current;
    if (!element) return;

    const update = () => {
      const nextSize = {
        width: Math.round(element.clientWidth),
        height: Math.round(element.clientHeight),
      };
      setFrameSize((previous) =>
        previous.width === nextSize.width && previous.height === nextSize.height ? previous : nextSize
      );
    };

    update();

    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", update);
      return () => {
        window.removeEventListener("resize", update);
      };
    }

    const observer = new ResizeObserver(() => {
      update();
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, [config?.composition.height, config?.composition.width]);

  const totalDuration = useMemo(() => getRenderConfigTotalDuration(config), [config]);
  const resolvedPreviewTimeSec = onPreviewTimeChange ? previewTimeSec : localPreviewTimeSec;
  const clampedPreviewTime = clamp(resolvedPreviewTimeSec, 0, totalDuration);
  const displayedPreviewTime = isScrubbing ? scrubTimeSec : clampedPreviewTime;

  const commitPreviewTime = useCallback(
    (nextTimeSec: number) => {
      const clamped = clamp(nextTimeSec, 0, totalDuration);
      if (onPreviewTimeChange) {
        onPreviewTimeChange(clamped);
        return;
      }
      setLocalPreviewTimeSec(clamped);
    },
    [onPreviewTimeChange, totalDuration]
  );

  const timelineSegments = useMemo(() => (config ? buildTimelineSegments(config) : []), [config]);
  const sourceTime = useMemo(
    () => mapPreviewTimeToSourceTime(timelineSegments, clampedPreviewTime),
    [clampedPreviewTime, timelineSegments]
  );
  const displayedSourceTime = useMemo(
    () => mapPreviewTimeToSourceTime(timelineSegments, displayedPreviewTime),
    [displayedPreviewTime, timelineSegments]
  );

  useEffect(() => {
    setScrubTimeSec(clampedPreviewTime);
  }, [clampedPreviewTime]);

  useEffect(() => {
    setIsPlaying(false);
  }, [config, sourceUrl]);

  useEffect(() => {
    if (!isPlaying || isScrubbing) return;

    const playbackStartPreviewTime = clampedPreviewTime;
    const startedAt = performance.now();
    const tick = (now: number) => {
      const nextTimeSec = playbackStartPreviewTime + (now - startedAt) / 1000;
      if (nextTimeSec >= totalDuration) {
        commitPreviewTime(totalDuration);
        setIsPlaying(false);
        return;
      }
      commitPreviewTime(nextTimeSec);
      playbackFrameRef.current = window.requestAnimationFrame(tick);
    };

    playbackFrameRef.current = window.requestAnimationFrame(tick);
    return () => {
      if (playbackFrameRef.current !== null) {
        window.cancelAnimationFrame(playbackFrameRef.current);
        playbackFrameRef.current = null;
      }
    };
  }, [clampedPreviewTime, commitPreviewTime, isPlaying, isScrubbing, totalDuration]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !Number.isFinite(sourceTime)) return;
    const applyTime = () => {
      video.pause();
      const maxTime = Number.isFinite(video.duration) && video.duration > 0 ? Math.max(0, video.duration - 0.05) : sourceTime;
      const nextTime = clamp(sourceTime, 0, maxTime);
      if (Math.abs(video.currentTime - nextTime) > 0.033) {
        video.currentTime = nextTime;
      }
    };

    if (video.readyState >= 1) {
      applyTime();
      return;
    }

    video.addEventListener("loadedmetadata", applyTime, {once: true});
    return () => {
      video.removeEventListener("loadedmetadata", applyTime);
    };
  }, [sourceTime, sourceUrl]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const updateDimensions = () => {
      const width = Math.round(video.videoWidth || 0);
      const height = Math.round(video.videoHeight || 0);
      if (width <= 0 || height <= 0) return;
      setSourceDimensions((previous) =>
        previous?.width === width && previous?.height === height ? previous : {width, height}
      );
    };

    updateDimensions();
    video.addEventListener("loadedmetadata", updateDimensions);
    return () => {
      video.removeEventListener("loadedmetadata", updateDimensions);
    };
  }, [sourceUrl]);

  const {
    activeCaptionLayout,
    previewModel,
    subtitleRenderFontSize,
    subtitleRenderText,
    subtitleStyleOverrides,
  } = useOverlayLayout({
    clampedPreviewTime,
    config,
    overlayControls,
    subtitleTheme,
    totalDuration,
  });

  if (!config || !previewModel) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
        正在准备导出预览...
      </div>
    );
  }

  const compositionWidth = config.composition.width;
  const compositionHeight = config.composition.height;
  const currentFrame = Math.min(
    config.composition.durationInFrames,
    Math.max(0, Math.round(displayedPreviewTime * config.composition.fps))
  );
  const widthScale = frameSize.width > 0 ? frameSize.width / compositionWidth : 1;
  const heightScale = frameSize.height > 0 ? frameSize.height / compositionHeight : 1;
  const previewScale = Math.min(widthScale, heightScale);
  const centeredVideoStyle = getCenteredVideoStyle(sourceDimensions, compositionWidth, compositionHeight);
  const activeTopicTitle = previewModel.activeTopic?.title ?? "拖动时间轴查看不同章节";
  const togglePlayback = () => {
    if (isPlaying) {
      setIsPlaying(false);
      return;
    }
    if (clampedPreviewTime >= totalDuration) {
      commitPreviewTime(0);
    }
    setIsPlaying(true);
  };
  const handleTimelineChange = (nextValue: number) => {
    const nextTimeSec = clamp(nextValue, 0, totalDuration);
    setScrubTimeSec(nextTimeSec);
    commitPreviewTime(nextTimeSec);
  };
  const handleScrubStart = () => {
    wasPlayingBeforeScrubRef.current = isPlaying;
    setIsPlaying(false);
    setIsScrubbing(true);
  };
  const handleScrubEnd = () => {
    setIsScrubbing(false);
    if (wasPlayingBeforeScrubRef.current) {
      setIsPlaying(true);
    }
    wasPlayingBeforeScrubRef.current = false;
  };

  return (
    <div className="flex min-h-0 w-full flex-1 items-center justify-center">
      <div
        className="flex h-full min-h-0 w-full flex-col overflow-hidden rounded-[24px] border border-slate-200/80 bg-[linear-gradient(180deg,#fbfdff_0%,#f1f5f9_100%)] shadow-[0_24px_70px_-40px_rgba(15,23,42,0.28)]"
      >
        <div className="flex items-center justify-between border-b border-slate-200/80 px-4 py-3">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-slate-400">
              Export Preview
            </div>
            <div className="truncate text-sm font-semibold text-slate-900">{activeTopicTitle}</div>
          </div>
          <div className="ml-3 flex shrink-0 items-center gap-2">
            <span className="rounded-full bg-slate-900 px-2.5 py-1 text-[11px] font-medium text-white">
              F{currentFrame}
            </span>
            <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-500">
              {formatAspectRatio(compositionWidth, compositionHeight)}
            </span>
            <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-mono text-slate-500">
              {compositionWidth}x{compositionHeight}
            </span>
          </div>
        </div>

        <div
          ref={frameRef}
          className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-[radial-gradient(circle_at_top,rgba(148,163,184,0.22),transparent_38%),linear-gradient(180deg,#e2e8f0_0%,#cbd5e1_100%)] px-3 py-3"
        >
          <OverlayLayer
            activeCaptionLayout={activeCaptionLayout}
            compositionHeight={compositionHeight}
            compositionWidth={compositionWidth}
            displayedPreviewTime={displayedPreviewTime}
            displayedSourceTime={displayedSourceTime}
            formatClockTime={formatClockTime}
            previewModel={previewModel}
            previewScale={previewScale}
            subtitleRenderFontSize={subtitleRenderFontSize}
            subtitleRenderText={subtitleRenderText}
            subtitleStyleOverrides={subtitleStyleOverrides}
          >
            <PreviewPlayer
              centeredVideoStyle={centeredVideoStyle}
              emptyStateMode={emptyStateMode}
              sourceUrl={sourceUrl}
              videoRef={videoRef}
            />
          </OverlayLayer>
        </div>

        <div className="border-t border-slate-200/80 bg-white/90 px-4 py-3">
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={togglePlayback}
              className="inline-flex h-9 min-w-[64px] items-center justify-center rounded-full bg-slate-900 px-4 text-sm font-medium text-white transition hover:bg-slate-800"
            >
              {isPlaying ? "暂停" : "播放"}
            </button>
            <div className="min-w-[72px] text-[12px] font-mono text-slate-600">
              {formatClockTime(displayedPreviewTime)}
            </div>
            <input
              type="range"
              min={0}
              max={Math.max(totalDuration, 0.1)}
              step={0.01}
              value={displayedPreviewTime}
              onMouseDown={handleScrubStart}
              onTouchStart={handleScrubStart}
              onChange={(event) => handleTimelineChange(Number(event.currentTarget.value))}
              onMouseUp={handleScrubEnd}
              onTouchEnd={handleScrubEnd}
              onBlur={handleScrubEnd}
              className="h-2 min-w-[160px] flex-1 cursor-ew-resize accent-slate-900"
              aria-label="导出预览时间轴"
            />
            <div className="min-w-[72px] text-right text-[12px] font-mono text-slate-400">
              {formatClockTime(totalDuration)}
            </div>
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
            <span className="truncate">
              {previewModel.activeTopicLabel ? `章节 ${previewModel.activeTopicLabel}` : "章节未命中"} · {activeTopicTitle}
            </span>
            <span>原片映射 {formatClockTime(displayedSourceTime)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
