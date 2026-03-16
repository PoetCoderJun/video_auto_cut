import test from "node:test";
import assert from "node:assert/strict";

import { isUnsupportedMobileUploadDevice } from "./device.ts";

function withMockBrowserEnv({
  hasWindow = true,
  navigatorValue,
}, run) {
  const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, "window");
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");

  if (hasWindow) {
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      writable: true,
      value: {},
    });
  } else {
    delete globalThis.window;
  }

  if (navigatorValue === undefined) {
    delete globalThis.navigator;
  } else {
    Object.defineProperty(globalThis, "navigator", {
      configurable: true,
      writable: true,
      value: navigatorValue,
    });
  }

  try {
    run();
  } finally {
    if (windowDescriptor) {
      Object.defineProperty(globalThis, "window", windowDescriptor);
    } else {
      delete globalThis.window;
    }

    if (navigatorDescriptor) {
      Object.defineProperty(globalThis, "navigator", navigatorDescriptor);
    } else {
      delete globalThis.navigator;
    }
  }
}

test("returns false outside the browser", () => {
  withMockBrowserEnv({ hasWindow: false, navigatorValue: undefined }, () => {
    assert.equal(isUnsupportedMobileUploadDevice(), false);
  });
});

test("blocks common mobile user agents", () => {
  withMockBrowserEnv(
    {
      navigatorValue: {
        userAgent:
          "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
        vendor: "Apple Computer, Inc.",
        platform: "iPhone",
        maxTouchPoints: 5,
      },
    },
    () => {
      assert.equal(isUnsupportedMobileUploadDevice(), true);
    }
  );
});

test("blocks mobile devices reported through userAgentData", () => {
  withMockBrowserEnv(
    {
      navigatorValue: {
        userAgent:
          "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36",
        vendor: "Google Inc.",
        platform: "Linux x86_64",
        maxTouchPoints: 0,
        userAgentData: {
          mobile: true,
        },
      },
    },
    () => {
      assert.equal(isUnsupportedMobileUploadDevice(), true);
    }
  );
});

test("blocks iPad desktop-mode browsers", () => {
  withMockBrowserEnv(
    {
      navigatorValue: {
        userAgent:
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15) AppleWebKit/605.1.15 Version/18.0 Safari/605.1.15",
        vendor: "Apple Computer, Inc.",
        platform: "MacIntel",
        maxTouchPoints: 5,
      },
    },
    () => {
      assert.equal(isUnsupportedMobileUploadDevice(), true);
    }
  );
});

test("keeps desktop Chrome upload enabled", () => {
  withMockBrowserEnv(
    {
      navigatorValue: {
        userAgent:
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36",
        vendor: "Google Inc.",
        platform: "MacIntel",
        maxTouchPoints: 0,
        userAgentData: {
          mobile: false,
        },
      },
    },
    () => {
      assert.equal(isUnsupportedMobileUploadDevice(), false);
    }
  );
});
