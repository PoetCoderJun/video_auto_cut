import test from "node:test";
import assert from "node:assert/strict";

import {
  choosePreferredVideoDimensions,
  parseMediaInfoVideoMetadata,
} from "./media-metadata.ts";

test("parseMediaInfoVideoMetadata extracts width height fps and duration", () => {
  const parsed = parseMediaInfoVideoMetadata({
    media: {
      track: [
        {
          "@type": "General",
          Duration: 12.587,
          OverallBitRate: 4200000,
        },
        {
          "@type": "Video",
          Width: 3840,
          Height: 2160,
          FrameRate: 59.94,
          Duration: 12.587,
          BitRate: 3900000,
          Format: "AVC",
        },
        {
          "@type": "Audio",
          BitRate: 192000,
        },
      ],
    },
  });

  assert.deepEqual(parsed, {
    width: 3840,
    height: 2160,
    fps: 59.94,
    durationSec: 12.587,
    overallBitrate: 4200000,
    videoBitrate: 3900000,
    audioBitrate: 192000,
    videoCodec: "AVC",
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
    overallBitrate: null,
    videoBitrate: null,
    audioBitrate: null,
    videoCodec: null,
  });
});

test("parseMediaInfoVideoMetadata returns null when no video track exists", () => {
  assert.equal(parseMediaInfoVideoMetadata({media: {track: [{"@type": "Audio"}]}}), null);
});

test("choosePreferredVideoDimensions prefers metadata when browser dimensions are smaller but aspect matches", () => {
  assert.deepEqual(
    choosePreferredVideoDimensions({
      browserWidth: 1728,
      browserHeight: 3072,
      metadataWidth: 2160,
      metadataHeight: 3840,
    }),
    {
      width: 2160,
      height: 3840,
      source: "metadata",
    }
  );
});

test("choosePreferredVideoDimensions keeps browser dimensions when metadata does not clearly represent the same frame", () => {
  assert.deepEqual(
    choosePreferredVideoDimensions({
      browserWidth: 1080,
      browserHeight: 1920,
      metadataWidth: 1440,
      metadataHeight: 1920,
    }),
    {
      width: 1080,
      height: 1920,
      source: "browser",
    }
  );
});
