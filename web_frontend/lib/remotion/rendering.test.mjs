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

test("maps AudioData copy conversion failures to a friendly audio guidance", () => {
  const message = getFriendlyWebRenderErrorMessage(
    new Error(
      "Failed to execute 'copyTo' on 'AudioData': AudioData currently only supports copy conversion to f32-planar."
    )
  );
  assert.match(message, /本地音频处理失败/);
  assert.match(message, /H\.264\/AAC/);
});

test("maps no-audio-codec export failures to the same friendly audio guidance", () => {
  const message = getFriendlyWebRenderErrorMessage(
    new Error("No audio codec can be encoded by this browser for container mp4.")
  );
  assert.match(message, /本地音频处理失败/);
  assert.match(message, /导出/);
});
