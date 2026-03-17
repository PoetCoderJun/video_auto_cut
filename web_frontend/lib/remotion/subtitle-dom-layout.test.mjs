import test from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_SUBTITLE_MAX_LINES,
  fitSubtitleLayoutWithDom,
  getResponsiveOverlayTypography,
} from "./typography.ts";

const originalWindowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");

const setMockWindow = (getComputedStyle) => {
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    writable: true,
    value: {
      getComputedStyle,
    },
  });
};

const restoreWindow = () => {
  if (originalWindowDescriptor) {
    Object.defineProperty(globalThis, "window", originalWindowDescriptor);
    return;
  }
  delete globalThis.window;
};

const readFontSize = (style, fallback) => {
  const parsed = Number.parseFloat(style.fontSize ?? "");
  return Number.isFinite(parsed) ? parsed : fallback;
};

const makeElement = ({clientWidth, baseFontSize, measure}) => {
  const style = {};
  return {
    clientWidth,
    style,
    get scrollWidth() {
      return measure(readFontSize(style, baseFontSize)).scrollWidth;
    },
    get scrollHeight() {
      return measure(readFontSize(style, baseFontSize)).scrollHeight;
    },
  };
};

test.afterEach(() => {
  restoreWindow();
});

test("returns the base layout before the DOM is available", () => {
  restoreWindow();
  const layout = fitSubtitleLayoutWithDom({
    element: {clientWidth: 320, style: {fontSize: "42px"}},
    baseFontSize: 42,
    minFontSize: 18,
  });
  assert.deepEqual(layout, {fontSize: 42, maxLines: DEFAULT_SUBTITLE_MAX_LINES[0]});
});

test("returns the base layout when the subtitle box has not been laid out yet", () => {
  setMockWindow(() => ({lineHeight: "54px"}));
  const layout = fitSubtitleLayoutWithDom({
    element: {clientWidth: 0, style: {fontSize: "40px"}},
    baseFontSize: 40,
    minFontSize: 20,
  });
  assert.deepEqual(layout, {fontSize: 40, maxLines: DEFAULT_SUBTITLE_MAX_LINES[0]});
});

test("shrinks font size until width overflow disappears within the current line budget", () => {
  setMockWindow((element) => {
    const fontSize = readFontSize(element.style, 32);
    return {lineHeight: `${fontSize * 1.5}px`};
  });
  const element = makeElement({
    clientWidth: 300,
    baseFontSize: 32,
    measure: (fontSize) => ({
      scrollWidth: fontSize * 12,
      scrollHeight: fontSize * 1.5 * 2,
    }),
  });
  const layout = fitSubtitleLayoutWithDom({
    element,
    baseFontSize: 32,
    minFontSize: 18,
  });

  assert.deepEqual(layout, {fontSize: 25, maxLines: 2});
});

test("keeps the larger font and falls back to three lines when height is the only overflow source", () => {
  setMockWindow((element) => {
    const fontSize = readFontSize(element.style, 30);
    return {lineHeight: `${fontSize * 1.5}px`};
  });
  const element = makeElement({
    clientWidth: 640,
    baseFontSize: 30,
    measure: (fontSize) => {
      const lineHeight = fontSize * 1.5;
      return {
        scrollWidth: 240,
        scrollHeight: lineHeight * 2.4,
      };
    },
  });
  const layout = fitSubtitleLayoutWithDom({
    element,
    baseFontSize: 30,
    minFontSize: 18,
    maxLinesCandidates: [2, 3, 4],
  });

  assert.deepEqual(layout, {fontSize: 30, maxLines: 3});
});

test("accepts the exact tolerance boundary used by the DOM fitter", () => {
  setMockWindow((element) => {
    const fontSize = readFontSize(element.style, 24);
    return {lineHeight: `${fontSize * 1.5}px`};
  });
  const element = makeElement({
    clientWidth: 320,
    baseFontSize: 24,
    measure: (fontSize) => ({
      scrollWidth: 321,
      scrollHeight: fontSize * 1.5 * 2 + 1,
    }),
  });
  const layout = fitSubtitleLayoutWithDom({
    element,
    baseFontSize: 24,
    minFontSize: 16,
  });

  assert.deepEqual(layout, {fontSize: 24, maxLines: 2});
});

