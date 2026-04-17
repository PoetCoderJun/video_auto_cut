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

test("subtitle theme styles keep boxed presentation in CSS rather than typography tokens", () => {
  const boxed = getSubtitleThemeStyle({
    subtitleTheme: "box-white-on-black",
    boxMaxWidth: 520,
    textMaxWidth: 460,
  });
  const plain = getSubtitleThemeStyle({
    subtitleTheme: "text-white",
    boxMaxWidth: 520,
    textMaxWidth: 460,
  });

  assert.equal(boxed.maxWidth, 520);
  assert.match(String(boxed.padding), /em/);
  assert.match(String(boxed.borderRadius), /em/);
  assert.equal(plain.maxWidth, 460);
  assert.equal(plain.padding, "0");
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
