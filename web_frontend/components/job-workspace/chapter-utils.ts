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

export function parseBlockRange(
  value: string,
): {start: number; end: number} | null {
  const raw = String(value || "").trim();
  if (!raw) {
    return null;
  }
  if (!raw.includes("-")) {
    const normalized = Number.parseInt(raw, 10);
    if (!Number.isFinite(normalized) || normalized < 1) {
      return null;
    }
    return {start: normalized, end: normalized};
  }

  const [startRaw, endRaw] = raw.split("-", 2);
  const start = Number.parseInt(startRaw.trim(), 10);
  const end = Number.parseInt(endRaw.trim(), 10);
  if (
    !Number.isFinite(start) ||
    !Number.isFinite(end) ||
    start < 1 ||
    end < start
  ) {
    return null;
  }
  return {start, end};
}

export function formatBlockRange(start: number, end: number): string {
  return start === end ? String(start) : `${start}-${end}`;
}

export function getChapterLinesFromRange(
  chapter: Chapter,
  keptLines: TestLine[],
): TestLine[] {
  const parsed = parseBlockRange(chapter.block_range);
  if (!parsed) {
    return [];
  }
  return keptLines.slice(parsed.start - 1, parsed.end);
}

export function getTimelineChapterMarkers(
  lines: TestLine[],
  displayChapters: Chapter[],
  keptLinePositionById: Map<number, number>,
  chapterByStartPosition: Map<number, Chapter>,
): Map<number, Chapter> {
  const markers = new Map<number, Chapter>();
  if (lines.length === 0 || displayChapters.length === 0) {
    return markers;
  }

  const firstChapter = displayChapters[0];
  markers.set(lines[0].line_id, firstChapter);

  lines.forEach((line) => {
    const position = keptLinePositionById.get(line.line_id);
    if (!position) {
      return;
    }
    const chapter = chapterByStartPosition.get(position);
    if (!chapter || chapter.chapter_id === firstChapter.chapter_id) {
      return;
    }
    markers.set(line.line_id, chapter);
  });

  return markers;
}

function findChapterIndexByPosition(
  chapters: Chapter[],
  position: number,
): number {
  return chapters.findIndex((chapter) => {
    const parsed = parseBlockRange(chapter.block_range);
    return Boolean(parsed && parsed.start <= position && position <= parsed.end);
  });
}

export function moveAdjacentChapterRange(
  chapters: Chapter[],
  draggedPosition: number,
  targetChapterId: number,
): {chapters: Chapter[]; error: string | null} {
  const sourceIndex = findChapterIndexByPosition(chapters, draggedPosition);
  const targetIndex = chapters.findIndex(
    (chapter) => chapter.chapter_id === targetChapterId,
  );
  if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) {
    return {chapters, error: null};
  }
  if (Math.abs(sourceIndex - targetIndex) !== 1) {
    return {
      chapters,
      error: "当前 block_range 模式只支持拖到相邻章节，以保持章节连续。",
    };
  }

  const sourceRange = parseBlockRange(chapters[sourceIndex].block_range);
  const targetRange = parseBlockRange(chapters[targetIndex].block_range);
  if (!sourceRange || !targetRange) {
    return {chapters, error: "章节范围无效，请刷新后重试。"};
  }

  const next = chapters.map((chapter) => ({...chapter}));
  if (sourceIndex < targetIndex) {
    if (
      draggedPosition < sourceRange.start ||
      draggedPosition > sourceRange.end
    ) {
      return {chapters, error: "拖拽位置无效，请重试。"};
    }
    next[sourceIndex].block_range = formatBlockRange(
      sourceRange.start,
      draggedPosition - 1,
    );
    next[targetIndex].block_range = formatBlockRange(
      draggedPosition,
      targetRange.end,
    );
    return {chapters: next, error: null};
  }

  if (
    draggedPosition < sourceRange.start ||
    draggedPosition > sourceRange.end
  ) {
    return {chapters, error: "拖拽位置无效，请重试。"};
  }
  next[targetIndex].block_range = formatBlockRange(
    targetRange.start,
    draggedPosition,
  );
  next[sourceIndex].block_range = formatBlockRange(
    draggedPosition + 1,
    sourceRange.end,
  );
  return {chapters: next, error: null};
}

