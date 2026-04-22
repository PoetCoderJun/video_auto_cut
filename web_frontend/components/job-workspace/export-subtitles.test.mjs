import test from "node:test";
import assert from "node:assert/strict";

import {
  buildSrtDownloadFromRenderConfig,
  buildSrtFromRenderCaptions,
  formatSrtTimestamp,
} from "./export-subtitles.ts";

test("formatSrtTimestamp renders SRT-compliant timestamps", () => {
  assert.equal(formatSrtTimestamp(0), "00:00:00,000");
  assert.equal(formatSrtTimestamp(62.345), "00:01:02,345");
  assert.equal(formatSrtTimestamp(3661.9996), "01:01:02,000");
});

test("buildSrtFromRenderCaptions serializes multiline captions and skips invalid rows", () => {
  const srt = buildSrtFromRenderCaptions([
    {index: 9, start: 0, end: 1.2, text: "第一句"},
    {index: 10, start: 1.2, end: 3.4, text: "第二句\n第二行"},
    {index: 11, start: 4, end: 4, text: "无效"},
    {index: 12, start: 5, end: 6, text: "   "},
  ]);

  assert.equal(
    srt,
    [
      "1",
      "00:00:00,000 --> 00:00:01,200",
      "第一句",
      "",
      "2",
      "00:00:01,200 --> 00:00:03,400",
      "第二句",
      "第二行",
      "",
    ].join("\n"),
  );
});

test("buildSrtDownloadFromRenderConfig derives a .srt file name from output_name", () => {
  const result = buildSrtDownloadFromRenderConfig({
    output_name: "job_123_export.mp4",
    composition: {
      id: "test",
      fps: 30,
      width: 1080,
      height: 1920,
      durationInFrames: 300,
    },
    input_props: {
      src: "https://example.com/source.mp4",
      captions: [{index: 1, start: 0, end: 1, text: "你好"}],
      segments: [{start: 0, end: 1}],
      topics: [],
      fps: 30,
      width: 1080,
      height: 1920,
    },
  });

  assert.equal(result.fileName, "job_123_export.srt");
  assert.match(result.content, /00:00:00,000 --> 00:00:01,000/);
});
