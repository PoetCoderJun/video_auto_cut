import test from "node:test";
import assert from "node:assert/strict";

import {STATUS} from "../../lib/workflow.ts";
import {
  getActiveStep,
  getJobWorkspaceView,
  getTestProcessingNote,
  getTestProcessingTitle,
  getTestVisualProgress,
} from "./workspace-state.ts";

test("getJobWorkspaceView follows the current step handoff contract", () => {
  assert.equal(getJobWorkspaceView(STATUS.CREATED, false), "upload");
  assert.equal(getJobWorkspaceView(STATUS.UPLOAD_READY, false), "processing");
  assert.equal(getJobWorkspaceView(STATUS.TEST_RUNNING, false), "processing");
  assert.equal(getJobWorkspaceView(STATUS.TEST_READY, false), "processing");
  assert.equal(getJobWorkspaceView(STATUS.TEST_READY, true), "editor");
  assert.equal(getJobWorkspaceView(STATUS.TEST_CONFIRMED, false), "export");
  assert.equal(getJobWorkspaceView(STATUS.SUCCEEDED, false), "export");
});

test("getActiveStep stays aligned with workflow statuses", () => {
  assert.equal(getActiveStep(STATUS.CREATED), 1);
  assert.equal(getActiveStep(STATUS.TEST_READY), 2);
  assert.equal(getActiveStep(STATUS.SUCCEEDED), 3);
});

test("getTestVisualProgress prefers stage codes and clamps fallback progress", () => {
  assert.equal(
    getTestVisualProgress({
      status: STATUS.TEST_RUNNING,
      progress: 31,
      stage: {code: "OPTIMIZING_TEXT", message: ""},
    }),
    56,
  );
  assert.equal(
    getTestVisualProgress({
      status: STATUS.UPLOAD_READY,
      progress: 99,
      stage: null,
    }),
    100,
  );
});

test("backend transcribing alias keeps processing copy aligned", () => {
  assert.equal(
    getTestVisualProgress({
      status: STATUS.TEST_RUNNING,
      progress: 31,
      stage: {code: "TRANSCRIBING_MEDIA", message: ""},
    }),
    34,
  );
  assert.equal(getTestProcessingTitle("TRANSCRIBING_MEDIA", ""), "正在识别语音");
  assert.equal(
    getTestProcessingNote("TRANSCRIBING_MEDIA"),
    "先生成初版字幕，完成后会继续自动处理。",
  );
});
