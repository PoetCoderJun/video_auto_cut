#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import {spawn} from "node:child_process";
import {setTimeout as sleep} from "node:timers/promises";

const repoRoot = process.cwd();
const chromeBinary =
  process.env.E2E_CHROME_BIN ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const cdpPort = Number.parseInt(process.env.E2E_CDP_PORT || "9222", 10);
const baseUrl = (process.env.E2E_BASE_URL || "http://127.0.0.1:3000").replace(/\/$/, "");
const authBaseUrl = `${baseUrl}/api/auth`;
const sourceFile = path.resolve(
  repoRoot,
  process.env.E2E_SOURCE_FILE || "test_data/raw/AI1.MOV",
);
const downloadDir = path.resolve(
  repoRoot,
  process.env.E2E_DOWNLOAD_DIR || "workdir/e2e_browser_downloads",
);
const chromeProfileDir = path.resolve(
  repoRoot,
  process.env.E2E_CHROME_PROFILE_DIR || "workdir/e2e_chrome_profile",
);
const artifactsDir = path.resolve(
  repoRoot,
  process.env.E2E_ARTIFACTS_DIR || "workdir/e2e_browser_artifacts",
);
const startedAtIso = new Date().toISOString();
const email = process.env.E2E_EMAIL || "e2e-web-smoke@example.com";
const password = process.env.E2E_PASSWORD || "E2E-Web-Smoke-20260420!";
const headed = String(process.env.E2E_HEADLESS || "").trim() !== "1";

const timeouts = {
  navigationMs: 60_000,
  uploadMs: 15 * 60_000,
  processingMs: 45 * 60_000,
  exportMs: 20 * 60_000,
};

function ensureDir(dir) {
  fs.mkdirSync(dir, {recursive: true});
}

function fail(message, details) {
  const error = new Error(message);
  if (details !== undefined) {
    error.details = details;
  }
  throw error;
}

function parseSetCookieValue(setCookieHeader, cookieName) {
  const escaped = cookieName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = String(setCookieHeader || "").match(
    new RegExp(`(?:^|,\\s*)${escaped}=([^;]+)`),
  );
  return match ? String(match[1] || "").trim() : "";
}

async function fetchJson(url, init) {
  const response = await fetch(url, init);
  if (!response.ok) {
    fail(`HTTP ${response.status} for ${url}`, await response.text());
  }
  return response.json();
}

class CdpClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.nextId = 0;
    this.pending = new Map();
    this.eventHandlers = new Map();
    this.consoleMessages = [];
    this.pageErrors = [];
  }

  async connect() {
    this.ws = new WebSocket(this.wsUrl);
    await new Promise((resolve, reject) => {
      const onOpen = () => resolve();
      const onError = (event) => reject(event.error || new Error("WebSocket connection failed"));
      this.ws.addEventListener("open", onOpen, {once: true});
      this.ws.addEventListener("error", onError, {once: true});
    });
    this.ws.addEventListener("message", (event) => {
      const payload = JSON.parse(String(event.data));
      if (payload.id) {
        const waiter = this.pending.get(payload.id);
        if (!waiter) {
          return;
        }
        this.pending.delete(payload.id);
        if (payload.error) {
          waiter.reject(new Error(payload.error.message || "CDP command failed"));
          return;
        }
        waiter.resolve(payload.result);
        return;
      }

      if (payload.method === "Runtime.consoleAPICalled") {
        const text = (payload.params?.args || [])
          .map((item) => item.value ?? item.description ?? "")
          .join(" ")
          .trim();
        if (text) {
          this.consoleMessages.push({
            type: payload.params?.type || "log",
            text,
          });
        }
      }

      if (payload.method === "Runtime.exceptionThrown") {
        const text = String(
          payload.params?.exceptionDetails?.text ||
            payload.params?.exceptionDetails?.exception?.description ||
            "Unknown page exception",
        ).trim();
        this.pageErrors.push(text);
      }

      const handlers = this.eventHandlers.get(payload.method);
      if (handlers) {
        for (const handler of handlers) {
          try {
            handler(payload.params || {});
          } catch {
            // Ignore handler failures to keep the CDP session alive.
          }
        }
      }
    });
  }

  on(method, handler) {
    const handlers = this.eventHandlers.get(method) || [];
    handlers.push(handler);
    this.eventHandlers.set(method, handlers);
  }

  async send(method, params = {}) {
    const id = ++this.nextId;
    const message = JSON.stringify({id, method, params});
    const result = new Promise((resolve, reject) => {
      this.pending.set(id, {resolve, reject});
    });
    this.ws.send(message);
    return result;
  }

  async close() {
    if (!this.ws) {
      return;
    }
    await new Promise((resolve) => {
      this.ws.addEventListener("close", () => resolve(), {once: true});
      this.ws.close();
    });
  }
}

