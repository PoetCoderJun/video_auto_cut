import test from "node:test";
import assert from "node:assert/strict";

import { getFriendlyCanRenderIssueMessage } from "./upload-render-validation.ts";

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
