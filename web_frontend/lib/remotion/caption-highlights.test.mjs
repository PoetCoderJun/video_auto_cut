import test from "node:test";
import assert from "node:assert/strict";

import {
  buildCaptionRenderChunks,
  getCaptionChunkFontScale,
  normalizeCaptionTokensForRender,
} from "./caption-highlights.ts";

test("plain highlight ranges still render as highlighted chunks without explicit style fields", () => {
  const tokens = normalizeCaptionTokensForRender(
    [
      {text: "重", start: 0, end: 0.5},
      {text: "点", start: 0.5, end: 1},
      {text: "词", start: 1, end: 1.5},
    ],
    {start: 0, end: 1.5},
    undefined,
    [{startToken: 0, endToken: 2}],
  );

  const chunks = buildCaptionRenderChunks(tokens);

  assert.equal(chunks.length, 2);
  assert.equal(chunks[0].text, "重点");
  assert.equal(chunks[0].isHighlighted, true);
  const highlightScale = getCaptionChunkFontScale(chunks[0]) ?? 1;
  assert.ok(highlightScale >= 1.16);
  assert.ok(highlightScale <= 1.3);
  assert.equal(chunks[1].text, "词");
  assert.equal(chunks[1].isHighlighted, false);
});
