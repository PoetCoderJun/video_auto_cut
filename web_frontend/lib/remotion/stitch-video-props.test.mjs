import test from "node:test";
import assert from "node:assert/strict";

import {buildStitchVideoInputProps} from "./stitch-video-props.ts";

const config = {
  output_name: "out.mp4",
  composition: {
    id: "StitchVideoWeb",
    fps: 30,
    width: 1920,
    height: 1080,
    durationInFrames: 90,
  },
  input_props: {
    src: "old-src",
    captions: [{index: 1, start: 0, end: 1, text: "字幕"}],
    topics: [{title: "章节", start: 0, end: 1}],
    segments: [{start: 2, end: 3}],
    fps: 24,
    width: 720,
    height: 1280,
    overlayReferenceWidth: 720,
    overlayReferenceHeight: 1280,
    subtitleTheme: "stroke",
    showHighlights: false,
  },
};

test("buildStitchVideoInputProps keeps preview and export prop overrides identical", () => {
  const props = buildStitchVideoInputProps({
    config,
    src: "blob:render-source",
    subtitleTheme: "stroke-white",
    overlayControls: {
      subtitleScale: 1.2,
      subtitleYPercent: 88,
      progressScale: 1.1,
      progressYPercent: 96,
      chapterScale: 0.9,
      showSubtitles: true,
      showHighlights: true,
      showProgress: false,
      showChapter: true,
      progressLabelMode: "single",
    },
  });

  assert.equal(props.src, "blob:render-source");
  assert.equal(props.fps, 30);
  assert.equal(props.width, 1920);
  assert.equal(props.height, 1080);
  assert.equal(props.overlayReferenceWidth, 720);
  assert.equal(props.overlayReferenceHeight, 1280);
  assert.equal(props.subtitleTheme, "stroke-white");
  assert.equal(props.showHighlights, true);
  assert.equal(props.showProgress, false);
  assert.equal(props.progressLabelMode, "single");
});
