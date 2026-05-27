import test from "node:test";
import assert from "node:assert/strict";

import {
  CHAPTER_CARD_PADDING_X_EM,
  PROGRESS_LABEL_PADDING_X_EM,
  SUBTITLE_PROGRESS_GAP_EM,
  SUBTITLE_BOX_PADDING_X_EM,
  getChapterCardStyle,
  getChapterCardTitleMaxWidth,
  getProgressLabelPaddingX,
  reserveSubtitleBottomForProgress,
  getSubtitleTextMaxWidth,
  getSubtitleTextShadowLayers,
  getSubtitleThemeStyle,
  getChapterCardBackdropLayers,
  getProgressTrackBackdropLayers,
} from "./overlay-presentation.ts";

test("lets the chapter card use natural height with fit-content width", () => {
  const style = getChapterCardStyle({cardMaxWidth: 420});

  assert.equal(style.width, "fit-content");
  assert.equal(style.maxWidth, 420);
  assert.equal("minHeight" in style, false);
  assert.equal(style.position, "relative");
  assert.equal("borderLeft" in style, false);
  assert.equal("boxShadow" in style, false);
  assert.equal("backdropFilter" in style, false);
});

test("derives chapter title width budget from CSS-side horizontal padding", () => {
  const titleMaxWidth = getChapterCardTitleMaxWidth({cardMaxWidth: 420, titleFontSize: 30});
  assert.equal(titleMaxWidth, 420 - 30 * CHAPTER_CARD_PADDING_X_EM * 2);
});

test("lets render-time chapter typography tokens drive the actual card box", () => {
  const style = getChapterCardStyle({
    cardMaxWidth: 720,
    gap: 14,
    paddingX: 32,
    paddingY: 24,
    radius: 18,
  });
  const titleMaxWidth = getChapterCardTitleMaxWidth({
    cardMaxWidth: 720,
    titleFontSize: 56,
    paddingX: 32,
  });

  assert.equal(style.gap, 14);
  assert.equal(style.padding, "24px 32px");
  assert.equal(style.borderRadius, 18);
  assert.equal(titleMaxWidth, 720 - 32 * 2);
});

test("boxed subtitle themes reduce text width by CSS-side padding while text themes do not", () => {
  assert.equal(
    getSubtitleTextMaxWidth({boxMaxWidth: 600, fontSize: 40, isBoxedTheme: true}),
    600 - 40 * SUBTITLE_BOX_PADDING_X_EM * 2
  );
  assert.equal(
    getSubtitleTextMaxWidth({boxMaxWidth: 600, fontSize: 40, isBoxedTheme: false}),
    600
  );
});

test("subtitle theme styles keep text-only rendering with export-safe paint", () => {
  const darkText = getSubtitleThemeStyle({
    subtitleTheme: "black",
    boxMaxWidth: 520,
    textMaxWidth: 460,
  });
  const lightText = getSubtitleThemeStyle({
    subtitleTheme: "white",
    boxMaxWidth: 520,
    textMaxWidth: 460,
  });

  assert.equal(darkText.maxWidth, 460);
  assert.equal("padding" in darkText, false);
  assert.equal("backgroundColor" in darkText, false);
  assert.equal(darkText.color, "#111827");
  assert.equal("WebkitTextStroke" in darkText, false);
  assert.equal("textShadow" in darkText, false);
  assert.equal(lightText.maxWidth, 460);
  assert.equal("borderRadius" in lightText, false);
  assert.equal(lightText.color, "#f9fbff");
  assert.equal("WebkitTextStroke" in lightText, false);
  assert.equal("textShadow" in lightText, false);
});

test("subtitle shadow layers use duplicated text instead of unsupported CSS text effects", () => {
  const darkLayers = getSubtitleTextShadowLayers("stroke");
  const lightLayers = getSubtitleTextShadowLayers("stroke-white");

  assert.ok(darkLayers.length >= 4);
  assert.ok(lightLayers.length >= 4);
  assert.ok(darkLayers.every((layer) => Number.isFinite(layer.translateXEm)));
  assert.ok(lightLayers.some((layer) => layer.color === "#020617"));
});

test("subtitle shadow layers avoid large soft offsets that encode as blurry text", () => {
  for (const theme of ["stroke", "stroke-white"]) {
    const layers = getSubtitleTextShadowLayers(theme);
    assert.ok(layers.length <= 5, `${theme} should use a small number of crisp text layers`);
    for (const layer of layers) {
      const offset = Math.hypot(layer.translateXEm, layer.translateYEm);
      assert.ok(
        offset <= 0.06,
        `${theme} layer ${layer.key} offset should stay crisp, got ${offset.toFixed(3)}em`
      );
    }
  }
});

test("overlay presentation avoids CSS effects that browser export cannot reproduce", () => {
  const chapterCard = getChapterCardStyle({cardMaxWidth: 420});
  const subtitleStyle = getSubtitleThemeStyle({
    subtitleTheme: "white",
    boxMaxWidth: 520,
    textMaxWidth: 460,
  });
  const unsupportedKeys = [
    "textShadow",
    "WebkitTextStroke",
    "paintOrder",
    "backdropFilter",
    "WebkitBackdropFilter",
    "filter",
    "mixBlendMode",
    "clipPath",
    "maskImage",
    "WebkitMaskImage",
  ];

  for (const style of [chapterCard, subtitleStyle]) {
    for (const key of unsupportedKeys) {
      assert.equal(key in style, false, `${key} should not be used in export overlay styles`);
    }
  }
  assert.doesNotMatch(String(chapterCard.boxShadow || ""), /\binset\b/i);
});

test("chapter and progress visuals use explicit export-safe layers", () => {
  const chapterCard = getChapterCardStyle({cardMaxWidth: 420});
  const chapterLayers = getChapterCardBackdropLayers({activeTopicIndex: 2});
  const progressLayers = getProgressTrackBackdropLayers();

  assert.equal("boxShadow" in chapterCard, false);
  assert.ok(chapterLayers.length >= 3, "expected chapter card depth to come from real layers");
  assert.ok(
    chapterLayers.some((layer) => layer.kind === "accent"),
    "expected chapter card to keep an explicit accent layer"
  );
  assert.ok(progressLayers.length >= 2, "expected progress track to keep explicit surface layers");

  for (const layer of [...chapterLayers, ...progressLayers]) {
    assert.equal("boxShadow" in layer.style, false);
    assert.equal("backdropFilter" in layer.style, false);
    assert.equal("WebkitBackdropFilter" in layer.style, false);
    assert.equal("filter" in layer.style, false);
  }
});

test("progress label fit budget follows CSS-side em padding", () => {
  const padding = getProgressLabelPaddingX(20);
  assert.equal(padding, Math.round(20 * PROGRESS_LABEL_PADDING_X_EM * 4) / 4);
});

test("subtitle default bottom reserves space above the progress bar", () => {
  const reserved = reserveSubtitleBottomForProgress({
    subtitleBottom: 65,
    progressBottom: 24,
    progressHeight: 40,
    subtitleFontSize: 48,
    showProgress: true,
  });

  assert.equal(
    reserved,
    24 + 40 + Math.max(10, Math.round(48 * SUBTITLE_PROGRESS_GAP_EM))
  );
});

test("subtitle reserve can use actual rendered subtitle height for highlighted captions", () => {
  const reserved = reserveSubtitleBottomForProgress({
    subtitleBottom: 65,
    progressBottom: 24,
    progressHeight: 40,
    subtitleFontSize: 48,
    subtitleVisualHeight: 92,
    showProgress: true,
  });

  assert.equal(reserved, 24 + 40 + Math.round(92 * 0.18));
});
