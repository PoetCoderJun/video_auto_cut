import test from "node:test";
import assert from "node:assert/strict";

import {getSourceVideoMismatchMessage} from "./source-video-guard.ts";

test("getSourceVideoMismatchMessage skips duration guard for cut proxy render sources", () => {
  const result = getSourceVideoMismatchMessage(
    "source.mp4",
    {
      width: 3840,
      height: 2160,
      fps: 60,
      duration_sec: 86,
    },
    {
      output_name: "job_x_export.mp4",
      composition: {
        id: "StitchVideoWeb",
        fps: 60,
        width: 3840,
        height: 2160,
        durationInFrames: 3600,
      },
      input_props: {
        src: "/api/v1/jobs/job_x/render/source-video",
        sourceKind: "cut-proxy",
        captions: [],
        segments: [{start: 0, end: 180}],
        topics: [],
        fps: 60,
        width: 3840,
        height: 2160,
      },
    },
  );

  assert.equal(result, null);
});