async function waitFor(predicate, description, timeoutMs, intervalMs = 500) {
  const deadline = Date.now() + timeoutMs;
  let lastValue = null;
  while (Date.now() < deadline) {
    lastValue = await predicate();
    if (lastValue) {
      return lastValue;
    }
    await sleep(intervalMs);
  }
  fail(`Timed out waiting for ${description}`, lastValue);
}

async function evalExpression(cdp, expression, options = {}) {
  const result = await cdp.send("Runtime.evaluate", {
    expression,
    awaitPromise: Boolean(options.awaitPromise),
    returnByValue: options.returnByValue !== false,
  });
  if (result.exceptionDetails) {
    fail(`Page evaluation failed for expression: ${expression}`, result.exceptionDetails);
  }
  return options.returnByValue === false ? result.result : result.result?.value;
}

async function setInputValue(cdp, selector, value) {
  const focused = await evalExpression(
    cdp,
    `
      (() => {
        const input = document.querySelector(${JSON.stringify(selector)});
        if (!input) return false;
        input.focus();
        input.select?.();
        return true;
      })()
    `,
  );
  if (focused === false) {
    fail(`Input not found for selector ${selector}`);
  }
  await cdp.send("Input.insertText", {text: value});
  await waitFor(
    async () => {
      const currentValue = await evalExpression(
        cdp,
        `document.querySelector(${JSON.stringify(selector)})?.value || ""`,
      );
      return currentValue === value ? currentValue : null;
    },
    `input value for ${selector}`,
    10_000,
    200,
  );
}

async function clickSelector(cdp, selector) {
  const expression = `
    (() => {
      const element = document.querySelector(${JSON.stringify(selector)});
      if (!element) return false;
      element.click();
      return true;
    })()
  `;
  const ok = await evalExpression(cdp, expression);
  if (!ok) {
    fail(`Clickable element not found for selector ${selector}`);
  }
}

async function waitForButtonSelector(cdp, label, timeoutMs, markerAttr) {
  return waitFor(
    async () => {
      return (
        (await evalExpression(
          cdp,
          `
            (() => {
              const button = Array.from(document.querySelectorAll('button')).find((item) =>
                (item.innerText || '').includes(${JSON.stringify(label)})
              );
              if (!button) return null;
              button.setAttribute(${JSON.stringify(markerAttr)}, '1');
              return '[' + ${JSON.stringify(markerAttr)} + '="1"]';
            })()
          `,
        )) || null
      );
    },
    `button "${label}"`,
    timeoutMs,
    500,
  );
}

async function getBodyText(cdp) {
  return String(
    (await evalExpression(
      cdp,
      "document.body ? document.body.innerText : ''",
    )) || "",
  );
}

async function waitForText(cdp, text, timeoutMs) {
  return waitFor(
    async () => {
      const bodyText = await getBodyText(cdp);
      return bodyText.includes(text) ? bodyText : null;
    },
    `text "${text}"`,
    timeoutMs,
  );
}

async function waitForPath(cdp, expectedPath, timeoutMs) {
  return waitFor(
    async () => {
      const pathname = await evalExpression(cdp, "location.pathname");
      return pathname === expectedPath ? pathname : null;
    },
    `path ${expectedPath}`,
    timeoutMs,
  );
}

async function waitForFileInput(cdp, selector, timeoutMs) {
  return waitFor(
    async () => {
      const node = await cdp.send("DOM.getDocument", {depth: -1, pierce: true});
      const query = await cdp.send("DOM.querySelector", {
        nodeId: node.root.nodeId,
        selector,
      });
      return query.nodeId ? query.nodeId : null;
    },
    `file input ${selector}`,
    timeoutMs,
  );
}

