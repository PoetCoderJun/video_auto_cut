import type {Chapter, TestConfirmChapter, TestLine} from "../../lib/api.ts";

export function getOriginalDurationFromLines(lines: TestLine[]): number {
  return lines.reduce((max, line) => {
    const end = Number(line.end);
    if (!Number.isFinite(end) || end <= max) {
      return max;
    }
    return end;
  }, 0);
}

export function getEstimatedDurationFromLines(lines: TestLine[]): number {
  const intervals = lines
    .filter((line) => !line.user_final_remove)
    .filter((line) => String(line.optimized_text || "").trim().length > 0)
    .map((line) => ({
      start: Number(line.start),
      end: Number(line.end),
    }))
    .filter(
      (line) =>
        Number.isFinite(line.start) &&
        Number.isFinite(line.end) &&
        line.end > line.start,
    )
    .sort((a, b) => a.start - b.start);

  if (intervals.length === 0) {
    return 0;
  }

  let total = 0;
  let currentStart = intervals[0].start;
  let currentEnd = intervals[0].end;

  for (let idx = 1; idx < intervals.length; idx += 1) {
    const item = intervals[idx];
    if (item.start <= currentEnd) {
      currentEnd = Math.max(currentEnd, item.end);
      continue;
    }
    total += currentEnd - currentStart;
    currentStart = item.start;
    currentEnd = item.end;
  }

  total += currentEnd - currentStart;
  return Math.max(0, total);
}

export function getKeptTestLines(lines: TestLine[]): TestLine[] {
  return lines
    .filter((line) => !line.user_final_remove)
    .sort((a, b) => a.line_id - b.line_id);
}

function normalizeChapterTitle(title: string, index: number): string {
  const trimmed = String(title || "").trim();
  return trimmed || `章节${index + 1}`;
}

function defaultChapterKey(index: number): string {
  return `chapter-${String(index + 1).padStart(4, "0")}`;
}

function getOrderedLines(lines: TestLine[]): TestLine[] {
  return [...lines].sort((a, b) => a.line_id - b.line_id);
}

function getLineIndexMap(lines: TestLine[]): Map<number, number> {
  return new Map(lines.map((line, index) => [line.line_id, index]));
}

function renumberChapters(chapters: Chapter[]): Chapter[] {
  return [...chapters]
    .sort((left, right) => left.start_line_id - right.start_line_id)
    .map((chapter, index) => ({
      ...chapter,
      chapter_key: String(chapter.chapter_key || defaultChapterKey(index)),
      chapter_id: index + 1,
      title: normalizeChapterTitle(chapter.title, index),
    }));
}

function deriveBlockRange(activeLines: TestLine[], keptLines: TestLine[]): string {
  if (activeLines.length === 0) {
    return "";
  }
  const keptIndexByLineId = new Map(
    keptLines.map((line, index) => [line.line_id, index + 1]),
  );
  const start = keptIndexByLineId.get(activeLines[0].line_id);
  const end = keptIndexByLineId.get(activeLines[activeLines.length - 1].line_id);
  if (!start || !end) {
    return "";
  }
  return start === end ? String(start) : `${start}-${end}`;
}

export function materializeChapterRanges(
  chapters: Chapter[],
  allLines: TestLine[],
): Chapter[] {
  const orderedLines = getOrderedLines(allLines);
  if (orderedLines.length === 0) {
    return [];
  }
  const keptLines = getKeptTestLines(orderedLines);
  const normalizedChapters = renumberChapters(chapters);
  const lineIndexById = getLineIndexMap(orderedLines);

  return normalizedChapters.map((chapter, index) => {
    const startIndex = lineIndexById.get(chapter.start_line_id);
    if (startIndex == null) {
      return {
        ...chapter,
        end_line_id: chapter.start_line_id,
        active_start_line_id: null,
        active_end_line_id: null,
        active_line_count: 0,
        start: null,
        end: null,
        block_range: "",
      } satisfies Chapter;
    }
    const nextStartLineId = normalizedChapters[index + 1]?.start_line_id;
    const nextStartIndex = nextStartLineId != null ? lineIndexById.get(nextStartLineId) : undefined;
    const endIndex = nextStartIndex != null ? nextStartIndex - 1 : orderedLines.length - 1;
    const chapterLines = orderedLines.slice(startIndex, endIndex + 1);
    const activeLines = chapterLines.filter((line) => !line.user_final_remove);

    return {
      chapter_key: chapter.chapter_key,
      chapter_id: index + 1,
      title: normalizeChapterTitle(chapter.title, index),
      start_line_id: chapter.start_line_id,
      end_line_id: chapterLines[chapterLines.length - 1]?.line_id ?? chapter.start_line_id,
      active_start_line_id: activeLines[0]?.line_id ?? null,
      active_end_line_id: activeLines[activeLines.length - 1]?.line_id ?? null,
      active_line_count: activeLines.length,
      start: activeLines[0]?.start ?? null,
      end: activeLines[activeLines.length - 1]?.end ?? null,
      block_range: deriveBlockRange(activeLines, keptLines),
    } satisfies Chapter;
  });
}

