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
    markUserModified,
    resetTestDocument,
    setChapters,
    setLines,
    testDraftError,
    testReadyHandoffActive,
    testReadyLinesLoaded,
  } = useTestDocumentPolling({
    jobId,
    status: job?.status,
    stageCode: job?.stage?.code,
  });

  useEffect(() => {
    resetTestDocument();
  }, [jobId, resetTestDocument]);

  const keptLines = useMemo(() => getKeptTestLines(lines), [lines]);

  const updateChapter = useCallback(
    (chapterKey: string, patch: Partial<Chapter>) => {
      markUserModified();
      setChapters((previous) =>
        previous.map((chapter) =>
          chapter.chapter_key === chapterKey
            ? {...chapter, ...patch}
            : chapter,
        ),
      );
    },
    [markUserModified, setChapters],
  );

  const updateLine = useCallback(
    (lineId: number, patch: Partial<TestLine>) => {
      markUserModified();
      setLines((previous) =>
        previous.map((line) =>
          line.line_id === lineId ? {...line, ...patch} : line,
        ),
      );
    },
    [markUserModified, setLines],
  );

  const moveChapterBoundary = useCallback(
    (targetLineId: number, targetChapterKey: string) => {
      markUserModified();
      setChapters((previous) => {
        const moved = moveAdjacentChapterRange(
          previous,
          targetLineId,
          targetChapterKey,
        );
        if (moved.error) {
          setError(moved.error);
          return previous;
        }
        setError("");
        return moved.chapters;
      });
    },
    [markUserModified, setChapters, setError],
  );

  const removeChapter = useCallback(
    (chapterKey: string) => {
      markUserModified();
      setChapters((previous) =>
        deleteChapterAndRebalance(previous, chapterKey, lines),
      );
    },
    [lines, markUserModified, setChapters],
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
        chapters: buildTestConfirmChapters(chapters, lines),
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
    () => materializeChapterRanges(chapters, lines),
    [chapters, lines],
  );

  const isEditorVisible =
    job?.status === STATUS.TEST_READY &&
    testReadyLinesLoaded &&
    !testReadyHandoffActive;

  return {
    state: {
      busy,
      chapterBadgeColors: CHAPTER_BADGE_COLORS,
      displayChapters,
      estimatedDuration,
      isEditorVisible,
      keptLines,
      lines,
      originalDuration,
      testDraftError,
      testReadyHandoffActive,
      testReadyLinesLoaded,
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
