import test from "node:test";
import assert from "node:assert/strict";

import { getFriendlyWebRenderErrorMessage } from "./rendering.ts";

test("maps flushing errors to a browser encoder message", () => {
  const message = getFriendlyWebRenderErrorMessage(new Error("Flushing error."));
  assert.match(message, /浏览器本地视频编码器初始化失败/);
});

test("keeps frame extraction timeout guidance", () => {
  const message = getFriendlyWebRenderErrorMessage(
    new Error("Timeout while extracting frame at time 0")
  );
  assert.match(message, /浏览器读取原视频帧超时/);
});
