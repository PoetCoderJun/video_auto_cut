import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_OVERLAY_CONTROLS,
  normalizeOverlayScaleControls,
  resolveOverlayAnchorBottom,
  resolveOverlayVisualBottom,
} from "./overlay-controls.ts";

test("defaults keep highlight rendering enabled", () => {
  assert.equal(DEFAULT_OVERLAY_CONTROLS.showHighlights, true);
  assert.equal(normalizeOverlayScaleControls({}).showHighlights, true);
  assert.equal(normalizeOverlayScaleControls({showHighlights: false}).showHighlights, false);
});

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

test("maps visual overlay position controls across the full canvas range", () => {
  assert.equal(
    resolveOverlayVisualBottom({
      frameHeight: 1080,
      visualHeight: 84,
      currentPercent: 0,
    }),
    996
  );
  assert.equal(
    resolveOverlayVisualBottom({
      frameHeight: 1080,
      visualHeight: 84,
      currentPercent: 100,
    }),
    0
  );
  assert.equal(
    resolveOverlayVisualBottom({
      frameHeight: 1080,
      visualHeight: 84,
      currentPercent: 50,
    }),
    498
  );
});

test("keeps the default visual overlay anchors proportional across resolutions", () => {
  const low = resolveOverlayVisualBottom({
    frameHeight: 720,
    visualHeight: 42,
    currentPercent: DEFAULT_OVERLAY_CONTROLS.progressYPercent,
  });
  const high = resolveOverlayVisualBottom({
    frameHeight: 2160,
    visualHeight: 126,
    currentPercent: DEFAULT_OVERLAY_CONTROLS.progressYPercent,
  });

  assert.ok(
    Math.abs(low / (720 - 42) - high / (2160 - 126)) < 0.001,
    "expected default anchor ratios to stay visually proportional after quarter-pixel rounding"
  );
});
