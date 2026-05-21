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
import {buildStitchVideoInputProps} from "@/lib/remotion/stitch-video-props";

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

const parseClockTime = (text: string): number | null => {
  const clean = text.trim();
  const match = clean.match(/^(\d{1,2}):(\d{2})(?:\.(\d))?$/);
  if (!match) return null;
  const minutes = Number(match[1]);
  const seconds = Number(match[2]);
  const tenths = match[3] ? Number(match[3]) : 0;
  if (seconds >= 60) return null;
  return minutes * 60 + seconds + tenths * 0.1;
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
  const [isSourcePreloading, setIsSourcePreloading] = useState(false);
  const [isSourceBuffered, setIsSourceBuffered] = useState(false);
  const [isBuffering, setIsBuffering] = useState(false);
  const playerRef = useRef<PlayerRef>(null);
  const bufferVideoRef = useRef<HTMLVideoElement | null>(null);
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

  const primeBrowserBuffer = useCallback(
    (timeSec: number) => {
      const video = bufferVideoRef.current;
      if (!video || !sourceUrl) return;
      const targetTimeSec = clamp(timeSec, 0, Math.max(totalDuration - 0.1, 0));
      const seekWhenReady = () => {
        try {
          if (Number.isFinite(targetTimeSec)) {
            video.currentTime = targetTimeSec;
          }
        } catch {
          // Early seeks can fail while metadata is still loading.
        }
        try {
          void video.play().then(() => video.pause()).catch(() => undefined);
        } catch {
          // preload=auto still warms the browser media cache if autoplay is rejected.
        }
      };

      if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
        seekWhenReady();
        return;
      }
      video.addEventListener("loadedmetadata", seekWhenReady, {once: true});
      try {
        video.load();
      } catch {
        // ignore preload failures; the visible player can still try playback.
      }
    },
    [sourceUrl, totalDuration],
  );

  useEffect(() => {
    if (!sourceUrl) {
      setIsSourcePreloading(false);
      setIsSourceBuffered(false);
      return;
    }

    const video = bufferVideoRef.current;
    if (!video) return;

    let cancelled = false;
    setIsSourcePreloading(true);
    setIsSourceBuffered(false);

    const markBuffered = () => {
      if (cancelled) return;
      setIsSourceBuffered(true);
      setIsSourcePreloading(false);
    };
    const evaluateBuffer = () => {
      if (cancelled) return;
      const hasDecodedFrame = video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA;
      const hasBufferedRange = video.buffered.length > 0 && video.buffered.end(0) > 0;
      if (hasDecodedFrame || hasBufferedRange) {
        markBuffered();
      }
    };

    video.preload = "auto";
    video.muted = true;
    video.playsInline = true;
    video.addEventListener("loadeddata", markBuffered);
    video.addEventListener("canplay", markBuffered);
    video.addEventListener("canplaythrough", markBuffered);
    video.addEventListener("progress", evaluateBuffer);
    video.addEventListener("error", markBuffered);
    evaluateBuffer();
    primeBrowserBuffer(clampedPreviewTime);

    const fallbackTimer = window.setTimeout(markBuffered, 3000);
    return () => {
      cancelled = true;
      window.clearTimeout(fallbackTimer);
      video.removeEventListener("loadeddata", markBuffered);
      video.removeEventListener("canplay", markBuffered);
      video.removeEventListener("canplaythrough", markBuffered);
      video.removeEventListener("progress", evaluateBuffer);
      video.removeEventListener("error", markBuffered);
    };
  }, [primeBrowserBuffer, sourceUrl]);

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
    let prevFrame = -1;
    let stuckFrames = 0;

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

      // Detect buffering: same frame for > 6 ticks (~100ms) while playing
      if (isPlaying) {
        if (frame === prevFrame) {
          stuckFrames++;
          if (stuckFrames > 6) {
            setIsBuffering(true);
          }
        } else {
          stuckFrames = 0;
          setIsBuffering(false);
        }
      } else {
        stuckFrames = 0;
        setIsBuffering(false);
      }
      prevFrame = frame;

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
    primeBrowserBuffer(player.getCurrentFrame() / fps);
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
    primeBrowserBuffer(scrubTimeSec);
    if (wasPlayingBeforeScrubRef.current) {
      playerRef.current?.play();
      setIsPlaying(true);
    }
    wasPlayingBeforeScrubRef.current = false;
  };

  const [timeInput, setTimeInput] = useState(formatClockTime(displayedPreviewTime));

  useEffect(() => {
    setTimeInput(formatClockTime(displayedPreviewTime));
  }, [displayedPreviewTime]);

  const handleTimeInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setTimeInput(e.target.value);
  };

  const handleTimeInputBlur = () => {
    const parsed = parseClockTime(timeInput);
    if (parsed !== null && parsed <= totalDuration) {
      commitPreviewTime(parsed);
      playerRef.current?.seekTo(Math.round(parsed * fps));
    } else {
      setTimeInput(formatClockTime(displayedPreviewTime));
    }
  };

  const handleTimeInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.currentTarget.blur();
    }
  };

  const inputProps = useMemo(() => {
    if (!config) return null;
    return buildStitchVideoInputProps({
      config,
      src: sourceUrl ?? "",
      subtitleTheme,
      overlayControls,
    });
  }, [config, sourceUrl, subtitleTheme, overlayControls]);

  const playerStyle = useMemo(() => ({width: "100%", height: "100%"}), []);

  if (!config) {
    return (
      <div className="rounded-2xl border border-dashed border-muted bg-muted/50 px-6 py-10 text-center text-sm text-muted-foreground">
        正在准备导出预览…
      </div>
    );
  }

  const showPlayer = Boolean(sourceUrl) || emptyStateMode === "blank";

  if (!showPlayer) {
    return (
      <div className="flex h-full min-h-0 w-full flex-1 flex-col overflow-hidden rounded-xl bg-black">
        <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-[linear-gradient(180deg,#111827_0%,#0f172a_100%)] text-sm text-muted-foreground">
          当前会话缺少本地原视频，预览不可用
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 w-full flex-1 flex-col overflow-hidden rounded-xl bg-black">
      <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden">
        {sourceUrl && (
          <video
            ref={bufferVideoRef}
            src={sourceUrl}
            preload="auto"
            muted
            playsInline
            aria-hidden="true"
            className="hidden"
          />
        )}
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
        {(isSourcePreloading || (isPlaying && isBuffering)) && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/30">
            <div className="flex items-center gap-2 rounded-full bg-black/60 px-4 py-2 text-sm text-white backdrop-blur-sm">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              {isSourceBuffered ? "缓冲中…" : "正在预读…"}
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-border/80 bg-black px-4 py-3">
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={togglePlayback}
            disabled={isSourcePreloading || isBuffering}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
            aria-label={isPlaying ? "Pause" : "Play"}
          >
            {isPlaying ? (
              <Pause className="h-4 w-4 fill-current" />
            ) : (
              <Play className="h-4 w-4 fill-current" />
            )}
          </button>

          <div className="flex items-center gap-1.5">
            <input
              type="text"
              value={timeInput}
              onChange={handleTimeInputChange}
              onBlur={handleTimeInputBlur}
              onKeyDown={handleTimeInputKeyDown}
              className="w-[72px] rounded border border-white/20 bg-transparent px-1.5 py-0.5 text-center text-[12px] font-mono text-white outline-none focus:border-primary"
              aria-label="当前时间"
            />
            <span className="text-[12px] font-mono text-muted-foreground">
              / {formatClockTime(totalDuration)}
            </span>
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
