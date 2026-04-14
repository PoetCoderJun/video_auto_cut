import test from "node:test";
import assert from "node:assert/strict";

import {
  clearStep1Draft,
  clearStep2Draft,
  clearExportPreferences,
  loadExportPreferences,
  loadStep1Draft,
  loadStep2Draft,
  mergeStep1Draft,
  mergeStep2Draft,
  saveExportPreferences,
  saveStep1Draft,
  saveStep2Draft,
} from "./job-draft-storage.ts";

function createMockStorage() {
  const items = new Map();

  return {
    getItem(key) {
      return items.has(key) ? items.get(key) : null;
    },
    setItem(key, value) {
      items.set(key, String(value));
    },
    removeItem(key) {
      items.delete(key);
    },
    clear() {
      items.clear();
    },
  };
}

function withMockWindowStorage(storage = createMockStorage()) {
  const originalWindow = globalThis.window;

  globalThis.window = {
    ...originalWindow,
    localStorage: storage,
  };

  return () => {
    globalThis.window = originalWindow;
  };
}

test("step1 drafts save load and clear by job id", () => {
  const restoreWindow = withMockWindowStorage();
  try {
    saveStep1Draft("job-step1", [
      {
        line_id: 1,
        start: 0,
        end: 1.2,
        original_text: "原文",
        optimized_text: "已修改",
        ai_suggest_remove: false,
        user_final_remove: true,
      },
    ]);

    assert.deepEqual(loadStep1Draft("job-step1"), [
      {
        line_id: 1,
        start: 0,
        end: 1.2,
        original_text: "原文",
        optimized_text: "已修改",
        ai_suggest_remove: false,
        user_final_remove: true,
      },
    ]);

    clearStep1Draft("job-step1");
    assert.equal(loadStep1Draft("job-step1"), null);
  } finally {
    restoreWindow();
  }
});

test("step2 drafts save load and clear by job id", () => {
  const restoreWindow = withMockWindowStorage();
  try {
    saveStep2Draft("job-step2", [
      {
        chapter_id: 1,
        title: "新标题",
        start: 0,
        end: 10,
        block_range: "1-3",
      },
    ]);

    assert.deepEqual(loadStep2Draft("job-step2"), [
      {
        chapter_id: 1,
        title: "新标题",
        start: 0,
        end: 10,
        block_range: "1-3",
      },
    ]);

    clearStep2Draft("job-step2");
    assert.equal(loadStep2Draft("job-step2"), null);
  } finally {
    restoreWindow();
  }
});

test("export preferences save load and normalize invalid cached values", () => {
  const storage = createMockStorage();
  const restoreWindow = withMockWindowStorage(storage);
  try {
    saveExportPreferences({
      subtitleTheme: "text-white",
      overlayControls: {
        subtitleScale: 1.22,
        subtitleYPercent: 84,
        progressScale: 1.18,
        progressYPercent: 91,
        chapterScale: 0.92,
        showSubtitles: false,
        showProgress: true,
        showChapter: false,
        progressLabelMode: "double",
      },
    });

    assert.deepEqual(loadExportPreferences(), {
      subtitleTheme: "text-white",
      overlayControls: {
        subtitleScale: 1.22,
        subtitleYPercent: 84,
        progressScale: 1.18,
        progressYPercent: 91,
        chapterScale: 0.92,
        showSubtitles: false,
        showProgress: true,
        showChapter: false,
        progressLabelMode: "double",
      },
    });

    storage.setItem(
      "video_auto_cut_export_preferences",
      JSON.stringify({
        version: 1,
        updatedAt: Date.now(),
        subtitleTheme: "unexpected-theme",
        overlayControls: {
          subtitleScale: 9,
          subtitleYPercent: -20,
          progressScale: "bad",
          progressYPercent: 200,
          chapterScale: null,
          showSubtitles: "yes",
          showProgress: false,
          showChapter: undefined,
          progressLabelMode: "single",
        },
      })
    );

    assert.deepEqual(loadExportPreferences(), {
      subtitleTheme: "box-white-on-black",
      overlayControls: {
        subtitleScale: 1.45,
        subtitleYPercent: 0,
        progressScale: 1,
        progressYPercent: 100,
        chapterScale: 1,
        showSubtitles: true,
        showProgress: false,
        showChapter: true,
        progressLabelMode: "single",
      },
    });

    clearExportPreferences();
    assert.equal(loadExportPreferences(), null);
  } finally {
    restoreWindow();
  }
});

test("mergeStep1Draft overlays local edits onto server lines", () => {
  const merged = mergeStep1Draft(
    [
      {
        line_id: 1,
        start: 0,
        end: 1,
        original_text: "原文",
        optimized_text: "服务端",
        ai_suggest_remove: false,
        user_final_remove: false,
      },
      {
        line_id: 2,
        start: 1,
        end: 2,
        original_text: "第二句",
        optimized_text: "第二句",
        ai_suggest_remove: false,
        user_final_remove: false,
      },
    ],
    [
      {
        line_id: 1,
        start: 0,
        end: 1,
        original_text: "原文",
        optimized_text: "本地改过",
        ai_suggest_remove: false,
        user_final_remove: true,
      },
    ]
  );

  assert.equal(merged[0].optimized_text, "本地改过");
  assert.equal(merged[0].user_final_remove, true);
  assert.equal(merged[1].optimized_text, "第二句");
});

test("mergeStep2Draft overlays local chapter title and range edits", () => {
  const merged = mergeStep2Draft(
    [
      {
        chapter_id: 1,
        title: "服务端标题",
        start: 0,
        end: 10,
        block_range: "1-2",
      },
    ],
    [
      {
        chapter_id: 1,
        title: "本地标题",
        start: 0,
        end: 10,
        block_range: "1-3",
      },
    ]
  );

  assert.equal(merged[0].title, "本地标题");
  assert.equal(merged[0].block_range, "1-3");
});
