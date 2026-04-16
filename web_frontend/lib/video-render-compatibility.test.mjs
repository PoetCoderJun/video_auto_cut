import test from "node:test";
import assert from "node:assert/strict";

import {
  MOCK_CAN_DECODE_FALSE_MARKER,
  getRenderSourceDirectExportErrorMessage,
  isMockCanDecodeFalseFileName,
} from "./video-render-compatibility.ts";
import { getBrowserCompatibleOutputName } from "./video-transcode-name.ts";

test("isMockCanDecodeFalseFileName matches the explicit marker", () => {
  assert.equal(
    isMockCanDecodeFalseFileName(`sample_${MOCK_CAN_DECODE_FALSE_MARKER}.mp4`),
    true
  );
  assert.equal(
    isMockCanDecodeFalseFileName(`SAMPLE_${MOCK_CAN_DECODE_FALSE_MARKER.toUpperCase()}.mov`),
    true
  );
  assert.equal(isMockCanDecodeFalseFileName("sample.mp4"), false);
  assert.equal(isMockCanDecodeFalseFileName(null), false);
});

test("getBrowserCompatibleOutputName strips the mock marker from transcoded output names", () => {
  assert.equal(
    getBrowserCompatibleOutputName(`sample_${MOCK_CAN_DECODE_FALSE_MARKER}.mp4`),
    "sample_browser_compatible.mp4"
  );
  assert.equal(
    getBrowserCompatibleOutputName(`SAMPLE_${MOCK_CAN_DECODE_FALSE_MARKER.toUpperCase()}.mov`),
    "SAMPLE_browser_compatible.mp4"
  );
});


test("getRenderSourceDirectExportErrorMessage passes through blocked and incompatible guidance", () => {
  assert.equal(
    getRenderSourceDirectExportErrorMessage({
      status: "blocked",
      message: "当前浏览器不支持 VideoDecoder。",
      videoCodec: null,
      audioCodec: null,
    }),
    "当前浏览器不支持 VideoDecoder。"
  );
  assert.equal(
    getRenderSourceDirectExportErrorMessage({
      status: "incompatible",
      message: "当前浏览器无法解码该视频轨，检测到视频编码为 hev1。需要先转成兼容 MP4 后再导出。",
      videoCodec: "hev1",
      audioCodec: "mp4a.40.2",
    }),
    "当前浏览器无法解码该视频轨，检测到视频编码为 hev1。需要先转成兼容 MP4 后再导出。"
  );
  assert.equal(
    getRenderSourceDirectExportErrorMessage({
      status: "compatible",
      message: "当前源视频可直接用于浏览器导出。",
      videoCodec: "avc1.640028",
      audioCodec: "mp4a.40.2",
    }),
    null
  );
});