test("returns the minimum font size and last fallback line count when nothing can fit", () => {
  setMockWindow((element) => {
    const fontSize = readFontSize(element.style, 22);
    return {lineHeight: `${fontSize * 1.5}px`};
  });
  const element = makeElement({
    clientWidth: 120,
    baseFontSize: 22,
    measure: (fontSize) => ({
      scrollWidth: fontSize * 20,
      scrollHeight: fontSize * 1.5 * 6,
    }),
  });
  const layout = fitSubtitleLayoutWithDom({
    element,
    baseFontSize: 22,
    minFontSize: 12,
  });

  assert.deepEqual(layout, {fontSize: 12, maxLines: 4});
});

test("ignores previously applied line clamping when re-measuring subtitles", () => {
  setMockWindow((element) => {
    const fontSize = readFontSize(element.style, 32);
    return {lineHeight: `${fontSize * 1.5}px`};
  });
  const style = {
    display: "-webkit-box",
    overflow: "hidden",
    maxHeight: "72px",
    webkitLineClamp: "2",
    webkitBoxOrient: "vertical",
  };
  const element = {
    clientWidth: 300,
    style,
    get scrollWidth() {
      return 240;
    },
    get scrollHeight() {
      const fontSize = readFontSize(style, 32);
      const naturalHeight = fontSize * 1.5 * 3;
      const clampedHeight =
        style.overflow === "hidden" && style.maxHeight !== "none"
          ? Math.min(naturalHeight, Number.parseFloat(style.maxHeight))
          : naturalHeight;
      return clampedHeight;
    },
  };
  const layout = fitSubtitleLayoutWithDom({
    element,
    baseFontSize: 32,
    minFontSize: 18,
    maxLinesCandidates: [2, 3, 4],
  });

  assert.deepEqual(layout, {fontSize: 32, maxLines: 3});
  assert.equal(style.maxHeight, "72px");
  assert.equal(style.webkitLineClamp, "2");
});

test("stays within allowed lines across representative portrait resolutions", () => {
  const resolutions = [
    {width: 544, height: 960},
    {width: 720, height: 1268},
    {width: 720, height: 1280},
    {width: 750, height: 1334},
    {width: 828, height: 1792},
    {width: 1080, height: 1920},
  ];
  const naturalWidthAtOnePx = 14.2;

  for (const {width, height} of resolutions) {
    const typography = getResponsiveOverlayTypography({width, height});
    const clientWidth = Math.max(
      1,
      width * typography.subtitleMaxWidthRatio * typography.subtitleSafeWidthRatio - typography.subtitlePaddingX * 2
    );
    setMockWindow((element) => {
      const fontSize = readFontSize(element.style, typography.subtitleFontSize);
      return {lineHeight: `${fontSize * 1.5}px`};
    });
    const element = makeElement({
      clientWidth,
      baseFontSize: typography.subtitleFontSize,
      measure: (fontSize) => {
        const lineHeight = fontSize * 1.5;
        const naturalWidth = fontSize * naturalWidthAtOnePx;
        const lineCount = Math.max(1, Math.ceil(naturalWidth / clientWidth));
        return {
          scrollWidth: Math.min(clientWidth + 1, naturalWidth),
          scrollHeight: lineCount * lineHeight,
        };
      },
    });

    const layout = fitSubtitleLayoutWithDom({
      element,
      baseFontSize: typography.subtitleFontSize,
      minFontSize: Math.max(23, Math.floor(typography.subtitleFontSize * 0.44)),
    });

    const finalLineCount = Math.max(1, Math.ceil((layout.fontSize * naturalWidthAtOnePx) / clientWidth));
    assert.ok(
      finalLineCount <= layout.maxLines,
      `expected ${width}x${height} subtitle to fit within ${layout.maxLines} lines, got ${finalLineCount}`
    );
    assert.ok(
      layout.fontSize >= Math.max(23, Math.floor(typography.subtitleFontSize * 0.44)),
      `expected ${width}x${height} subtitle to stay above the portrait minimum, got ${layout.fontSize}`
    );
  }
});
