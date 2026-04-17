import test from "node:test";
import assert from "node:assert/strict";

import {
  ApiClientError,
  clearRenderCompletionPending,
  createJob,
  getRenderCompletionPending,
  invalidateTokenCache,
  setApiAuthTokenProvider,
  setRenderCompletionPending,
  uploadAudio,
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

test("invalid render completion storage is ignored and cleared", () => {
  const storage = createMockStorage();
  const restoreWindow = withMockWindowStorage(storage);

  try {
    storage.setItem(RENDER_COMPLETION_PENDING_STORAGE_KEY, "{invalid json");
    assert.equal(getRenderCompletionPending("job-invalid"), null);
    assert.equal(storage.getItem(RENDER_COMPLETION_PENDING_STORAGE_KEY), null);
  } finally {
    restoreWindow();
  }
});

test("uploadAudio uses frontend direct OSS upload flow", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];

  setApiAuthTokenProvider(async () => "test-token");
  invalidateTokenCache();

  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });

    if (calls.length === 1) {
      return new Response(
        JSON.stringify({
          request_id: "req-1",
          data: {
            put_url: "https://oss.example.invalid/upload/audio.mp3",
            object_key: "video-auto-cut/asr/job-1/audio.mp3",
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    if (calls.length === 2) {
      return new Response(null, { status: 200 });
    }

    if (calls.length === 3) {
      return new Response(
        JSON.stringify({
          request_id: "req-2",
          data: {
            job: {
              job_id: "job-1",
              status: "UPLOAD_READY",
              progress: 10,
              stage: null,
              error: null,
            },
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    throw new Error(`unexpected fetch call ${calls.length}`);
  };

  try {
    const file = new File([new Uint8Array([1, 2, 3])], "audio.mp3", {
      type: "audio/mpeg",
    });

    const job = await uploadAudio("job-1", file);

    assert.equal(job.job_id, "job-1");
    assert.equal(job.status, "UPLOAD_READY");
    assert.equal(calls.length, 3);

    assert.match(calls[0].url, /\/jobs\/job-1\/oss-upload-url$/);
    assert.equal(
      new Headers(calls[0].init?.headers).get("Authorization"),
      "Bearer test-token"
    );

    assert.equal(calls[1].url, "https://oss.example.invalid/upload/audio.mp3");
    assert.equal(calls[1].init?.method, "PUT");
    assert.equal(new Headers(calls[1].init?.headers).get("Content-Type"), "audio/mpeg");
    assert.equal(calls[1].init?.body, file);
    assert.equal(new Headers(calls[1].init?.headers).get("Authorization"), null);

    assert.match(calls[2].url, /\/jobs\/job-1\/audio-oss-ready$/);
    assert.deepEqual(JSON.parse(String(calls[2].init?.body)), {
      object_key: "video-auto-cut/asr/job-1/audio.mp3",
    });
  } finally {
    globalThis.fetch = originalFetch;
    setApiAuthTokenProvider(null);
    invalidateTokenCache();
  }
});

test("createJob waits briefly for auth token initialization before failing", async () => {
  const originalFetch = globalThis.fetch;
  let attempts = 0;
  const calls = [];

  setApiAuthTokenProvider(async () => {
    attempts += 1;
    return attempts < 2 ? null : "late-token";
  });
  invalidateTokenCache();

  globalThis.fetch = async (url, init) => {
    calls.push({url: String(url), init});
    return new Response(
      JSON.stringify({
        request_id: "req-auth-retry",
        data: {
          job: {
            job_id: "job-auth-retry",
            status: "CREATED",
            progress: 0,
            stage: null,
            error: null,
          },
        },
      }),
      {
        status: 200,
        headers: {"Content-Type": "application/json"},
      }
    );
  };

  try {
    const job = await createJob();

    assert.equal(job.job_id, "job-auth-retry");
    assert.equal(attempts, 2);
    assert.equal(calls.length, 1);
    assert.equal(
      new Headers(calls[0].init?.headers).get("Authorization"),
      "Bearer late-token"
    );
  } finally {
    globalThis.fetch = originalFetch;
    setApiAuthTokenProvider(null);
    invalidateTokenCache();
  }
});

test("uploadAudio surfaces direct upload failures", async () => {
  const originalFetch = globalThis.fetch;

  setApiAuthTokenProvider(async () => "test-token");
  invalidateTokenCache();

  globalThis.fetch = async (url) => {
    if (String(url).includes("/oss-upload-url")) {
      return new Response(
        JSON.stringify({
          request_id: "req-1",
          data: {
            put_url: "https://oss.example.invalid/upload/audio.mp3",
            object_key: "video-auto-cut/asr/job-1/audio.mp3",
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    return new Response("upload failed", { status: 500 });
  };

  try {
    const file = new File([new Uint8Array([1, 2, 3])], "audio.mp3", {
      type: "audio/mpeg",
    });

    await assert.rejects(() => uploadAudio("job-1", file), (error) => {
      assert.ok(error instanceof ApiClientError);
      assert.equal(error.message, "音频上传失败，请稍后重试。");
      assert.equal(error.code, "DIRECT_UPLOAD_FAILED");
      assert.equal(error.status, 500);
      assert.equal(error.details, "PUT 500: upload failed");
      return true;
    });
  } finally {
    globalThis.fetch = originalFetch;
    setApiAuthTokenProvider(null);
    invalidateTokenCache();
  }
});

test("uploadAudio preserves backend service-unavailable message", async () => {
  const originalFetch = globalThis.fetch;

  setApiAuthTokenProvider(async () => "test-token");
  invalidateTokenCache();

  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        request_id: "req-1",
        error: {
          code: "SERVICE_UNAVAILABLE",
          message: "上传服务暂未配置，请稍后再试。",
        },
      }),
      {
        status: 503,
        headers: { "Content-Type": "application/json" },
      }
    );

  try {
    const file = new File([new Uint8Array([1, 2, 3])], "audio.mp3", {
      type: "audio/mpeg",
    });

    await assert.rejects(() => uploadAudio("job-1", file), (error) => {
      assert.ok(error instanceof ApiClientError);
      assert.equal(error.status, 503);
      assert.equal(error.code, "SERVICE_UNAVAILABLE");
      assert.equal(error.message, "上传服务暂未配置，请稍后再试。");
      return true;
    });
  } finally {
    globalThis.fetch = originalFetch;
    setApiAuthTokenProvider(null);
    invalidateTokenCache();
  }
});
