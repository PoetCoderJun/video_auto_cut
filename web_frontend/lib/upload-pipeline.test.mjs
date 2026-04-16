import test from "node:test";
import assert from "node:assert/strict";

import {
  MAX_VIDEO_DURATION_SEC,
  getVideoDurationLimitMessage,
} from "./upload-pipeline.ts";

test("getVideoDurationLimitMessage describes the detected duration and shared limit", () => {
  assert.equal(
    getVideoDurationLimitMessage(MAX_VIDEO_DURATION_SEC + 17),
    "视频时长 10 分 17 秒，已达到 10 分钟限制，请上传更短的视频。",
  );
});
