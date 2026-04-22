import test from "node:test";
import assert from "node:assert/strict";

import {
  buildTestConfirmChapters,
  deleteChapterAndRebalance,
  getChapterLinesFromRange,
  getEstimatedDurationFromLines,
  getKeptLinePosition,
  getKeptTestLines,
  getTimelineChapterMarkers,
  materializeChapterRanges,
  moveAdjacentChapterRange,
  syncChaptersWithKeptLines,
} from "./chapter-utils.ts";

const lines = [
  {line_id: 1, start: 0, end: 1, optimized_text: "A", user_final_remove: false},
  {line_id: 2, start: 1, end: 2, optimized_text: "B", user_final_remove: false},
  {line_id: 3, start: 2, end: 3, optimized_text: "C", user_final_remove: false},
  {line_id: 4, start: 3, end: 4, optimized_text: "D", user_final_remove: false},
];

function buildChapter(overrides = {}) {
  return {
    chapter_key: "chapter-0001",
    chapter_id: 1,
    title: "章节",
    start_line_id: 1,
    end_line_id: 1,
    active_start_line_id: null,
    active_end_line_id: null,
    active_line_count: 0,
    start: null,
    end: null,
    ...overrides,
  };
}

const chapters = [
  buildChapter({chapter_key: "chapter-0001", chapter_id: 1, title: "第一章", start_line_id: 1}),
  buildChapter({chapter_key: "chapter-0002", chapter_id: 2, title: "第二章", start_line_id: 3}),
];

test("moveAdjacentChapterRange moves an adjacent chapter start in original-line space", () => {
  const moved = moveAdjacentChapterRange(chapters, 2, "chapter-0002");

  assert.equal(moved.error, null);
  assert.deepEqual(
    moved.chapters.map((chapter) => chapter.start_line_id),
    [1, 2],
  );
});

test("syncChaptersWithKeptLines creates a single covering chapter when draft chapters are missing", () => {
  const keptLines = getKeptTestLines(lines.slice(0, 3));
  const synced = syncChaptersWithKeptLines([], keptLines);

  assert.equal(synced.length, 1);
  assert.equal(synced[0].title, "章节1");
  assert.equal(synced[0].start_line_id, 1);
  assert.equal(synced[0].block_range, "1-3");
});

test("syncChaptersWithKeptLines anchors the chapter to the first original line even when early lines are removed", () => {
  const synced = syncChaptersWithKeptLines(
    [],
    [
      {line_id: 1, start: 0, end: 1, optimized_text: "< No Speech >", user_final_remove: true},
      {line_id: 2, start: 1, end: 2, optimized_text: "第一句", user_final_remove: false},
      {line_id: 3, start: 2, end: 3, optimized_text: "< No Speech >", user_final_remove: true},
      {line_id: 4, start: 3, end: 4, optimized_text: "第二句", user_final_remove: false},
    ],
  );

  assert.equal(synced[0].start_line_id, 1);
  assert.equal(synced[0].active_start_line_id, 2);
  assert.equal(synced[0].active_end_line_id, 4);
  assert.equal(synced[0].block_range, "1-2");
});

test("deleteChapterAndRebalance preserves continuity after removing the first chapter", () => {
  const next = deleteChapterAndRebalance(chapters, "chapter-0001", lines);

  assert.equal(next.length, 1);
  assert.equal(next[0].title, "第二章");
  assert.equal(next[0].start_line_id, 1);
});

test("materializeChapterRanges and buildTestConfirmChapters normalize canonical input", () => {
  const sparseChapters = [
    buildChapter({chapter_key: "chapter-0009", chapter_id: 9, title: "", start_line_id: 1}),
    buildChapter({chapter_key: "chapter-0010", chapter_id: 10, title: "尾声", start_line_id: 3}),
  ];

  const materialized = materializeChapterRanges(sparseChapters, lines);
  const confirmPayload = buildTestConfirmChapters(sparseChapters, lines);

  assert.deepEqual(
    materialized.map((chapter) => chapter.chapter_id),
    [1, 2],
  );
  assert.deepEqual(confirmPayload, [
    {chapter_key: "chapter-0009", chapter_id: 1, title: "章节1", start_line_id: 1},
    {chapter_key: "chapter-0010", chapter_id: 2, title: "尾声", start_line_id: 3},
  ]);
});

test("buildTestConfirmChapters blocks empty chapters before confirm", () => {
  const linesWithRemoved = [
    {line_id: 1, start: 0, end: 1, optimized_text: "第一句", user_final_remove: false},
    {line_id: 2, start: 1, end: 2, optimized_text: "第二句", user_final_remove: true},
  ];
  const draftChapters = [
    buildChapter({chapter_key: "chapter-0001", chapter_id: 1, title: "开场", start_line_id: 1}),
    buildChapter({chapter_key: "chapter-0002", chapter_id: 2, title: "收尾", start_line_id: 2}),
  ];

  assert.throws(
    () => buildTestConfirmChapters(draftChapters, linesWithRemoved),
    /请先处理空章节：收尾/,
  );
});

