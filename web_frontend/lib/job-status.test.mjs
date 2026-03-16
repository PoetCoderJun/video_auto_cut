import test from "node:test";
import assert from "node:assert/strict";

import {
  mergeJobSnapshot,
  mergeJobStatus,
  shouldPollJobStatus,
} from "./job-status.ts";

test("mergeJobSnapshot keeps newer local status when a stale refresh arrives", () => {
  const localJob = {
    job_id: "job-123",
    status: "STEP2_CONFIRMED",
    progress: 80,
    stage: null,
    error: null,
  };
  const staleRefresh = {
    job_id: "job-123",
    status: "STEP2_READY",
    progress: 75,
    stage: { code: "PREPARING_EXPORT", message: "正在准备导出..." },
    error: null,
  };

  const merged = mergeJobSnapshot(localJob, staleRefresh);

  assert.equal(merged.status, "STEP2_CONFIRMED");
  assert.equal(merged.progress, 80);
});

test("mergeJobStatus advances a job without allowing regression", () => {
  const localJob = {
    job_id: "job-123",
    status: "STEP2_READY",
    progress: 75,
    stage: { code: "PREPARING_EXPORT", message: "正在准备导出..." },
    error: null,
  };

  const confirmed = mergeJobStatus(localJob, "STEP2_CONFIRMED");
  const regressed = mergeJobStatus(confirmed, "STEP2_READY");

  assert.ok(confirmed);
  assert.equal(confirmed?.status, "STEP2_CONFIRMED");
  assert.equal(confirmed?.progress, 80);
  assert.equal(confirmed?.stage, null);
  assert.equal(regressed?.status, "STEP2_CONFIRMED");
  assert.equal(regressed?.progress, 80);
});

test("shouldPollJobStatus keeps polling while step2 is waiting to enter export", () => {
  assert.equal(shouldPollJobStatus("STEP2_READY"), true);
  assert.equal(shouldPollJobStatus("STEP2_CONFIRMED"), false);
});
