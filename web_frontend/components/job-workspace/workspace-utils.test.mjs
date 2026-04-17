import test from "node:test";
import assert from "node:assert/strict";

import {
  buildPreviewRenderMeta,
  getTestPreviewLines,
  isPreviewRenderMetaReduced,
} from "./workspace-utils.ts";

const buildLine = (overrides = {}) => ({
  line_id: 1,
  start: 0,
  end: 1,
  original_text: "原始字幕",
  optimized_text: "",
  ai_suggest_remove: false,
  user_final_remove: false,
  ...overrides,
});

test("getTestPreviewLines keeps the earliest visible lines in lightweight contract format", () => {
  const lines = Array.from({length: 16}, (_, index) =>
    buildLine({
      line_id: index + 1,
      start: index * 5,
      end: index * 5 + 2,
      original_text: `第${index + 1}句`,
      user_final_remove: index === 2,
    }),
  );

  assert.deepEqual(getTestPreviewLines(lines), [
    "【00:00】第1句",
    "【00:05】第2句",
    "【00:10】<remove>第3句",
    "【00:15】第4句",
    "【00:20】第5句",
    "【00:25】第6句",
    "【00:30】第7句",
    "【00:35】第8句",
    "【00:40】第9句",
    "【00:45】第10句",
    "【00:50】第11句",
    "【00:55】第12句",
    "【01:00】第13句",
    "【01:05】第14句",
  ]);
});

test("getTestPreviewLines skips empty kept lines and preserves removed placeholders", () => {
  const lines = [
    buildLine({line_id: 1, start: 0, original_text: "   ", optimized_text: "  "}),
    buildLine({line_id: 2, start: 1, original_text: "原始稿", optimized_text: "润色后"}),
    buildLine({line_id: 3, start: 2, original_text: "", optimized_text: "", user_final_remove: true}),
  ];

  assert.deepEqual(getTestPreviewLines(lines), [
    "【00:01】润色后",
    "【00:02】<remove><No Speech>",
  ]);
});

test("buildPreviewRenderMeta keeps aspect ratio while capping preview resolution and fps", () => {
  const previewMeta = buildPreviewRenderMeta({
    width: 3840,
    height: 2160,
    fps: 59.94,
    duration_sec: 120,
  });

  assert.deepEqual(previewMeta, {
    width: 960,
    height: 540,
    fps: 20,
    duration_sec: 120,
  });
});

test("isPreviewRenderMetaReduced detects when preview can stay on original lightweight spec", () => {
  const sourceMeta = {
    width: 640,
    height: 360,
    fps: 15,
    duration_sec: 30,
  };
  const previewMeta = buildPreviewRenderMeta(sourceMeta);

  assert.equal(isPreviewRenderMetaReduced(sourceMeta, previewMeta), false);
  assert.deepEqual(previewMeta, sourceMeta);
});