async function setFileInputFiles(cdp, selector, files) {
  const nodeId = await waitForFileInput(cdp, selector, timeouts.navigationMs);
  await cdp.send("DOM.setFileInputFiles", {nodeId, files});
}

async function captureScreenshot(cdp, fileName) {
  const result = await cdp.send("Page.captureScreenshot", {format: "png"});
  const filePath = path.join(artifactsDir, fileName);
  fs.writeFileSync(filePath, Buffer.from(result.data, "base64"));
  return filePath;
}

async function startChrome() {
  fs.rmSync(chromeProfileDir, {recursive: true, force: true});
  ensureDir(downloadDir);
  ensureDir(chromeProfileDir);
  ensureDir(artifactsDir);
  const chromeArgs = [
    `--remote-debugging-port=${cdpPort}`,
    `--user-data-dir=${chromeProfileDir}`,
    "--no-first-run",
    "--no-default-browser-check",
  ];
  if (!headed) {
    chromeArgs.push("--headless=new", "--disable-gpu");
  }
  chromeArgs.push("about:blank");
  return spawn(chromeBinary, chromeArgs, {
    stdio: ["ignore", "ignore", "pipe"],
  });
}

async function getCdpWebSocketUrl() {
  return waitFor(
    async () => {
      try {
        const version = await fetchJson(`http://127.0.0.1:${cdpPort}/json/version`);
        return version.webSocketDebuggerUrl || null;
      } catch {
        return null;
      }
    },
    "Chrome remote debugging endpoint",
    20_000,
  );
}

async function createTarget() {
  const response = await fetch(
    `http://127.0.0.1:${cdpPort}/json/new?${encodeURIComponent("about:blank")}`,
    {method: "PUT"},
  );
  if (!response.ok) {
    fail(`Failed to create Chrome target: ${response.status}`, await response.text());
  }
  return response.json();
}

async function signInViaApi() {
  const response = await fetch(`${authBaseUrl}/sign-in/email`, {
    method: "POST",
    headers: {
      Origin: baseUrl,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      email,
      password,
    }),
  });
  const text = await response.text();
  if (!response.ok) {
    fail(`Sign-in failed: HTTP ${response.status}`, text);
  }
  const setCookieHeader = response.headers.get("set-cookie") || "";
  const sessionCookie = parseSetCookieValue(setCookieHeader, "better-auth.session_token");
  if (!sessionCookie) {
    fail("Sign-in succeeded but no better-auth.session_token cookie was returned", text);
  }
  return sessionCookie;
}

function summarizeConsole(cdp) {
  return {
    consoleMessages: cdp.consoleMessages.slice(-40),
    pageErrors: cdp.pageErrors.slice(-20),
  };
}

function listDownloadedMediaFiles() {
  return fs
    .readdirSync(downloadDir)
    .filter((name) => /\.(mp4|webm)$/i.test(name))
    .sort();
}

async function waitForEditorConfirmResult(cdp, timeoutMs) {
  return waitFor(
    async () => {
      const bodyText = await getBodyText(cdp);
      if (bodyText.includes("导出设置")) {
        return "export";
      }
      if (
        bodyText.includes("test document revision conflict") ||
        bodyText.includes("保存失败") ||
        bodyText.includes("revision conflict")
      ) {
        return "conflict";
      }
      return null;
    },
    "editor confirm result",
    timeoutMs,
    500,
  );
}

