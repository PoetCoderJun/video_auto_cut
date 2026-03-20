import test from "node:test";
import assert from "node:assert/strict";

import { parseMediaInfoVideoMetadata } from "./media-metadata.ts";

test("parseMediaInfoVideoMetadata extracts width height fps and duration", () => {
  const parsed = parseMediaInfoVideoMetadata({
    media: {
      track: [
        {
          "@type": "General",
          Duration: 12.587,
        },
        {
          "@type": "Video",
          Width: 3840,
          Height: 2160,
          FrameRate: 59.94,
          Duration: 12.587,
        },
      ],
    },
  });

  assert.deepEqual(parsed, {
    width: 3840,
    height: 2160,
    fps: 59.94,
    durationSec: 12.587,
  });
});

test("parseMediaInfoVideoMetadata falls back to stored dimensions and frame rate ratio", () => {
  const parsed = parseMediaInfoVideoMetadata({
    media: {
      track: [
        {
          "@type": "General",
          Duration: 65.6,
        },
        {
          "@type": "Video",
          Stored_Width: 3840,
          Stored_Height: 2160,
          FrameRate_Num: 60000,
          FrameRate_Den: 1001,
        },
      ],
    },
  });

  assert.deepEqual(parsed, {
    width: 3840,
    height: 2160,
    fps: 59.94,
    durationSec: 65.6,
  });
});

test("parseMediaInfoVideoMetadata returns null when no video track exists", () => {
  assert.equal(parseMediaInfoVideoMetadata({media: {track: [{"@type": "Audio"}]}}), null);
});
