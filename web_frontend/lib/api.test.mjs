import test from "node:test";
import assert from "node:assert/strict";

import {
  clearRenderCompletionPending,
  getRenderCompletionPending,
  setRenderCompletionPending,
} from "./api.ts";

const RENDER_COMPLETION_PENDING_STORAGE_KEY = "video_auto_cut_render_completion_pending";

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

test("setRenderCompletionPending creates and updates marker attempts", () => {
  const restoreWindow = withMockWindowStorage();
  try {
    const first = setRenderCompletionPending("job-1", "first error");
    const second = setRenderCompletionPending("job-1", "second error");

    assert.equal(first?.attempts, 1);
    assert.equal(second?.attempts, 2);
    assert.equal(second?.job_id, "job-1");
    assert.equal(second?.lastError, "second error");
    assert.equal(second?.createdAt, first?.createdAt);
  } finally {
    restoreWindow();
  }
});

test("set/get/clear render completion pending marker", () => {
  const restoreWindow = withMockWindowStorage();
  try {
    const first = setRenderCompletionPending("job-clear");
    assert.ok(first);
    assert.equal(getRenderCompletionPending("job-clear")?.job_id, "job-clear");

    clearRenderCompletionPending("job-clear");
    assert.equal(getRenderCompletionPending("job-clear"), null);
  } finally {
    restoreWindow();
  }
});

test("expired render completion pending markers are pruned", () => {
  const storage = createMockStorage();
  const restoreWindow = withMockWindowStorage(storage);
  const originalNow = Date.now;

  try {
    const now = Date.now();
    storage.setItem(
      RENDER_COMPLETION_PENDING_STORAGE_KEY,
      JSON.stringify({
        "job-expired": {
          job_id: "job-expired",
          createdAt: now - 8 * 24 * 60 * 60 * 1000,
          attempts: 1,
        },
      })
    );

    Date.now = () => now;
    assert.equal(getRenderCompletionPending("job-expired"), null);
    assert.equal(storage.getItem(RENDER_COMPLETION_PENDING_STORAGE_KEY), null);
  } finally {
    Date.now = originalNow;
    restoreWindow();
  }
});