async function extractBrowserDownloadToFile(cdp) {
  await evalExpression(
    cdp,
    `(() => {
      if (!window.__e2eDownloadHookInstalled) {
        window.__e2eDownloadHookInstalled = true;
        window.__e2eLastDownload = null;
        const originalClick = HTMLAnchorElement.prototype.click;
        HTMLAnchorElement.prototype.click = function(...args) {
          try {
            if (this.download) {
              window.__e2eLastDownload = {href: this.href, download: this.download};
            }
          } catch {
            // ignore
          }
          return originalClick.apply(this, args);
        };
      }
      return true;
    })()`,
  );

  const downloadSelector = await waitForButtonSelector(
    cdp,
    "下载上次导出",
    timeouts.navigationMs,
    "data-e2e-download",
  );
  await clickSelector(cdp, downloadSelector);

  const downloadInfoRaw = await waitFor(
    async () =>
      (await evalExpression(
        cdp,
        "JSON.stringify(window.__e2eLastDownload)",
      )) || null,
    "captured browser download link",
    10_000,
    200,
  );
  const downloadInfo = JSON.parse(downloadInfoRaw);
  if (!downloadInfo?.href || !downloadInfo?.download) {
    fail("Browser download metadata was not captured", downloadInfo);
  }

  const outputPath = path.join(downloadDir, String(downloadInfo.download).trim());
  const blobUrl = String(downloadInfo.href);
  const chunkSize = 256 * 1024;
  const size = Number(
    await evalExpression(
      cdp,
      `fetch(${JSON.stringify(blobUrl)}).then(async (response) => {
        const blob = await response.blob();
        window.__e2eBlob = blob;
        return blob.size;
      })`,
      {awaitPromise: true},
    ),
  );
  if (!Number.isFinite(size) || size <= 0) {
    fail("Invalid browser blob size", {blobUrl, size});
  }

  const fd = fs.openSync(outputPath, "w");
  try {
    for (let offset = 0; offset < size; offset += chunkSize) {
      const end = Math.min(size, offset + chunkSize);
      const base64 = String(
        await evalExpression(
          cdp,
          `window.__e2eBlob.slice(${offset}, ${end}).arrayBuffer().then((buffer) => {
            const bytes = new Uint8Array(buffer);
            let binary = "";
            const block = 0x8000;
            for (let i = 0; i < bytes.length; i += block) {
              binary += String.fromCharCode(...bytes.subarray(i, i + block));
            }
            return btoa(binary);
          })`,
          {awaitPromise: true},
        ),
      );
      const chunk = Buffer.from(base64, "base64");
      fs.writeSync(fd, chunk, 0, chunk.length, offset);
    }
  } finally {
    fs.closeSync(fd);
  }

  return path.basename(outputPath);
}

