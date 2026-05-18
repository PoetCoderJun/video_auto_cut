"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

const CYCLE = 5000;
const PHASE_BEFORE = 2200;

interface SubLine {
  id: number;
  time: string;
  text: string;
}

const BEFORE_LINES: SubLine[] = [
  { id: 1, time: "00:01", text: "大家好，今天和大家聊聊 AI 剪辑" },
  { id: 2, time: "00:03", text: "嗯..." },
  { id: 3, time: "00:04", text: "它可以自动去水词和修复语音识别不，嗯" },
  { id: 4, time: "00:07", text: "它可以自动去水词和修复语音识别不准的问题" },
  { id: 5, time: "00:10", text: "额，一键就可以生成带字幕、高粱、进度条的成片" },
  { id: 6, time: "00:13", text: "用起来简单得不得了" },
];

const AFTER_LINES: SubLine[] = [
  { id: 1, time: "00:01", text: "大家好，今天和大家聊聊 AI 剪辑" },
  { id: 4, time: "00:07", text: "它可以自动去水词和修复语音识别不准的问题" },
  { id: 5, time: "00:10", text: "一键就可以生成带字幕、高亮、进度条的成片" },
  { id: 6, time: "00:13", text: "用起来简单得不得了" },
];

function Line5Text({ phase, progress }: { phase: "before" | "after"; progress: number }) {
  const isAfter = phase === "after";
  const correctProgress = isAfter ? Math.min(1, progress * 2.5) : 0;

  if (!isAfter) {
    return <span className="text-foreground/80">{BEFORE_LINES[4].text}</span>;
  }

  const beforeText = BEFORE_LINES[4].text;
  const afterText = AFTER_LINES[2].text;

  // "额，一键就可以生成带字幕、高粱、进度条的成片"
  //   → "一键就可以生成带字幕、高亮、进度条的成片"

  const prefix = "一键就可以生成带字幕、";
  const wrongMid = "高粱";
  const correctMid = "高亮";
  const suffix = "、进度条的成片";

  return (
    <span className="text-foreground/80">
      {/* "额，" — cross out and fade */}
      <span
        className={cn(
          "inline-block transition-all duration-700",
          correctProgress > 0.3
            ? "opacity-0 w-0 scale-90"
            : "opacity-100 text-red-400 line-through decoration-red-300/60"
        )}
      >
        额，
      </span>
      {prefix}
      {/* "高粱" → "高亮" swap */}
      <span className="relative inline-block">
        {/* wrong: fades out */}
        <span
          className={cn(
            "transition-all duration-700",
            correctProgress > 0.5
              ? "opacity-0 scale-90"
              : "opacity-100 text-red-400 line-through decoration-red-300/60"
          )}
        >
          {wrongMid}
        </span>
        {/* correct: fades in */}
        <span
          className={cn(
            "absolute left-0 top-0 transition-all duration-700",
            correctProgress > 0.5
              ? "opacity-100 scale-100"
              : "opacity-0 scale-95"
          )}
        >
          {correctMid}
        </span>
      </span>
      {suffix}
    </span>
  );
}

export default function HeroAnimation({ className }: { className?: string }) {
  const [phase, setPhase] = useState<"before" | "after">("before");
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let raf: number;
    const start = performance.now();

    const tick = (now: number) => {
      const elapsed = (now - start) % CYCLE;

      if (elapsed < PHASE_BEFORE) {
        setPhase("before");
        setProgress(elapsed / PHASE_BEFORE);
      } else {
        setPhase("after");
        setProgress((elapsed - PHASE_BEFORE) / (CYCLE - PHASE_BEFORE));
      }

      raf = requestAnimationFrame(tick);
    };

    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const lines = phase === "before" ? BEFORE_LINES : AFTER_LINES;

  return (
    <div className={cn("w-full max-w-[400px] mx-auto select-none", className)}>
      <div className="rounded-2xl border border-border/50 bg-card/80 shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-2.5 border-b border-border/30">
          <div className="flex items-center gap-2">
            <div
              className={cn(
                "h-1.5 w-1.5 rounded-full transition-colors duration-300",
                phase === "before" && "bg-amber-400",
                phase === "after" && "bg-emerald-400"
              )}
            />
            <span className="text-[11px] font-medium text-muted-foreground/80">
              {phase === "before" ? "原始字幕" : "精剪后"}
            </span>
          </div>
          <span className="text-[11px] tabular-nums text-muted-foreground/60">
            {phase === "after" ? "4 / 6" : "6"}
          </span>
        </div>

        {/* Lines */}
        <div className="px-5 py-4 min-h-[200px]">
          <div className="space-y-2">
            {lines.map((line, idx) => (
              <div
                key={line.id}
                className={cn(
                  "flex items-center gap-2.5 transition-all duration-700 ease-out",
                  phase === "after" && idx >= 2 && line.id === 5
                    ? "translate-x-0"
                    : ""
                )}
              >
                <span className="text-[10px] text-muted-foreground/50 font-mono w-7 shrink-0">
                  {line.time}
                </span>
                <div
                  className={cn(
                    "flex-1 flex items-center gap-2 rounded-md px-2.5 py-1.5",
                    phase === "before" && line.id === 5 && "bg-amber-400/[0.06]"
                  )}
                >
                  <div
                    className={cn(
                      "h-1 rounded-full shrink-0 transition-all duration-300",
                      phase === "before" && (line.id === 2 || line.id === 3 || line.id === 5)
                        ? "w-4 bg-amber-400/60"
                        : "w-2.5 bg-muted-foreground/15"
                    )}
                  />
                  {line.id === 5 ? (
                    <span className="text-[13px] truncate">
                      <Line5Text phase={phase} progress={progress} />
                    </span>
                  ) : (
                    <span className="text-[13px] truncate text-foreground/80">
                      {line.text}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Result badge */}
        <div className="px-5 pb-4">
          <div
            className={cn(
              "text-center transition-all duration-500",
              phase === "after"
                ? "opacity-100 translate-y-0"
                : "opacity-0 translate-y-1 pointer-events-none"
            )}
          >
            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/[0.08] px-3 py-1 text-[11px] font-medium text-emerald-600/80 dark:text-emerald-400/80">
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <polyline points="20 6 9 17 4 12" />
              </svg>
              删去 2 句废话，修正 2 处错字
            </span>
          </div>
        </div>

        {/* Phase dots */}
        <div className="flex items-center justify-center gap-1 pb-3">
          <div
            className={cn(
              "h-[3px] rounded-full transition-all duration-500",
              phase === "before" ? "w-5 bg-foreground/40" : "w-1.5 bg-foreground/20"
            )}
          />
          <div
            className={cn(
              "h-[3px] rounded-full transition-all duration-500",
              phase === "after" ? "w-5 bg-foreground/40" : "w-1.5 bg-muted-foreground/10"
            )}
          />
        </div>
      </div>
    </div>
  );
}
