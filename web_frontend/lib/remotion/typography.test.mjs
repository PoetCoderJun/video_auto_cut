import test from "node:test";
import assert from "node:assert/strict";

import {
  fitSingleLineText,
  fitTextToBox,
  getResponsiveOverlayTypography,
  normalizeCaptionDisplayText,
  OVERLAY_FONT_FAMILY,
  wrapCaptionText,
} from "./typography.ts";

test("uses an explicit cross-platform Chinese font stack for overlays", () => {
  assert.match(OVERLAY_FONT_FAMILY, /Noto Sans SC/);
  assert.match(OVERLAY_FONT_FAMILY, /Source Han Sans SC/);
  assert.match(OVERLAY_FONT_FAMILY, /PingFang SC/);
});

test("normalizes repeated em dashes into a CJK-safe horizontal bar glyph", () => {
  assert.equal(normalizeCaptionDisplayText("流量就越高——但AI不会"), "流量就越高――但AI不会");
  assert.equal(normalizeCaptionDisplayText("讲错一次、两次、三次————没关系"), "讲错一次、两次、三次――――没关系");
});

test("keeps overlay typography readable on narrow portrait frames", () => {
  const typography = getResponsiveOverlayTypography({width: 720, height: 1280});

  assert.ok(typography.subtitleFontSize >= 50, `expected subtitle font >= 50, got ${typography.subtitleFontSize}`);
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

test("uses a larger but restrained progress label baseline on common landscape outputs", () => {
  const typography1080 = getResponsiveOverlayTypography({width: 1920, height: 1080});
  const typography4k = getResponsiveOverlayTypography({width: 3840, height: 2160});

  assert.ok(
    typography1080.progressLabelFontSize >= 18,
    `expected 1080p progress label font >= 18, got ${typography1080.progressLabelFontSize}`
  );
  assert.ok(
    typography4k.progressLabelFontSize >= 30,
    `expected 4k progress label font >= 30, got ${typography4k.progressLabelFontSize}`
  );
  assert.ok(
    typography4k.progressHeight >= 68,
    `expected 4k progress height >= 68, got ${typography4k.progressHeight}`
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

test("fits each progress label independently instead of forcing one global font size", () => {
  const wideShort = fitSingleLineText({
    text: "功能",
    maxWidth: 240,
    baseFontSize: 18,
    minFontSize: 12,
    maxFontSize: 30,
    maxHeight: 42,
    lineHeight: 1.2,
    targetWidthRatio: 0.84,
    horizontalPadding: 4,
    fontWeight: 700,
  });
  const narrowLong = fitSingleLineText({
    text: "这是一个更长的章节标题",
    maxWidth: 180,
    baseFontSize: 18,
    minFontSize: 12,
    maxFontSize: 30,
    maxHeight: 42,
    lineHeight: 1.2,
    targetWidthRatio: 0.84,
    horizontalPadding: 4,
    fontWeight: 700,
  });

  assert.equal(wideShort.visible, true, "expected wide short label to stay visible");
  assert.equal(narrowLong.visible, true, "expected narrow long label to stay visible");
  assert.ok(wideShort.fontSize > 18, `expected wide short label to grow beyond baseline, got ${wideShort.fontSize}`);
  assert.ok(
    narrowLong.fontSize < wideShort.fontSize,
    `expected narrow long label to be smaller, got ${narrowLong.fontSize} vs ${wideShort.fontSize}`
  );
});

test("wraps portrait subtitles into balanced lines instead of collapsing to tiny fonts", () => {
  const typography = getResponsiveOverlayTypography({width: 720, height: 1280});
  const wrapped = wrapCaptionText(
    "这是一个专门用于验证竖屏视频字幕自适应效果的长句子，需要在合理字号下分成多行显示。",
    {
      width: 720,
      fontSize: typography.subtitleFontSize,
      maxWidthRatio: typography.subtitleMaxWidthRatio,
      fontWeight: 700,
      fontFamily: OVERLAY_FONT_FAMILY,
    }
  );

  const lines = wrapped.split("\n");
  assert.ok(lines.length >= 2, `expected wrapped subtitle to span multiple lines, got ${lines.length}`);
  assert.ok(lines.every((line) => line.length > 0), "expected all wrapped lines to contain text");
});

test("wraps Chinese em dash subtitles conservatively on narrow frames", () => {
  const wrapped = wrapCaptionText("内容越紧凑，流量就越高——但AI不会替你做决定", {
    width: 360,
    fontSize: 36,
    maxWidthRatio: 0.9,
    safeWidthRatio: 0.86,
    fontWeight: 700,
    fontFamily: OVERLAY_FONT_FAMILY,
  });

  const lines = wrapped.split("\n");
  assert.ok(lines.length >= 2, `expected em dash subtitle to wrap, got ${lines.length}`);
  assert.ok(lines.every((line) => line.trim().length > 0), "expected wrapped em dash lines to stay non-empty");
  assert.ok(wrapped.includes("――"), "expected wrapped subtitle to use normalized horizontal bars");
});
