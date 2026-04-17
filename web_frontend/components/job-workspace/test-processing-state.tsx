"use client";

import {useMemo} from "react";

import type {Job, TestLine} from "../../lib/api.ts";
import {Button} from "@/components/ui/button";
import {Progress} from "@/components/ui/progress";
import {Loader2} from "lucide-react";

import {
  getTestProcessingNote,
  getTestProcessingTitle,
  getTestVisualProgress,
} from "./workspace-state";
import {getTestPreviewLines} from "./workspace-utils";

export function TestProcessingState({
  job,
  lines,
  busy,
  autoTestTriggered,
  draftError,
  onRetry,
  onRetryDraft,
}: {
  job: Job;
  lines: TestLine[];
  busy: boolean;
  autoTestTriggered: boolean;
  draftError: string;
  onRetry: () => void;
  onRetryDraft: () => void;
}) {
  const visualProgress = getTestVisualProgress(job);
  const previewLines = useMemo(() => getTestPreviewLines(lines), [lines]);
  const showSubtitlePreview = previewLines.length > 0;

  return (
    <div className="mx-auto max-w-5xl py-6 md:py-10">
      <div className="relative min-h-[560px] overflow-hidden rounded-[30px] border border-slate-200/80 bg-white shadow-[0_24px_80px_-40px_rgba(15,23,42,0.28)]">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,_rgba(255,255,255,0.28),_rgba(248,250,252,0.06)_48%,_rgba(241,245,249,0.16))]" />
        <div className="absolute inset-0 px-6 py-6 md:px-10 md:py-8">
          {showSubtitlePreview ? (
            <div className="mx-auto max-w-4xl">
              <div className="rounded-[28px] border border-white/45 bg-white/24 px-5 py-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.38)] backdrop-blur-[1px] md:px-6">
                <div className="flex flex-col gap-2.5 opacity-75">
                  {previewLines.map((line, index) => (
                    <div
                      key={`${line}-${index}`}
                      className="font-mono text-[13px] leading-6 tracking-[0.01em] text-slate-700/80 md:text-[14px]"
                    >
                      {line}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="mx-auto flex h-full max-w-4xl flex-col justify-center gap-5 opacity-70">
              {[0, 1, 2, 3, 4, 5].map((index) => (
                <div
                  key={index}
                  className="h-8 rounded-2xl bg-[linear-gradient(90deg,rgba(226,232,240,0.6),rgba(241,245,249,0.92),rgba(226,232,240,0.5))]"
                />
              ))}
            </div>
          )}
        </div>
        <div className="absolute inset-0 bg-white/8 backdrop-blur-[0.5px]" />

        <div className="relative z-10 flex min-h-[560px] items-center justify-center p-6">
          <div className="relative w-full max-w-[340px] overflow-hidden rounded-[22px] border border-white/70 bg-[linear-gradient(180deg,rgba(255,255,255,0.88),rgba(244,248,255,0.92))] px-4 py-5 text-center shadow-[0_20px_45px_-28px_rgba(37,99,235,0.28)] backdrop-blur-2xl md:max-w-[360px]">
            <div className="pointer-events-none absolute inset-x-8 top-0 h-12 rounded-full bg-[rgba(125,170,255,0.18)] blur-xl" />
            <div className="pointer-events-none absolute inset-x-10 bottom-0 h-10 rounded-full bg-[rgba(56,189,248,0.08)] blur-xl" />
            <div className="relative mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-[rgba(148,163,184,0.24)] bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(239,246,255,0.96))] text-[#0f172a] shadow-[0_10px_24px_-18px_rgba(37,99,235,0.38)]">
              <Loader2 className="h-5 w-5 animate-spin" />
            </div>

            <h2 className="relative mt-3 text-[17px] font-semibold tracking-tight text-slate-900 md:text-[19px]">
              {getTestProcessingTitle(job.stage?.code, job.stage?.message)}
            </h2>
            <p className="relative mx-auto mt-1.5 max-w-[240px] text-[12px] leading-5 text-slate-500">
              {getTestProcessingNote(job.stage?.code)}
            </p>
            {draftError && (
              <p className="relative mt-2 max-w-[260px] text-[12px] leading-5 text-red-600">
                {draftError}
              </p>
            )}

            <Progress
              value={visualProgress}
              className="relative mx-auto mt-3 h-1 w-20 bg-slate-200/80"
              indicatorClassName="bg-gradient-to-r from-[#60a5fa] via-[#2563eb] to-[#0f172a]"
            />

            {draftError && (
              <Button
                type="button"
                variant="outline"
                className="relative mt-4 h-8 rounded-full px-3 text-xs"
                onClick={onRetryDraft}
              >
                重新加载字幕草稿
              </Button>
            )}

            {job.status === "UPLOAD_READY" && !busy && autoTestTriggered && (
              <Button
                type="button"
                variant="outline"
                className="relative mt-4 h-8 rounded-full px-3 text-xs"
                onClick={onRetry}
              >
                重新尝试启动字幕任务
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