async function main() {
  if (!fs.existsSync(sourceFile)) {
    fail(`Source file not found: ${sourceFile}`);
  }
  if (!fs.existsSync(chromeBinary)) {
    fail(`Chrome binary not found: ${chromeBinary}`);
  }

  const chromeProcess = await startChrome();
  let cdp = null;
  let targetId = null;
  const report = {
    startedAt: startedAtIso,
    email,
    sourceFile,
    downloadDir,
    artifactsDir,
    steps: [],
  };

  try {
    const sessionCookie = await signInViaApi();
    const browserWsUrl = await getCdpWebSocketUrl();
    const browserCdp = new CdpClient(browserWsUrl);
    await browserCdp.connect();
    await browserCdp.send("Browser.setDownloadBehavior", {
      behavior: "allow",
      downloadPath: downloadDir,
      eventsEnabled: true,
    });

    const createdTarget = await createTarget();
    targetId = createdTarget.id;
    cdp = new CdpClient(createdTarget.webSocketDebuggerUrl);
    await cdp.connect();
    await cdp.send("Page.enable");
    await cdp.send("Runtime.enable");
    await cdp.send("DOM.enable");
    await cdp.send("Network.enable");

    let navigationResolvers = [];
    cdp.on("Page.loadEventFired", () => {
      for (const resolve of navigationResolvers) {
        resolve();
      }
      navigationResolvers = [];
    });
    const waitForLoad = () =>
      new Promise((resolve) => {
        navigationResolvers.push(resolve);
      });

    await cdp.send("Network.setCookie", {
      name: "better-auth.session_token",
      value: sessionCookie,
      url: baseUrl,
      httpOnly: true,
      sameSite: "Lax",
      path: "/",
    });

    report.steps.push({name: "open-home", url: `${baseUrl}/`});
    const initialLoad = waitForLoad();
    await cdp.send("Page.navigate", {
      url: `${baseUrl}/`,
    });
    await initialLoad;
    await waitForText(cdp, "点击或拖拽上传视频", timeouts.navigationMs);
    await waitFor(
      async () => {
        const bodyText = await getBodyText(cdp);
        return bodyText.includes(email) ? bodyText : null;
      },
      "signed-in home state",
      timeouts.navigationMs,
    );
    report.steps.push({name: "signed-in"});
    await waitForFileInput(cdp, "input[type='file']", timeouts.navigationMs);

    await setFileInputFiles(cdp, "input[type='file']", [sourceFile]);
    report.steps.push({name: "upload-started"});
    await waitForText(cdp, "请保持页面开启，我们会自动继续处理。", timeouts.uploadMs);
    report.steps.push({
      name: "job-workspace-mounted",
      path: await evalExpression(cdp, "location.pathname"),
    });

    await waitFor(
      async () => {
        const bodyText = await getBodyText(cdp);
        if (
          bodyText.includes("保存并进入导出") ||
          bodyText.includes("导出设置")
        ) {
          return bodyText;
        }
        return null;
      },
      "editor/export-ready state",
      timeouts.processingMs,
      2_000,
    );
    report.steps.push({name: "processing-complete"});
    await captureScreenshot(cdp, "editor-ready.png");

    const exportAlreadyVisible = await evalExpression(
      cdp,
      `
        (() => {
          const bodyText = document.body ? document.body.innerText : "";
          return bodyText.includes("导出设置");
        })()
      `,
    );
    if (!exportAlreadyVisible) {
      let enteredExport = false;
      for (let attempt = 1; attempt <= 3; attempt += 1) {
        const confirmSelector = await waitForButtonSelector(
          cdp,
          "保存并进入导出",
          timeouts.navigationMs,
          "data-e2e-confirm",
        );
        await clickSelector(cdp, confirmSelector);
        const result = await waitForEditorConfirmResult(cdp, timeouts.navigationMs);
        if (result === "export") {
          enteredExport = true;
          break;
        }
        report.steps.push({name: "confirm-retried", attempt});
        await sleep(1_500);
      }
      if (!enteredExport) {
        fail("Failed to enter export step after retrying editor confirmation.");
      }
    }
    report.steps.push({name: "entered-export"});
    await captureScreenshot(cdp, "export-ready.png");

    const exportSelector = await waitForButtonSelector(
      cdp,
      "导出视频",
      timeouts.navigationMs,
      "data-e2e-export",
    );
    await clickSelector(cdp, exportSelector);
    await waitForText(cdp, "下载上次导出", timeouts.exportMs);
    let downloadedFiles = listDownloadedMediaFiles();
    if (downloadedFiles.length === 0) {
      const extracted = await extractBrowserDownloadToFile(cdp);
      downloadedFiles = [extracted];
    }
    await waitFor(
      async () => {
        const files = listDownloadedMediaFiles();
        if (files.length > 0) {
          return files;
        }
        return null;
      },
      "finished export download",
      timeouts.exportMs,
      1_000,
    );
    await captureScreenshot(cdp, "export-done.png");
    report.steps.push({
      name: "export-finished",
      downloadedFiles: listDownloadedMediaFiles(),
    });

    const summary = {
      ok: true,
      ...report,
      ...summarizeConsole(cdp),
    };
    fs.writeFileSync(
      path.join(artifactsDir, "e2e-summary.json"),
      JSON.stringify(summary, null, 2),
      "utf8",
    );
    console.log(JSON.stringify(summary, null, 2));
  } catch (error) {
    const failure = {
      ok: false,
      ...report,
      error: {
        message: error instanceof Error ? error.message : String(error),
        details: error?.details ?? null,
      },
      ...(cdp ? summarizeConsole(cdp) : {}),
    };
    fs.writeFileSync(
      path.join(artifactsDir, "e2e-summary.json"),
      JSON.stringify(failure, null, 2),
      "utf8",
    );
    if (cdp) {
      try {
        await captureScreenshot(cdp, "failure.png");
      } catch {
        // Ignore screenshot failures on teardown.
      }
    }
    console.error(JSON.stringify(failure, null, 2));
    process.exitCode = 1;
  } finally {
    if (cdp) {
      try {
        await cdp.close();
      } catch {
        // Ignore teardown failures.
      }
    }
    if (targetId) {
      try {
        await fetch(`http://127.0.0.1:${cdpPort}/json/close/${targetId}`);
      } catch {
        // Ignore close failures.
      }
    }
    if (chromeProcess && typeof chromeProcess.kill === "function") {
      chromeProcess.kill("SIGTERM");
    }
  }
}

await main();
