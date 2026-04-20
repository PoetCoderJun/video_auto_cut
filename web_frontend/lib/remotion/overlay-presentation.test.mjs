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
  getSubtitleThemeStyle,
} from "./overlay-presentation.ts";

test("lets the chapter card use natural height with fit-content width", () => {
  const style = getChapterCardStyle({cardMaxWidth: 420});

  assert.equal(style.width, "fit-content");
  assert.equal(style.maxWidth, 420);
  assert.equal("minHeight" in style, false);
});

test("derives chapter title width budget from CSS-side horizontal padding", () => {
  const titleMaxWidth = getChapterCardTitleMaxWidth({cardMaxWidth: 420, titleFontSize: 30});
  assert.equal(titleMaxWidth, 420 - 30 * CHAPTER_CARD_PADDING_X_EM * 2);
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

test("subtitle theme styles now keep text-only rendering with no background box", () => {
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
  assert.equal(lightText.maxWidth, 460);
  assert.equal("borderRadius" in lightText, false);
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
    24 + 40 + Math.max(12, Math.round(48 * SUBTITLE_PROGRESS_GAP_EM))
  );
});
