import test from "node:test";
import assert from "node:assert/strict";

import { ApiClientError } from "./api.ts";
import {
  getFriendlyUploadErrorMessage,
  getUploadIssueErrorMessage,
  getUploadIssueErrorName,
} from "./upload-error.ts";

test("maps generic fetch failures to a service connectivity message", () => {
  const message = getFriendlyUploadErrorMessage(new TypeError("Failed to fetch"));
  assert.equal(
    message,
    "无法连接登录或上传服务。请确认页面当前地址可正常访问，并检查前后端服务是否已启动后重试。"
  );
});

test("keeps browser local-processing guidance for encoder-like errors", () => {
  const message = getFriendlyUploadErrorMessage(new Error("flushing error"));
  assert.equal(
    message,
    "浏览器本地视频编码器初始化失败。请刷新页面后重试；如果仍失败，请改用最新版 Chrome，或先转成 H.264/AAC 的 MP4 后再上传。"
  );
});

test("upload issue helpers unwrap UploadPipelineError causes", () => {
  const cause = new ApiClientError(
    "音频上传失败，请稍后重试。",
    "DIRECT_UPLOAD_FAILED",
    403,
    "PUT 403: SignatureDoesNotMatch"
  );
  const wrapped = new Error(cause.message);
  wrapped.name = "UploadPipelineError";
  wrapped.cause = cause;

  assert.equal(getUploadIssueErrorName(wrapped), "ApiClientError");
  assert.equal(
    getUploadIssueErrorMessage(wrapped),
    "音频上传失败，请稍后重试。 [PUT 403: SignatureDoesNotMatch]"
  );
});
