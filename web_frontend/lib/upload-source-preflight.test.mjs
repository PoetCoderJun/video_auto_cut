import test from "node:test";
import assert from "node:assert/strict";

import {
  getUploadSourcePreflightError,
  UploadSourcePreflightError,
} from "./upload-source-preflight.ts";

test("passes through incompatible source guidance instead of attempting upload-time transcoding", () => {
  const compatibility = {
    status: "incompatible",
    message: "当前浏览器无法解码该视频轨，检测到视频编码为 hev1。需要先转成兼容 MP4 后再导出。",
    videoCodec: "hev1",
    audioCodec: "mp4a.40.2",
  };

  const error = getUploadSourcePreflightError(compatibility);

  assert.ok(error instanceof UploadSourcePreflightError);
  assert.equal(error?.code, "SOURCE_INCOMPATIBLE");
  assert.equal(error?.message, compatibility.message);
  assert.equal(error?.causeMessage, compatibility.message);
});

test("maps blocked browser environments to the desktop Chrome upload guidance", () => {
  const compatibility = {
    status: "blocked",
    message: "当前浏览器不支持 VideoDecoder。",
    videoCodec: null,
    audioCodec: null,
  };

  const error = getUploadSourcePreflightError(compatibility);

  assert.ok(error instanceof UploadSourcePreflightError);
  assert.equal(error?.code, "BROWSER_UNSUPPORTED");
  assert.match(error?.message ?? "", /桌面版 Chrome/);
});

test("keeps compatible and unknown sources on the direct upload path", () => {
  assert.equal(
    getUploadSourcePreflightError({
      status: "compatible",
      message: "ok",
      videoCodec: "avc1.640028",
      audioCodec: "mp4a.40.2",
    }),
    null,
  );
  assert.equal(
    getUploadSourcePreflightError({
      status: "unknown",
      message: "skip check",
      videoCodec: null,
      audioCodec: null,
    }),
    null,
  );
});
