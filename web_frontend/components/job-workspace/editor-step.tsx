"use client";

import React, {useState} from "react";

import type {Chapter, TestLine} from "@/lib/api";
import {Badge} from "@/components/ui/badge";
import {Button} from "@/components/ui/button";
import {Card, CardContent} from "@/components/ui/card";
import {Textarea} from "@/components/ui/textarea";
import {formatDuration} from "@/lib/source-video-guard";
import {cn} from "@/lib/utils";
import {ArrowRight, GripVertical, Loader2, X} from "lucide-react";

import {autoResize} from "./workspace-utils";

export function EditorStep({
  actions,
  helpers,
  state,
}: {
  actions: {
    handleConfirmTest: () => void;
    handleRetryTestDraftLoad: () => void;
    moveChapterBoundary: (draggedPosition: number, targetChapterId: number) => void;
    removeChapter: (chapterId: number) => void;
    updateChapter: (chapterId: number, patch: Partial<Chapter>) => void;
    updateLine: (lineId: number, patch: Partial<TestLine>) => void;
  };
  helpers: {
    getChapterLinesFromRange: (chapter: Chapter, keptLines: TestLine[]) => TestLine[];
  };
  state: {
    busy: boolean;
    chapterBadgeColors: string[];
    chapterByStartPosition: Map<number, Chapter>;
    displayChapters: Chapter[];
    estimatedDuration: number;
    keptLinePositionById: Map<number, number>;
    keptLines: TestLine[];
    lines: TestLine[];
    originalDuration: number;
    testDraftError: string;
  };
}) {
  const {
    busy,
    chapterBadgeColors,
    chapterByStartPosition,
    displayChapters,
    estimatedDuration,
    keptLinePositionById,
    keptLines,
    lines,
    originalDuration,
    testDraftError,
  } = state;
  const [draggedChapterId, setDraggedChapterId] = useState<number | null>(null);
  const [dropTargetLineId, setDropTargetLineId] = useState<number | null>(null);

  if (lines.length === 0) {
    return (
      <div className="space-y-3 rounded-2xl border border-slate-200 bg-white py-16 text-center shadow-sm">
        <Loader2 className="mx-auto h-8 w-8 animate-spin text-primary" />
        <p className="font-medium text-slate-900">正在载入编辑文档...</p>
        <p className="text-sm text-slate-500">
          字幕和章节整理完成后，这里会显示可编辑内容。
        </p>
        {testDraftError && (
          <p className="mx-auto max-w-md text-sm text-red-600">{testDraftError}</p>
        )}
        {testDraftError && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={actions.handleRetryTestDraftLoad}
            className="mx-auto"
          >
            重新加载字幕草稿
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">用字幕编辑视频</h2>
          <p className="text-muted-foreground">
            直接修改字幕，章节会作为分隔符嵌在同一时间线里。
          </p>
        </div>
        <div className="hidden md:block">
          <Badge variant="outline" className="text-sm">
            共 {lines.length} 行字幕 / {displayChapters.length || 0} 个章节
          </Badge>
        </div>
      </div>

      <div className="relative min-h-[500px] w-full rounded-md bg-white border border-[#e2e8f0] shadow-sm py-12 px-8 md:px-16 overflow-hidden mt-6">
        <div className="max-w-3xl mx-auto flex flex-col gap-[6px]">
          {lines.map((line) => {
            const isRemoved = line.user_final_remove;
            const isNoSpeech = !line.optimized_text || line.optimized_text.trim() === "";
            const lineTime = formatDuration(Number(line.start) || 0);
            const linePosition = keptLinePositionById.get(line.line_id);
            const chapter = linePosition
              ? chapterByStartPosition.get(linePosition)
              : null;
            const chapterIndex =
              chapter && linePosition
                ? displayChapters.findIndex(
                    (item) => item.chapter_id === chapter.chapter_id,
                  )
                : -1;
            const currentChapterLines =
              chapter && chapterIndex >= 0
                ? helpers.getChapterLinesFromRange(chapter, keptLines)
                : [];
            const badgeColorClass =
              chapterIndex >= 0
                ? chapterBadgeColors[chapterIndex % chapterBadgeColors.length]
                : chapterBadgeColors[0];

            return (
              <React.Fragment key={line.line_id}>
                {dropTargetLineId === line.line_id && !isRemoved && (
                  <div className="h-1 rounded-full bg-blue-500/50 my-1" />
                )}
                <div className="space-y-[6px]">
                  {chapter && (
                    <div className="group relative flex items-center gap-2">
                      {chapterIndex > 0 && (
                        <div
                          draggable={currentChapterLines.length > 0}
                          onDragStart={(event) => {
                            event.dataTransfer.setData(
                              "text/plain",
                              chapter.chapter_id.toString(),
                            );
                            event.dataTransfer.effectAllowed = "move";
                            setDraggedChapterId(chapter.chapter_id);
                          }}
                          onDragEnd={() => {
                            setDraggedChapterId(null);
                            setDropTargetLineId(null);
                          }}
                          className={cn(
                            "flex h-full cursor-grab select-none items-center p-1 text-slate-300 transition hover:text-slate-500 active:cursor-grabbing",
                            draggedChapterId === chapter.chapter_id && "opacity-40",
                          )}
                          title="拖拽以调整章节边界"
                        >
                          <GripVertical className="h-4 w-4" />
                        </div>
                      )}
                      <span
                        className={cn(
                          "text-xs font-semibold",
                          badgeColorClass.replace("bg-", "text-"),
                        )}
                      >
                        章节{chapterIndex + 1}
                      </span>
                      <input
                        type="text"
                        value={chapter.title}
                        placeholder="章节标题"
                        onChange={(event) =>
                          actions.updateChapter(chapter.chapter_id, {
                            title: event.target.value,
                          })
                        }
                        className="min-w-0 flex-1 bg-transparent text-xs font-semibold text-slate-800 outline-none placeholder:text-slate-400"
                      />
                      {displayChapters.length > 1 && (
                        <button
                          type="button"
                          className="rounded p-1 text-slate-400 transition hover:bg-white hover:text-red-500"
                          onClick={() => actions.removeChapter(chapter.chapter_id)}
                          title="删除分隔符并并入相邻章节"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  )}

                  <div
                    className="group relative flex items-start gap-3"
                    onDragEnter={() => {
                      if (isRemoved || draggedChapterId === null) return;
                      setDropTargetLineId(line.line_id);
                    }}
                    onDragLeave={() => {
                      if (draggedChapterId === null) return;
                      setDropTargetLineId(null);
                    }}
                    onDragOver={(event) => {
                      if (isRemoved || draggedChapterId === null) return;
                      event.preventDefault();
                      event.dataTransfer.dropEffect = "move";
                    }}
                    onDrop={(event) => {
                      if (isRemoved) return;
                      event.preventDefault();
                      const draggedChapterId = parseInt(
                        event.dataTransfer.getData("text/plain"),
                        10,
                      );
                      setDraggedChapterId(null);
                      setDropTargetLineId(null);
                      if (Number.isNaN(draggedChapterId)) return;
                      const linePosition = keptLinePositionById.get(line.line_id);
                      if (!linePosition) return;
                      actions.moveChapterBoundary(linePosition, draggedChapterId);
                    }}
                  >
                    <span className="mt-[2px] select-none font-mono text-[12px] leading-[1.7] text-[#94a3b8]">
                      {lineTime}
                    </span>

                    <div className="min-w-0 flex-1">
                      {isRemoved ? (
                        <button
                          type="button"
                          className="py-[2px] text-left text-[12px] text-[#94a3b8] line-through"
                          onClick={() =>
                            actions.updateLine(line.line_id, {
                              user_final_remove: false,
                            })
                          }
                          title="点击恢复此行"
                        >
                          {isNoSpeech ? "<No Speech>" : line.optimized_text}
                        </button>
                      ) : (
                        <Textarea
                          value={line.optimized_text}
                          onChange={(event) =>
                            actions.updateLine(line.line_id, {
                              optimized_text: event.target.value,
                            })
                          }
                          rows={1}
                          onInput={(event) =>
                            autoResize(event.target as HTMLTextAreaElement)
                          }
                          ref={(element) => {
                            if (element) autoResize(element);
                          }}
                          className="min-h-0 block w-full resize-none border-0 bg-transparent p-0 text-[15px] leading-[1.7] text-[#334155] shadow-none focus-visible:ring-0 rounded-none m-0 overflow-hidden placeholder:text-[#cbd5e1]"
                          placeholder={isNoSpeech ? "<No Speech>" : ""}
                        />
                      )}
                    </div>
                    {!isRemoved && (
                      <div
                        className="shrink-0 ml-2 flex h-6 cursor-pointer items-center px-1 text-[#cbd5e1] opacity-0 transition-opacity hover:text-[#ef4444] group-hover:opacity-100"
                        onClick={() =>
                          actions.updateLine(line.line_id, {
                            user_final_remove: true,
                          })
                        }
                        title="剔除此行"
                      >
                        <X className="h-4 w-4" />
                      </div>
                    )}
                  </div>
                </div>
              </React.Fragment>
            );
          })}
        </div>
      </div>

      <div className="sticky bottom-6 z-10 mx-auto max-w-2xl">
        <Card className="border-t-4 border-t-primary shadow-xl">
          <CardContent className="flex items-center justify-between p-6">
            <div className="flex items-center gap-8">
              <div>
                <div className="text-sm font-medium text-muted-foreground">原始时长</div>
                <div className="text-2xl font-bold font-mono">
                  {formatDuration(originalDuration)}
                </div>
              </div>
              <ArrowRight className="h-6 w-6 text-muted-foreground/50" />
              <div>
                <div className="text-sm font-medium text-muted-foreground">预计时长</div>
                <div className="text-2xl font-bold font-mono text-emerald-600">
                  {formatDuration(estimatedDuration)}
                </div>
              </div>
            </div>
            <Button
              size="lg"
              onClick={actions.handleConfirmTest}
              disabled={
                lines.length === 0 ||
                keptLines.length === 0 ||
                displayChapters.length === 0 ||
                busy
              }
            >
              {busy ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在保存编辑结果...
                </>
              ) : (
                "保存并进入导出"
              )}
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