test("getChapterLinesFromRange and materializeChapterRanges use original-line anchors while projecting active lines", () => {
  const linesWithRemoved = [
    {line_id: 1, start: 0, end: 1, optimized_text: "< No Speech >", user_final_remove: true},
    {line_id: 2, start: 1, end: 2, optimized_text: "第一句", user_final_remove: false},
    {line_id: 3, start: 2, end: 3, optimized_text: "第二句", user_final_remove: false},
    {line_id: 4, start: 3, end: 4, optimized_text: "< No Speech >", user_final_remove: true},
    {line_id: 5, start: 4, end: 5, optimized_text: "第三句", user_final_remove: false},
    {line_id: 6, start: 5, end: 6, optimized_text: "第四句", user_final_remove: false},
  ];
  const draftChapters = [
    buildChapter({chapter_key: "chapter-0009", chapter_id: 9, title: "开场", start_line_id: 1}),
    buildChapter({chapter_key: "chapter-0010", chapter_id: 10, title: "收尾", start_line_id: 5}),
  ];
  const materialized = materializeChapterRanges(draftChapters, linesWithRemoved);

  assert.deepEqual(
    getChapterLinesFromRange(materialized[1], linesWithRemoved).map((line) => line.line_id),
    [5, 6],
  );
  assert.deepEqual(
    materialized.map((chapter) => ({
      chapter_id: chapter.chapter_id,
      start_line_id: chapter.start_line_id,
      active_start_line_id: chapter.active_start_line_id,
      active_end_line_id: chapter.active_end_line_id,
      start: chapter.start,
      end: chapter.end,
      block_range: chapter.block_range,
    })),
    [
      {chapter_id: 1, start_line_id: 1, active_start_line_id: 2, active_end_line_id: 3, start: 1, end: 3, block_range: "1-2"},
      {chapter_id: 2, start_line_id: 5, active_start_line_id: 5, active_end_line_id: 6, start: 4, end: 6, block_range: "3-4"},
    ],
  );
});

test("getEstimatedDurationFromLines merges overlapping kept segments only", () => {
  const estimated = getEstimatedDurationFromLines([
    {line_id: 1, start: 0, end: 2, optimized_text: "A", user_final_remove: false},
    {line_id: 2, start: 1.5, end: 3, optimized_text: "B", user_final_remove: false},
    {line_id: 3, start: 5, end: 6, optimized_text: "", user_final_remove: false},
    {line_id: 4, start: 7, end: 8, optimized_text: "D", user_final_remove: true},
  ]);

  assert.equal(estimated, 3);
});

test("getTimelineChapterMarkers falls back to the original start anchor when a chapter is temporarily empty", () => {
  const timelineLines = [
    {line_id: 10, start: 0, end: 1, optimized_text: "", user_final_remove: true},
    {line_id: 11, start: 1, end: 2, optimized_text: "保留 1", user_final_remove: false},
    {line_id: 12, start: 2, end: 3, optimized_text: "保留 2", user_final_remove: true},
    {line_id: 13, start: 3, end: 4, optimized_text: "保留 3", user_final_remove: false},
  ];
  const display = [
    buildChapter({chapter_key: "chapter-0101", chapter_id: 101, title: "第一章", start_line_id: 10}),
    buildChapter({chapter_key: "chapter-0102", chapter_id: 102, title: "第二章", start_line_id: 12}),
  ];
  const markers = getTimelineChapterMarkers(timelineLines, display);

  assert.deepEqual(
    Array.from(markers.entries()).map(([lineId, chapter]) => [lineId, chapter.title]),
    [
      [11, "第一章"],
      [13, "第二章"],
    ],
  );
});

test("getTimelineChapterMarkers maps visible starts for regular chapters", () => {
  const markers = getTimelineChapterMarkers(lines, chapters);

  assert.deepEqual(
    Array.from(markers.entries()).map(([lineId, chapter]) => [lineId, chapter.title]),
    [
      [1, "第一章"],
      [3, "第二章"],
    ],
  );
});

test("getKeptLinePosition returns 1-based kept-line coordinates", () => {
  const linesWithRemoved = [
    {line_id: 1, start: 0, end: 1, optimized_text: "< No Speech >", user_final_remove: true},
    {line_id: 2, start: 1, end: 2, optimized_text: "第一句", user_final_remove: false},
    {line_id: 3, start: 2, end: 3, optimized_text: "< No Speech >", user_final_remove: true},
    {line_id: 4, start: 3, end: 4, optimized_text: "第二句", user_final_remove: false},
    {line_id: 5, start: 4, end: 5, optimized_text: "第三句", user_final_remove: false},
  ];

  assert.equal(getKeptLinePosition(linesWithRemoved, 1), null);
  assert.equal(getKeptLinePosition(linesWithRemoved, 2), 1);
  assert.equal(getKeptLinePosition(linesWithRemoved, 4), 2);
  assert.equal(getKeptLinePosition(linesWithRemoved, 5), 3);
});
