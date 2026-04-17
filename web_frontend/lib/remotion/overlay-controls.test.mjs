import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_OVERLAY_CONTROLS,
  resolveOverlayAnchorBottom,
} from "./overlay-controls.ts";

test("keeps overlay bottom anchors at their baseline when controls stay at defaults", () => {
  assert.equal(
    resolveOverlayAnchorBottom({
      frameHeight: 1080,
      baselineBottom: 65,
      currentPercent: DEFAULT_OVERLAY_CONTROLS.subtitleYPercent,
      defaultPercent: DEFAULT_OVERLAY_CONTROLS.subtitleYPercent,
    }),
    65
  );
  assert.equal(
    resolveOverlayAnchorBottom({
      frameHeight: 1080,
      baselineBottom: 24,
      currentPercent: DEFAULT_OVERLAY_CONTROLS.progressYPercent,
      defaultPercent: DEFAULT_OVERLAY_CONTROLS.progressYPercent,
    }),
    24
  );
});

test("moving the Y slider up increases bottom spacing and moving it down reduces it", () => {
  const raised = resolveOverlayAnchorBottom({
    frameHeight: 1080,
    baselineBottom: 24,
    currentPercent: 92,
    defaultPercent: DEFAULT_OVERLAY_CONTROLS.progressYPercent,
  });
  const lowered = resolveOverlayAnchorBottom({
    frameHeight: 1080,
    baselineBottom: 24,
    currentPercent: 100,
    defaultPercent: DEFAULT_OVERLAY_CONTROLS.progressYPercent,
  });

  assert.ok(raised > 24, `expected raised bottom spacing > 24, got ${raised}`);
  assert.ok(lowered < 24, `expected lowered bottom spacing < 24, got ${lowered}`);
  assert.ok(lowered >= 0, `expected bottom spacing clamp >= 0, got ${lowered}`);
});
