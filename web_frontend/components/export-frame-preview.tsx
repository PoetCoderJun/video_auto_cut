"use client";

import React, {useCallback, useEffect, useMemo, useRef, useState} from "react";

import {Player, type PlayerRef} from "@remotion/player";
import {preloadVideo} from "@remotion/preload";
import {Pause, Play} from "lucide-react";
import type {WebRenderConfig} from "@/lib/api";
import {clamp} from "@/lib/utils";
import type {SubtitleTheme} from "@/lib/remotion/stitch-video-web";
import {type OverlayScaleControls} from "@/lib/remotion/overlay-controls";
import {getRenderConfigTotalDuration} from "@/lib/remotion/utils";
import {StitchVideoWeb} from "@/lib/remotion/stitch-video-web";

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

const formatClockTime = (timeSec: number): string => {
  const safe = Math.max(0, Number.isFinite(timeSec) ? timeSec : 0);
  const minutes = Math.floor(safe / 60);
  const seconds = Math.floor(safe % 60);
  const tenths = Math.floor((safe % 1) * 10);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}.${tenths}`;
};

function ExportFramePreview({
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
  const [localPreviewTimeSec, setLocalPreviewTimeSec] = useState(previewTimeSec);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isScrubbing, setIsScrubbing] = useState(false);
  const [scrubTimeSec, setScrubTimeSec] = useState(previewTimeSec);
  const playerRef = useRef<PlayerRef>(null);
  const wasPlayingBeforeScrubRef = useRef(false);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (!onPreviewTimeChange) {
      setLocalPreviewTimeSec(previewTimeSec);
    }
  }, [onPreviewTimeChange, previewTimeSec]);

  useEffect(() => {
    if (sourceUrlOverride) {
      setSourceUrl(sourceUrlOverride);
      const cancelPreload = preloadVideo(sourceUrlOverride);
      return () => {
        cancelPreload();
      };
    }
    if (!sourceFile) {
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
    const cancelPreload = preloadVideo(nextUrl);

    return () => {
      cancelPreload();
      URL.revokeObjectURL(nextUrl);
    };
  }, [sourceFile, sourceUrlOverride]);

  const totalDuration = useMemo(() => getRenderConfigTotalDuration(config), [config]);
  const resolvedPreviewTimeSec = onPreviewTimeChange ? previewTimeSec : localPreviewTimeSec;
  const clampedPreviewTime = clamp(resolvedPreviewTimeSec, 0, totalDuration);
  const displayedPreviewTime = isScrubbing ? scrubTimeSec : clampedPreviewTime;

  const fps = config?.composition.fps ?? 30;

  const commitPreviewTime = useCallback(
    (nextTimeSec: number) => {
      const clamped = clamp(nextTimeSec, 0, totalDuration);
      if (onPreviewTimeChange) {
        onPreviewTimeChange(clamped);
      } else {
        setLocalPreviewTimeSec(clamped);
      }
    },
    [onPreviewTimeChange, totalDuration],
  );

  // Sync external time changes into Player seek
  useEffect(() => {
    if (!playerRef.current || isScrubbing) return;
    const targetFrame = Math.round(clampedPreviewTime * fps);
    const currentFrame = playerRef.current.getCurrentFrame();
    if (currentFrame !== targetFrame) {
      playerRef.current.seekTo(targetFrame);
    }
  }, [clampedPreviewTime, fps, isScrubbing]);

  // Poll Player frame to update displayed time and detect end-of-playback
  useEffect(() => {
    const tick = () => {
      if (!playerRef.current) {
        rafRef.current = requestAnimationFrame(tick);
        return;
      }
      const frame = playerRef.current.getCurrentFrame();
      const timeSec = frame / fps;

      if (!isScrubbing) {
        if (onPreviewTimeChange) {
          if (Math.abs(timeSec - previewTimeSec) > 0.05) {
            onPreviewTimeChange(timeSec);
          }
        } else {
          setLocalPreviewTimeSec((prev) => {
            if (Math.abs(timeSec - prev) > 0.05) return timeSec;
            return prev;
          });
        }
      }

      if (isPlaying && config) {
        const lastFrame = config.composition.durationInFrames - 1;
        if (frame >= lastFrame) {
          setIsPlaying(false);
        }
      }

      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isPlaying, isScrubbing, fps, onPreviewTimeChange, previewTimeSec, config]);

  // Pause when source/config changes
  useEffect(() => {
    setIsPlaying(false);
    playerRef.current?.pause();
  }, [config, sourceUrl]);

  const togglePlayback = () => {
    const player = playerRef.current;
    if (!player || !config) return;
    if (isPlaying) {
      player.pause();
      setIsPlaying(false);
      return;
    }
    const lastFrame = config.composition.durationInFrames - 1;
    const currentFrame = player.getCurrentFrame();
    if (currentFrame >= lastFrame) {
      player.seekTo(0);
      commitPreviewTime(0);
    }
    player.play();
    setIsPlaying(true);
  };

  const handleTimelineChange = (nextValue: number) => {
    const nextTimeSec = clamp(nextValue, 0, totalDuration);
    setScrubTimeSec(nextTimeSec);
    playerRef.current?.seekTo(Math.round(nextTimeSec * fps));
    if (onPreviewTimeChange) {
      onPreviewTimeChange(nextTimeSec);
    } else {
      setLocalPreviewTimeSec(nextTimeSec);
    }
  };

  const handleScrubStart = () => {
    wasPlayingBeforeScrubRef.current = isPlaying;
    playerRef.current?.pause();
    setIsPlaying(false);
    setIsScrubbing(true);
  };

  const handleScrubEnd = () => {
    setIsScrubbing(false);
    if (wasPlayingBeforeScrubRef.current) {
      playerRef.current?.play();
      setIsPlaying(true);
    }
    wasPlayingBeforeScrubRef.current = false;
  };

  const inputProps = useMemo(() => {
    if (!config) return null;
    return {
      src: sourceUrl ?? "",
      captions: config.input_props.captions,
      topics: config.input_props.topics,
      segments: config.input_props.segments,
      fps: config.composition.fps,
      width: config.composition.width,
      height: config.composition.height,
      subtitleTheme,
      subtitleScale: overlayControls.subtitleScale,
      subtitleYPercent: overlayControls.subtitleYPercent,
      progressScale: overlayControls.progressScale,
      progressYPercent: overlayControls.progressYPercent,
      chapterScale: overlayControls.chapterScale,
      showSubtitles: overlayControls.showSubtitles,
      showProgress: overlayControls.showProgress,
      showChapter: overlayControls.showChapter,
      progressLabelMode: overlayControls.progressLabelMode,
    };
  }, [config, sourceUrl, subtitleTheme, overlayControls]);

  const playerStyle = useMemo(() => ({width: "100%", height: "100%"}), []);

  if (!config) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-6 py-10 text-center text-sm text-slate-500">
        正在准备导出预览...
      </div>
    );
  }

  const showPlayer = Boolean(sourceUrl) || emptyStateMode === "blank";

  if (!showPlayer) {
    return (
      <div className="flex h-full min-h-0 w-full flex-1 flex-col overflow-hidden rounded-xl bg-black">
        <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-[linear-gradient(180deg,#111827_0%,#0f172a_100%)] text-sm text-slate-300">
          当前会话缺少本地原视频，预览不可用
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-1 flex-col overflow-hidden rounded-xl bg-black">
      <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden">
        <Player
          ref={playerRef}
          component={StitchVideoWeb}
          durationInFrames={config.composition.durationInFrames}
          fps={config.composition.fps}
          compositionWidth={config.composition.width}
          compositionHeight={config.composition.height}
          inputProps={inputProps!}
          controls={false}
          style={playerStyle}
        />
      </div>

      <div className="border-t border-slate-800 bg-black px-4 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={togglePlayback}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-black transition hover:bg-slate-200"
            aria-label={isPlaying ? "Pause" : "Play"}
          >
            {isPlaying ? (
              <Pause className="h-4 w-4 fill-current" />
            ) : (
              <Play className="h-4 w-4 fill-current" />
            )}
          </button>
          <div className="min-w-[96px] text-[12px] font-mono text-slate-300">
            {formatClockTime(displayedPreviewTime)} / {formatClockTime(totalDuration)}
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
            className="h-2 min-w-[160px] flex-1 cursor-ew-resize accent-white"
            aria-label="Preview timeline"
          />
        </div>
      </div>
    </div>
  );
}

export default React.memo(ExportFramePreview);
