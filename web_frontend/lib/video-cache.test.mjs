import test from "node:test";
import assert from "node:assert/strict";

import {
  loadCachedJobSourceVideoRecord,
  saveCachedJobSourceVideo,
} from "./video-cache.ts";

function createRequest() {
  return {
    result: undefined,
    error: null,
    onsuccess: null,
    onerror: null,
    onupgradeneeded: null,
  };
}

function emitSuccess(request, result) {
  queueMicrotask(() => {
    request.result = result;
    request.onsuccess?.({target: request});
  });
}

function createFakeIndexedDb() {
  const records = new Map();
  let storeCreated = false;

  const objectStore = {
    createIndex() {},
    get(key) {
      const request = createRequest();
      emitSuccess(request, records.get(key));
      return request;
    },
    put(value) {
      const request = createRequest();
      records.set(value.jobId, value);
      emitSuccess(request, value);
      return request;
    },
    delete(key) {
      const request = createRequest();
      records.delete(key);
      emitSuccess(request, undefined);
      return request;
    },
    openCursor() {
      const request = createRequest();
      const values = Array.from(records.values());
      let index = 0;

      const advance = () => {
        if (index >= values.length) {
          emitSuccess(request, null);
          return;
        }

        const currentIndex = index;
        const cursor = {
          value: values[currentIndex],
          continue() {
            index += 1;
            advance();
          },
          delete() {
            records.delete(values[currentIndex].jobId);
          },
        };
        emitSuccess(request, cursor);
      };

      advance();
      return request;
    },
  };

  return {
    open() {
      const request = createRequest();
      const db = {
        objectStoreNames: {
          contains(name) {
            return storeCreated && name === "job_source_videos";
          },
        },
        createObjectStore() {
          storeCreated = true;
          return objectStore;
        },
        transaction() {
          return {
            error: null,
            onerror: null,
            objectStore() {
              return objectStore;
            },
          };
        },
        close() {},
      };

      queueMicrotask(() => {
        if (!storeCreated) {
          request.result = db;
          request.onupgradeneeded?.({target: request});
        }
        request.result = db;
        request.onsuccess?.({target: request});
      });

      return request;
    },
  };
}

function withFakeIndexedDb() {
  const originalWindow = globalThis.window;
  globalThis.window = {
    ...originalWindow,
    indexedDB: createFakeIndexedDb(),
  };
  return () => {
    globalThis.window = originalWindow;
  };
}

test("saveCachedJobSourceVideo stores and reloads render metadata", async () => {
  const restoreWindow = withFakeIndexedDb();

  try {
    await saveCachedJobSourceVideo(
      "job-1",
      new File(["first"], "source.mp4", {type: "video/mp4", lastModified: 1}),
      {
        renderMeta: {
          width: 1920,
          height: 1080,
          fps: 30,
          duration_sec: 61.2,
        },
      },
    );

    const cached = await loadCachedJobSourceVideoRecord("job-1");
    assert.ok(cached);
    assert.equal(cached.file.name, "source.mp4");
    assert.deepEqual(cached.renderMeta, {
      width: 1920,
      height: 1080,
      fps: 30,
      duration_sec: 61.2,
      source_overall_bitrate: undefined,
      source_video_bitrate: undefined,
      source_audio_bitrate: undefined,
      source_video_codec: undefined,
    });
  } finally {
    restoreWindow();
  }
});

test("saveCachedJobSourceVideo keeps previous render metadata when overwriting file only", async () => {
  const restoreWindow = withFakeIndexedDb();

  try {
    await saveCachedJobSourceVideo(
      "job-keep-meta",
      new File(["first"], "first.mp4", {type: "video/mp4", lastModified: 1}),
      {
        renderMeta: {
          width: 1080,
          height: 1920,
          fps: 60,
          duration_sec: 12.5,
        },
      },
    );

    await saveCachedJobSourceVideo(
      "job-keep-meta",
      new File(["second"], "second.mp4", {type: "video/mp4", lastModified: 2}),
    );

    const cached = await loadCachedJobSourceVideoRecord("job-keep-meta");
    assert.ok(cached);
    assert.equal(cached.file.name, "second.mp4");
    assert.equal(cached.renderMeta?.width, 1080);
    assert.equal(cached.renderMeta?.fps, 60);
  } finally {
    restoreWindow();
  }
});