export function syncChaptersWithKeptLines(
  chapters: Chapter[],
  allLines: TestLine[],
): Chapter[] {
  if (chapters.length > 0) return renumberChapters(chapters);

  const orderedLines = getOrderedLines(allLines);
  if (orderedLines.length === 0) return [];

  return materializeChapterRanges(
    [
      {
        chapter_key: defaultChapterKey(0),
        chapter_id: 1,
        title: "章节1",
        start_line_id: orderedLines[0].line_id,
        end_line_id: orderedLines[orderedLines.length - 1].line_id,
        active_start_line_id: null,
        active_end_line_id: null,
        active_line_count: 0,
        start: null,
        end: null,
      },
    ],
    orderedLines,
  );
}

export function getChapterLinesFromRange(
  chapter: Chapter,
  allLines: TestLine[],
): TestLine[] {
  return getKeptTestLines(allLines).filter((line) => {
    if (chapter.active_start_line_id == null || chapter.active_end_line_id == null) {
      return false;
    }
    return (
      line.line_id >= chapter.active_start_line_id &&
      line.line_id <= chapter.active_end_line_id
    );
  });
}

export function getTimelineChapterMarkers(
  allLines: TestLine[],
  chapters: Chapter[],
): Map<number, Chapter> {
  const markers = new Map<number, Chapter>();
  const materialized = materializeChapterRanges(chapters, allLines);
  for (const chapter of materialized) {
    const markerLineId = chapter.active_start_line_id ?? chapter.start_line_id;
    if (markerLineId != null) {
      markers.set(markerLineId, chapter);
    }
  }
  return markers;
}

export function moveAdjacentChapterRange(
  chapters: Chapter[],
  targetLineId: number,
  targetChapterKey: string,
): {chapters: Chapter[]; error: string | null} {
  const normalized = renumberChapters(chapters);
  const targetIndex = normalized.findIndex(
    (chapter) => chapter.chapter_key === targetChapterKey,
  );
  if (targetIndex <= 0) {
    return {chapters: normalized, error: null};
  }

  const previous = normalized[targetIndex - 1];
  const current = normalized[targetIndex];
  const next = normalized[targetIndex + 1] ?? null;
  const minStart = previous.start_line_id + 1;
  const maxStart = next ? next.start_line_id - 1 : Number.POSITIVE_INFINITY;

  if (targetLineId < minStart || targetLineId > maxStart) {
    return {
      chapters: normalized,
      error: "当前只支持拖到相邻章节边界内，以保持章节连续。",
    };
  }

  if (targetLineId === current.start_line_id) {
    return {chapters: normalized, error: null};
  }

  return {
    chapters: renumberChapters(
      normalized.map((chapter) =>
        chapter.chapter_key === targetChapterKey
          ? {...chapter, start_line_id: targetLineId}
          : chapter,
      ),
    ),
    error: null,
  };
}

export function deleteChapterAndRebalance(
  chapters: Chapter[],
  chapterKey: string,
  allLines: TestLine[],
): Chapter[] {
  const normalized = renumberChapters(chapters);
  if (normalized.length <= 1) return normalized;

  const index = normalized.findIndex((chapter) => chapter.chapter_key === chapterKey);
  if (index < 0) return normalized;

  const orderedLines = getOrderedLines(allLines);
  if (orderedLines.length === 0) {
    return normalized.filter((chapter) => chapter.chapter_key !== chapterKey);
  }

  const next = normalized.map((chapter) => ({...chapter}));
  if (index === 0 && next[1]) {
    next[1].start_line_id = orderedLines[0].line_id;
  }

  return renumberChapters(
    next.filter((chapter) => chapter.chapter_key !== chapterKey),
  );
}

export function buildTestConfirmChapters(
  chapters: Chapter[],
  allLines: TestLine[],
): TestConfirmChapter[] {
  const keptLines = getKeptTestLines(allLines);
  if (keptLines.length === 0) {
    throw new Error("请至少保留一句字幕后再进入导出。");
  }

  const materialized = materializeChapterRanges(chapters, allLines);
  const emptyChapters = materialized.filter((chapter) => chapter.active_line_count === 0);
  if (emptyChapters.length > 0) {
    const names = emptyChapters
      .map((chapter) =>
        normalizeChapterTitle(chapter.title, Math.max(0, chapter.chapter_id - 1)),
      )
      .join(" / ");
    throw new Error(`请先处理空章节：${names}`);
  }

  return renumberChapters(chapters).map((chapter, index) => ({
    chapter_key: chapter.chapter_key,
    chapter_id: index + 1,
    title: normalizeChapterTitle(chapter.title, index),
    start_line_id: chapter.start_line_id,
  }));
}

export function getKeptLinePosition(
  allLines: TestLine[],
  lineId: number,
): number | null {
  const keptIndex = getKeptTestLines(allLines).findIndex(
    (line) => line.line_id === lineId,
  );
  return keptIndex >= 0 ? keptIndex + 1 : null;
}
