import test from "node:test";
import assert from "node:assert/strict";

import { getRenderConfigTotalDuration } from "./utils.ts";

test("getRenderConfigTotalDuration uses the furthest relevant timeline endpoint", () => {
  const config = {
    output_name: "demo.mp4",
    composition: {
      id: "demo",
      fps: 30,
      width: 1920,
      height: 1080,
      durationInFrames: 300,
    },
    input_props: {
      src: "blob:test",
      fps: 30,
      width: 1920,
      height: 1080,
      captions: [{ index: 1, start: 0, end: 6.5, text: "字幕" }],
      topics: [{ title: "章节", start: 0, end: 5 }],
      segments: [
        { start: 0, end: 2.5 },
        { start: 4, end: 7.5 },
      ],
    },
  };

  assert.equal(getRenderConfigTotalDuration(config), 6.5);
});

test("getRenderConfigTotalDuration falls back to 1 when config is absent", () => {
  assert.equal(getRenderConfigTotalDuration(null), 1);
});
