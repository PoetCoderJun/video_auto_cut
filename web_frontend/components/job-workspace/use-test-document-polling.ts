"use client";

import {useCallback, useEffect, useState} from "react";

import {Chapter, getTest, TestLine} from "@/lib/api";
import {STATUS} from "@/lib/workflow";

const STEP_DRAFT_RETRY_DELAY_MS = 1400;
const TRANSIENT_AUTH_INIT_MESSAGE = "登录状态初始化中，请稍后重试。";

const getFriendlyError = (error: unknown): string => {
  if (error instanceof Error) return error.message;
  return String(error ?? "未知错误");
};

const isTransientAuthInitError = (error: unknown): boolean =>
  getFriendlyError(error).includes(TRANSIENT_AUTH_INIT_MESSAGE);

const areTestLinesEqual = (left: TestLine[], right: TestLine[]): boolean => {
  if (left.length !== right.length) return false;
  for (let index = 0; index < left.length; index += 1) {
    const leftLine = left[index];
    const rightLine = right[index];
    if (
      leftLine.line_id !== rightLine.line_id ||
      leftLine.start !== rightLine.start ||
      leftLine.end !== rightLine.end ||
      leftLine.original_text !== rightLine.original_text ||
      leftLine.optimized_text !== rightLine.optimized_text ||
      leftLine.ai_suggest_remove !== rightLine.ai_suggest_remove ||
      leftLine.user_final_remove !== rightLine.user_final_remove
    ) {
      return false;
    }
  }
  return true;
};

export function useTestDocumentPolling({
  jobId,
  status,
  stageCode,
}: {
  jobId: string;
  status?: string | null;
  stageCode?: string | null;
}) {
  const [lines, setLines] = useState<TestLine[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [testDraftError, setTestDraftError] = useState("");
  const [documentRevision, setDocumentRevision] = useState("");
  const [testReadyHandoffActive, setTestReadyHandoffActive] = useState(false);
  const [testReadyLinesLoaded, setTestReadyLinesLoaded] = useState(false);

  useEffect(() => {
    if (status !== STATUS.TEST_READY) {
      setTestReadyHandoffActive(false);
      setTestReadyLinesLoaded(false);
      setTestDraftError("");
      setDocumentRevision("");
      return;
    }
    if (testReadyLinesLoaded) {
      return;
    }

    setTestReadyHandoffActive(true);
    let cancelled = false;
    const pollTestDocument = () => {
      getTest(jobId)
        .then((document) => {
          if (cancelled) return;
          setTestDraftError("");
          setLines((previous) =>
            areTestLinesEqual(previous, document.lines) ? previous : document.lines,
          );
          setChapters(document.chapters);
          setDocumentRevision(document.document_revision || "");
          setTestReadyLinesLoaded(document.lines.length > 0);
        })
        .catch((error) => {
          if (cancelled) return;
          if (isTransientAuthInitError(error)) return;
          setTestDraftError(`编辑文档加载失败：${getFriendlyError(error)}，已自动重试。`);
        });
    };

    pollTestDocument();
    const intervalId = window.setInterval(pollTestDocument, STEP_DRAFT_RETRY_DELAY_MS);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [jobId, status, testReadyLinesLoaded]);

  useEffect(() => {
    if (status !== STATUS.TEST_RUNNING) {
      return;
    }

    let cancelled = false;
    const pollTestDocument = () => {
      getTest(jobId)
        .then((document) => {
          if (cancelled || document.lines.length === 0) return;
          setTestDraftError("");
          setLines((previous) =>
            areTestLinesEqual(previous, document.lines) ? previous : document.lines,
          );
          if (document.chapters.length > 0) {
            setChapters(document.chapters);
          }
          setDocumentRevision(document.document_revision || "");
        })
        .catch((error) => {
          if (cancelled) return;
          if (isTransientAuthInitError(error)) return;
          setTestDraftError(`字幕草稿加载失败：${getFriendlyError(error)}，已自动重试。`);
        });
    };

    pollTestDocument();
    const intervalId = window.setInterval(pollTestDocument, STEP_DRAFT_RETRY_DELAY_MS);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [jobId, stageCode, status]);

  useEffect(() => {
    if (
      status !== STATUS.TEST_READY ||
      !testReadyHandoffActive ||
      !testReadyLinesLoaded
    ) {
      return;
    }

    const timerId = window.setTimeout(() => {
      setTestReadyHandoffActive(false);
    }, 900);
    return () => {
      window.clearTimeout(timerId);
    };
  }, [status, testReadyHandoffActive, testReadyLinesLoaded]);

  const handleRetryTestDraftLoad = useCallback(() => {
    if (status !== STATUS.TEST_READY) return;
    setTestDraftError("");
    setTestReadyLinesLoaded(false);
  }, [status]);

  const resetTestDocument = useCallback(() => {
    setLines([]);
    setChapters([]);
    setDocumentRevision("");
    setTestReadyLinesLoaded(false);
    setTestDraftError("");
    setTestReadyHandoffActive(false);
  }, []);

  return {
    chapters,
    documentRevision,
    handleRetryTestDraftLoad,
    lines,
    resetTestDocument,
    setChapters,
    setDocumentRevision,
    setLines,
    setTestDraftError,
    testDraftError,
    testReadyHandoffActive,
    testReadyLinesLoaded,
  };
}
