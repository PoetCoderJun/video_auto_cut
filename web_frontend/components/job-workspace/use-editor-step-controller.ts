"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  type Dispatch,
  type SetStateAction,
} from "react";

import {
  type Chapter,
  confirmTest,
  type Job,
  type TestLine,
} from "../../lib/api";
import {mergeJobStatus} from "../../lib/job-status";
import {STATUS} from "../../lib/workflow";

import {CHAPTER_BADGE_COLORS} from "./constants";
import {
  buildTestConfirmChapters,
  deleteChapterAndRebalance,
  getChapterLinesFromRange,
  getEstimatedDurationFromLines,
  getKeptTestLines,
  getOriginalDurationFromLines,
  materializeChapterRanges,
  moveAdjacentChapterRange,
  parseBlockRange,
  syncChaptersWithKeptLines,
} from "./chapter-utils";
import {useTestDocumentPolling} from "./use-test-document-polling";

export function useEditorStepController({
  busy,
  job,
  jobId,
  setBusy,
  setError,
  setJob,
}: {
  busy: boolean;
  job: Job | null;
  jobId: string;
  setBusy: (busy: boolean) => void;
  setError: (error: string) => void;
  setJob: Dispatch<SetStateAction<Job | null>>;
}) {
  const {
    chapters,
    documentRevision,
    handleRetryTestDraftLoad,
    lines,
    resetTestDocument,
    setChapters,
    setLines,
    testDraftError,
    testReadyHandoffActive,
  } = useTestDocumentPolling({
    jobId,
    status: job?.status,
    stageCode: job?.stage?.code,
  });

  useEffect(() => {
    resetTestDocument();
  }, [jobId, resetTestDocument]);

  const keptLines = useMemo(() => getKeptTestLines(lines), [lines]);
  const keptLinePositionById = useMemo(
    () =>
      new Map(
        keptLines.map((line, index) => [line.line_id, index + 1] as const),
      ),
    [keptLines],
  );

  const updateChapter = useCallback(
    (chapterId: number, patch: Partial<Chapter>) => {
      setChapters((previous) =>
        previous.map((chapter) =>
          chapter.chapter_id === chapterId
            ? {...chapter, ...patch}
            : chapter,
        ),
      );
    },
    [setChapters],
  );

  const updateLine = useCallback(
    (lineId: number, patch: Partial<TestLine>) => {
      setLines((previous) => {
        const nextLines = previous.map((line) =>
          line.line_id === lineId ? {...line, ...patch} : line,
        );
        if (Object.prototype.hasOwnProperty.call(patch, "user_final_remove")) {
          setChapters((previousChapters) =>
            syncChaptersWithKeptLines(previousChapters, getKeptTestLines(nextLines)),
          );
        }
        return nextLines;
      });
    },
    [setChapters, setLines],
  );

  const moveChapterBoundary = useCallback(
    (draggedPosition: number, targetChapterId: number) => {
      setChapters((previous) => {
        const moved = moveAdjacentChapterRange(
          previous,
          draggedPosition,
          targetChapterId,
        );
        if (moved.error) {
          setError(moved.error);
          return previous;
        }
        return syncChaptersWithKeptLines(moved.chapters, keptLines);
      });
    },
    [keptLines, setChapters, setError],
  );

  const removeChapter = useCallback(
    (chapterId: number) => {
      setChapters((previous) =>
        deleteChapterAndRebalance(previous, chapterId, keptLines),
      );
    },
    [keptLines, setChapters],
  );

  const handleConfirmTest = useCallback(async () => {
    if (keptLines.length === 0) {
      setError("请至少保留一句字幕后再进入导出。");
      return;
    }

    setError("");
    setBusy(true);
    try {
      const status = await confirmTest(jobId, {
        lines,
        chapters: buildTestConfirmChapters(chapters, keptLines),
        expectedRevision: documentRevision,
      });
      setJob((previous) => mergeJobStatus(previous, status));
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败，请重试。");
    } finally {
      setBusy(false);
    }
  }, [
    chapters,
    documentRevision,
    jobId,
    keptLines,
    lines,
    setBusy,
    setError,
    setJob,
  ]);

  const originalDuration = useMemo(
    () => getOriginalDurationFromLines(lines),
    [lines],
  );
  const estimatedDuration = useMemo(
    () => getEstimatedDurationFromLines(lines),
    [lines],
  );
  const displayChapters = useMemo(
    () => materializeChapterRanges(chapters, keptLines),
    [chapters, keptLines],
  );

  const chapterByStartPosition = useMemo(() => {
    const mapping = new Map<number, Chapter>();
    displayChapters.forEach((chapter) => {
      const parsed = parseBlockRange(chapter.block_range);
      if (parsed) {
        mapping.set(parsed.start, chapter);
      }
    });
    return mapping;
  }, [displayChapters]);

  const isEditorVisible =
    job?.status === STATUS.TEST_READY && !testReadyHandoffActive;

  return {
    state: {
      busy,
      chapterBadgeColors: CHAPTER_BADGE_COLORS,
      chapterByStartPosition,
      displayChapters,
      estimatedDuration,
      isEditorVisible,
      keptLinePositionById,
      keptLines,
      lines,
      originalDuration,
      testDraftError,
      testReadyHandoffActive,
    },
    actions: {
      handleConfirmTest,
      handleRetryTestDraftLoad,
      moveChapterBoundary,
      removeChapter,
      handleReset: resetTestDocument,
      updateChapter,
      updateLine,
    },
    helpers: {
      getChapterLinesFromRange,
    },
  };
}
