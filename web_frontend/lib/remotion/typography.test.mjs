import test from "node:test";
import assert from "node:assert/strict";

import {getResponsiveOverlayTypography, wrapCaptionText} from "./typography.ts";

test("keeps overlay typography readable on narrow portrait frames", () => {
  const typography = getResponsiveOverlayTypography({width: 720, height: 1280});

  assert.ok(typography.subtitleFontSize >= 78, `expected subtitle font >= 78, got ${typography.subtitleFontSize}`);
  assert.ok(
    typography.chapterTitleFontSize >= 26,
    `expected chapter title font >= 26, got ${typography.chapterTitleFontSize}`
  );
  assert.ok(
    typography.progressLabelFontSize >= 12,
    `expected progress label font >= 12, got ${typography.progressLabelFontSize}`
  );
  assert.ok(
    typography.subtitleMaxWidthRatio >= 0.92,
    `expected subtitle width ratio >= 0.92, got ${typography.subtitleMaxWidthRatio}`
  );
});

test("caps typography growth on large landscape frames", () => {
  const typography = getResponsiveOverlayTypography({width: 2560, height: 1440});

  assert.ok(typography.subtitleFontSize <= 92, `expected subtitle font <= 92, got ${typography.subtitleFontSize}`);
  assert.ok(
    typography.chapterTitleFontSize <= 40,
    `expected chapter title font <= 40, got ${typography.chapterTitleFontSize}`
  );
  assert.ok(
    typography.progressLabelFontSize <= 17,
    `expected progress label font <= 17, got ${typography.progressLabelFontSize}`
  );
});

test("wraps portrait subtitles into balanced lines instead of collapsing to tiny fonts", () => {
  const typography = getResponsiveOverlayTypography({width: 720, height: 1280});
  const wrapped = wrapCaptionText(
    "这是一个专门用于验证竖屏视频字幕自适应效果的长句子，需要在合理字号下分成多行显示。",
    {width: 720, fontSize: typography.subtitleFontSize, maxWidthRatio: typography.subtitleMaxWidthRatio}
  );

  const lines = wrapped.split("\n");
  assert.ok(lines.length >= 2, `expected wrapped subtitle to span multiple lines, got ${lines.length}`);
  assert.ok(lines.every((line) => line.length > 0), "expected all wrapped lines to contain text");
});
