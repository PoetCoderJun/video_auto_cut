import test from "node:test";
import assert from "node:assert/strict";

import {
  buildTestConfirmChapters,
  deleteChapterAndRebalance,
  getEstimatedDurationFromLines,
  getKeptTestLines,
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

const chapters = [
  {chapter_id: 1, title: "第一章", start: 0, end: 2, block_range: "1-2"},
  {chapter_id: 2, title: "第二章", start: 2, end: 4, block_range: "3-4"},
];

test("moveAdjacentChapterRange moves the boundary between adjacent chapters", () => {
  const moved = moveAdjacentChapterRange(chapters, 2, 2);

  assert.equal(moved.error, null);
  assert.deepEqual(
    moved.chapters.map((chapter) => chapter.block_range),
    ["1", "2-4"],
  );
});

test("syncChaptersWithKeptLines rebalances ranges after a line is removed", () => {
  const keptLines = getKeptTestLines(lines.slice(0, 3));
  const synced = syncChaptersWithKeptLines(chapters, keptLines);

  assert.deepEqual(
    synced.map((chapter) => chapter.block_range),
    ["1-2", "3"],
  );
  assert.deepEqual(
    synced.map((chapter) => chapter.title),
    ["第一章", "第二章"],
  );
});

test("deleteChapterAndRebalance preserves continuity after removing a chapter", () => {
  const next = deleteChapterAndRebalance(chapters, 1, lines);

  assert.deepEqual(next.map((chapter) => chapter.block_range), ["1-4"]);
  assert.equal(next[0].title, "第二章");
});

test("materializeChapterRanges and buildTestConfirmChapters normalize sparse input", () => {
  const sparseChapters = [
    {chapter_id: 9, title: "", start: 0, end: 0, block_range: "1-2"},
    {chapter_id: 10, title: "尾声", start: 0, end: 0, block_range: "3-4"},
  ];

  const materialized = materializeChapterRanges(sparseChapters, lines);
  const confirmPayload = buildTestConfirmChapters(sparseChapters, lines);

  assert.deepEqual(
    materialized.map((chapter) => chapter.chapter_id),
    [1, 2],
  );
  assert.deepEqual(
    confirmPayload.map((chapter) => ({
      chapter_id: chapter.chapter_id,
      title: chapter.title,
      block_range: chapter.block_range,
    })),
    [
      {chapter_id: 1, title: "章节1", block_range: "1-2"},
      {chapter_id: 2, title: "尾声", block_range: "3-4"},
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
