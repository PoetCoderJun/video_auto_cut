import test from "node:test";
import assert from "node:assert/strict";

import {
  getFriendlyCanRenderIssueMessage,
  getFriendlyCanRenderThrownErrorMessage,
  RenderCapabilityValidationTimeoutError,
  validateBrowserRenderCapability,
} from "./upload-render-validation.ts";

const originalWindow = globalThis.window;

function installWindowStub() {
  globalThis.window = globalThis;
  return () => {
    if (typeof originalWindow === "undefined") {
      delete globalThis.window;
      return;
    }
    globalThis.window = originalWindow;
  };
}

test("maps webcodecs unavailable issues to a HTTPS or Chrome hint", () => {
  const message = getFriendlyCanRenderIssueMessage([
    {
      type: "webcodecs-unavailable",
      severity: "error",
      message: "WebCodecs unavailable",
    },
  ]);
  assert.match(message, /WebCodecs/);
  assert.match(message, /HTTPS/);
});

test("maps codec support issues to a format guidance message", () => {
  const message = getFriendlyCanRenderIssueMessage([
    {
      type: "video-codec-unsupported",
      severity: "error",
      message: "Video codec unsupported",
    },
  ]);
  assert.match(message, /H\.264\/AAC/);
});

test("falls back to the first issue detail when no specific mapping exists", () => {
  const message = getFriendlyCanRenderIssueMessage([
    {
      type: "transparent-video-unsupported",
      severity: "warning",
      message: "Transparent videos unsupported",
    },
  ]);
  assert.match(message, /Transparent videos unsupported/);
});

test("maps AudioData copy conversion failures to upload guidance", () => {
  const message = getFriendlyCanRenderThrownErrorMessage(
    new Error(
      "Failed to execute 'copyTo' on 'AudioData': AudioData currently only supports copy conversion to f32-planar."
    )
  );
  assert.match(message, /本地音频处理失败/);
  assert.match(message, /上传/);
});

test("continues upload when metadata probe times out", async () => {
  const restoreWindow = installWindowStub();
  try {
    await assert.doesNotReject(
      validateBrowserRenderCapability(new File(["video"], "probe.mp4"), {
        loadMetadata: async () => {
          throw new RenderCapabilityValidationTimeoutError("metadata", 1);
        },
      })
    );
  } finally {
    restoreWindow();
  }
});

test("continues upload when capability probe times out", async () => {
  const restoreWindow = installWindowStub();
  try {
    await assert.doesNotReject(
      validateBrowserRenderCapability(new File(["video"], "probe.mp4"), {
        loadMetadata: async () => ({width: 1280, height: 720}),
        loadRenderer: async () => ({
          canRenderMediaOnWeb: async () => {
            throw new RenderCapabilityValidationTimeoutError("probe", 1);
          },
        }),
      })
    );
  } finally {
    restoreWindow();
  }
});

test("still blocks upload on definitive capability issues", async () => {
  const restoreWindow = installWindowStub();
  try {
    await assert.rejects(
      validateBrowserRenderCapability(new File(["video"], "probe.mp4"), {
        loadMetadata: async () => ({width: 1280, height: 720}),
        loadRenderer: async () => ({
          canRenderMediaOnWeb: async () => ({
            canRender: false,
            issues: [
              {
                type: "webgl-unsupported",
                severity: "error",
                message: "WebGL unsupported",
              },
            ],
          }),
        }),
      }),
      /图形能力不足/
    );
  } finally {
    restoreWindow();
  }
});

test("still blocks upload on definitive thrown compatibility errors", async () => {
  const restoreWindow = installWindowStub();
  try {
    await assert.rejects(
      validateBrowserRenderCapability(new File(["video"], "probe.mp4"), {
        loadMetadata: async () => ({width: 1280, height: 720}),
        loadRenderer: async () => ({
          canRenderMediaOnWeb: async () => {
            throw new Error(
              "Failed to execute 'copyTo' on 'AudioData': AudioData currently only supports copy conversion to f32-planar."
            );
          },
        }),
      }),
      /本地音频处理失败/
    );
  } finally {
    restoreWindow();
  }
});
