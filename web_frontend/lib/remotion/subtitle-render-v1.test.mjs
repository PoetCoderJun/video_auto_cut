import test from "node:test";
import assert from "node:assert/strict";

import {coerceStitchVideoWebProps, coerceWebRenderConfig} from "./subtitle-render-v1.ts";

test("coerceWebRenderConfig adapts subtitle-render.v1 contracts", () => {
  const contract = {
    version: "subtitle-render.v1",
    output_name: "contract.mp4",
    composition: {width: 720, height: 1280, fps: 24},
    captions: [
      {
        index: 1,
        start: "00:00:00.000",
        end: "00:00:01.500",
        text: "字幕合同",
        label: {
          highlights: [{text: "字幕"}],
        },
      },
    ],
    segments: [{start: "00:00:02.000", end: "00:00:03.500"}],
    topics: [{title: "开场", start: 0, end: 1.5}],
    subtitleTheme: "white",
  };

  const config = coerceWebRenderConfig(contract);

  assert.equal(config.output_name, "contract.mp4");
  assert.deepEqual(config.input_props.segments, [{start: 2, end: 3.5}]);
  assert.equal(config.input_props.captions[0].tokens[0].text, "字");
  assert.equal(config.input_props.captions[0].label.highlights[0].text, "字幕");
  assert.equal(config.input_props.captions[0].label.highlights[0].startToken, 0);
  assert.equal(config.input_props.subtitleTheme, "white");
  assert.equal(config.composition.durationInFrames, 36);
});

test("coerceStitchVideoWebProps returns input props for subtitle-render.v1 contracts", () => {
  const props = coerceStitchVideoWebProps({
    contract: "subtitle-render.v1",
    video: {width: 1080, height: 1920, fps: 30},
    captions: [{index: 1, start: 0, end: 1, text: "hello"}],
    segments: [{start: 0, end: 1}],
    chapters: [{title: "第一章", start: 0, end: 1}],
  });

  assert.equal(props.width, 1080);
  assert.equal(props.height, 1920);
  assert.equal(props.topics[0].title, "第一章");
});
