import test from "node:test";
import assert from "node:assert/strict";

import { resolveAuthClientBaseURL } from "./auth-client.ts";

test("resolveAuthClientBaseURL prefers current browser origin", () => {
  const originalWindow = globalThis.window;
  globalThis.window = {
    location: {
      origin: "http://localhost:3000/",
    },
  };

  try {
    assert.equal(resolveAuthClientBaseURL(), "http://localhost:3000");
  } finally {
    globalThis.window = originalWindow;
  }
});