function buildChapterSizes(
  totalBlocks: number,
  chapterCount: number,
  weights: number[],
): number[] {
  if (totalBlocks <= 0 || chapterCount <= 0) {
    return [];
  }
  if (chapterCount === 1) {
    return [totalBlocks];
  }

  const safeCount = Math.min(chapterCount, totalBlocks);
  const normalizedWeights =
    weights.length === safeCount && weights.some((weight) => weight > 0)
      ? weights.map((weight) => Math.max(0, weight))
      : Array.from({length: safeCount}, () => 1);

  const base = Array.from({length: safeCount}, () => 1);
  let remaining = totalBlocks - safeCount;
  if (remaining <= 0) {
    return base;
  }

  const weightSum =
    normalizedWeights.reduce((sum, weight) => sum + weight, 0) || safeCount;
  const fractions = normalizedWeights.map((weight, index) => {
    const raw = (weight / weightSum) * remaining;
    const extra = Math.floor(raw);
    base[index] += extra;
    remaining -= extra;
    return {index, fraction: raw - extra};
  });

  fractions
    .sort((left, right) => right.fraction - left.fraction)
    .slice(0, remaining)
    .forEach(({index}) => {
      base[index] += 1;
    });

  return base;
}

function normalizeChapterTitle(title: string, index: number): string {
  const trimmed = String(title || "").trim();
  return trimmed || `章节${index + 1}`;
}

export function materializeChapterRanges(
  chapters: Chapter[],
  keptLines: TestLine[],
): Chapter[] {
  if (keptLines.length === 0) {
    return [];
  }

  return chapters
    .map((chapter, index) => {
      const parsed = parseBlockRange(chapter.block_range);
      if (!parsed) {
        return null;
      }
      const chapterLines = keptLines.slice(parsed.start - 1, parsed.end);
      if (chapterLines.length === 0) {
        return null;
      }
      return {
        chapter_id: index + 1,
        title: normalizeChapterTitle(chapter.title, index),
        start: chapterLines[0].start,
        end: chapterLines[chapterLines.length - 1].end,
        block_range: formatBlockRange(parsed.start, parsed.end),
      } satisfies Chapter;
    })
    .filter((chapter): chapter is Chapter => Boolean(chapter));
}

export function syncChaptersWithKeptLines(
  chapters: Chapter[],
  keptLines: TestLine[],
): Chapter[] {
  const keptCount = keptLines.length;
  if (keptCount === 0) {
    return [];
  }

  const nextCount = Math.min(Math.max(chapters.length, 1), keptCount);
  const weights = chapters.slice(0, nextCount).map((chapter) => {
    const parsed = parseBlockRange(chapter.block_range);
    if (!parsed) {
      return 1;
    }
    return Math.max(1, parsed.end - parsed.start + 1);
  });
  const sizes = buildChapterSizes(keptCount, nextCount, weights);

  let cursor = 1;
  return sizes.map((size, index) => {
    const start = cursor;
    const end = cursor + size - 1;
    cursor = end + 1;
    const chapterLines = keptLines.slice(start - 1, end);
    return {
      chapter_id: index + 1,
      title: normalizeChapterTitle(chapters[index]?.title || "", index),
      start: chapterLines[0].start,
      end: chapterLines[chapterLines.length - 1].end,
      block_range: formatBlockRange(start, end),
    } satisfies Chapter;
  });
}

export function deleteChapterAndRebalance(
  chapters: Chapter[],
  chapterId: number,
  keptLines: TestLine[],
): Chapter[] {
  if (chapters.length <= 1) {
    return syncChaptersWithKeptLines(chapters.slice(0, 1), keptLines);
  }
  const remaining = chapters.filter((chapter) => chapter.chapter_id !== chapterId);
  return syncChaptersWithKeptLines(remaining, keptLines);
}

export function buildTestConfirmChapters(
  chapters: Chapter[],
  keptLines: TestLine[],
): TestConfirmChapter[] {
  const normalizedChapters = materializeChapterRanges(chapters, keptLines);
  if (normalizedChapters.length === 0) {
    throw new Error("当前没有可用章节，请至少保留一句字幕。");
  }

  return normalizedChapters.map((chapter, index) => ({
    chapter_id: index + 1,
    title: normalizeChapterTitle(chapter.title, index),
    block_range: chapter.block_range,
  }));
}
