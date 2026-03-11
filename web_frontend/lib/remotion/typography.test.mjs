import test from "node:test";
import assert from "node:assert/strict";

import {
  fitSingleLineText,
  fitTextToBox,
  getResponsiveOverlayTypography,
  wrapCaptionText,
} from "./typography.ts";

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

test("keeps landscape overlays growing beyond 1080p", () => {
  const typography1080 = getResponsiveOverlayTypography({width: 1920, height: 1080});
  const typography1440 = getResponsiveOverlayTypography({width: 2560, height: 1440});

  assert.ok(
    typography1440.subtitleFontSize > typography1080.subtitleFontSize,
    `expected 1440p subtitle font > 1080p, got ${typography1080.subtitleFontSize} -> ${typography1440.subtitleFontSize}`
  );
  assert.ok(
    typography1440.chapterTitleFontSize > typography1080.chapterTitleFontSize,
    `expected 1440p chapter title font > 1080p, got ${typography1080.chapterTitleFontSize} -> ${typography1440.chapterTitleFontSize}`
  );
  assert.ok(
    typography1440.progressLabelFontSize > typography1080.progressLabelFontSize,
    `expected 1440p progress label font > 1080p, got ${typography1080.progressLabelFontSize} -> ${typography1440.progressLabelFontSize}`
  );
});

test("scales landscape overlays monotonically from HD through 8k", () => {
  const ladder = [
    getResponsiveOverlayTypography({width: 1280, height: 720}),
    getResponsiveOverlayTypography({width: 1920, height: 1080}),
    getResponsiveOverlayTypography({width: 2560, height: 1440}),
    getResponsiveOverlayTypography({width: 3840, height: 2160}),
    getResponsiveOverlayTypography({width: 7680, height: 4320}),
  ];

  for (let i = 1; i < ladder.length; i += 1) {
    assert.ok(
      ladder[i].subtitleFontSize > ladder[i - 1].subtitleFontSize,
      `expected subtitle font to grow at step ${i}, got ${ladder[i - 1].subtitleFontSize} -> ${ladder[i].subtitleFontSize}`
    );
    assert.ok(
      ladder[i].chapterTitleFontSize > ladder[i - 1].chapterTitleFontSize,
      `expected chapter title font to grow at step ${i}, got ${ladder[i - 1].chapterTitleFontSize} -> ${ladder[i].chapterTitleFontSize}`
    );
    assert.ok(
      ladder[i].progressHeight > ladder[i - 1].progressHeight,
      `expected progress height to grow at step ${i}, got ${ladder[i - 1].progressHeight} -> ${ladder[i].progressHeight}`
    );
    assert.ok(
      ladder[i].progressLabelFontSize > ladder[i - 1].progressLabelFontSize,
      `expected progress label font to grow at step ${i}, got ${ladder[i - 1].progressLabelFontSize} -> ${ladder[i].progressLabelFontSize}`
    );
  }
});

test("uses a doubled progress label baseline on common landscape outputs", () => {
  const typography1080 = getResponsiveOverlayTypography({width: 1920, height: 1080});
  const typography4k = getResponsiveOverlayTypography({width: 3840, height: 2160});

  assert.ok(
    typography1080.progressLabelFontSize >= 26,
    `expected 1080p progress label font >= 26, got ${typography1080.progressLabelFontSize}`
  );
  assert.ok(
    typography4k.progressLabelFontSize >= 42,
    `expected 4k progress label font >= 42, got ${typography4k.progressLabelFontSize}`
  );
  assert.ok(
    typography4k.progressHeight >= 94,
    `expected 4k progress height >= 94, got ${typography4k.progressHeight}`
  );
});

test("fits chapter titles into two lines before truncating", () => {
  const fitted = fitTextToBox({
    text: "这是一个很长的章节标题，用来验证章节卡片会先换行和缩字，而不是直接保持原字号溢出",
    maxWidth: 260,
    baseFontSize: 40,
    minFontSize: 22,
    maxLines: 2,
    fontWeight: 800,
  });

  assert.ok(fitted.fontSize <= 40, `expected fitted chapter font <= 40, got ${fitted.fontSize}`);
  assert.ok(fitted.fontSize >= 22, `expected fitted chapter font >= 22, got ${fitted.fontSize}`);
  assert.ok(fitted.lines.length <= 2, `expected at most 2 lines, got ${fitted.lines.length}`);
  assert.ok(fitted.text.length > 0, "expected fitted chapter text to stay non-empty");
});

test("shrinks progress labels to segment width and hides impossible ones", () => {
  const moderate = fitSingleLineText({
    text: "功能拆解",
    maxWidth: 72,
    baseFontSize: 18,
    minFontSize: 12,
    horizontalPadding: 4,
    fontWeight: 700,
  });
  assert.equal(moderate.visible, true, "expected moderate segment label to stay visible");
  assert.ok(moderate.fontSize <= 18, `expected fitted label font <= 18, got ${moderate.fontSize}`);

  const impossible = fitSingleLineText({
    text: "这是一个非常长而且不可能放进超窄进度片段里的标题",
    maxWidth: 36,
    baseFontSize: 18,
    minFontSize: 12,
    horizontalPadding: 4,
    fontWeight: 700,
  });
  assert.equal(impossible.visible, false, "expected impossible segment label to be hidden");
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
