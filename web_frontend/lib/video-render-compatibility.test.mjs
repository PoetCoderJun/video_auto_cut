import test from "node:test";
import assert from "node:assert/strict";

import {
  MOCK_CAN_DECODE_FALSE_MARKER,
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
