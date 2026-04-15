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
    status: "STEP1_CONFIRMED",
    progress: 80,
    stage: null,
    error: null,
  };
  const staleRefresh = {
    job_id: "job-123",
    status: "STEP1_READY",
    progress: 60,
    stage: { code: "GENERATING_CHAPTERS", message: "正在生成章节..." },
    error: null,
  };

  const merged = mergeJobSnapshot(localJob, staleRefresh);

  assert.equal(merged.status, "STEP1_CONFIRMED");
  assert.equal(merged.progress, 80);
});

test("mergeJobStatus advances a job without allowing regression", () => {
  const localJob = {
    job_id: "job-123",
    status: "STEP1_READY",
    progress: 60,
    stage: { code: "STEP1_READY", message: "已准备好编辑" },
    error: null,
  };

  const confirmed = mergeJobStatus(localJob, "STEP1_CONFIRMED");
  const regressed = mergeJobStatus(confirmed, "STEP1_READY");

  assert.ok(confirmed);
  assert.equal(confirmed?.status, "STEP1_CONFIRMED");
  assert.equal(confirmed?.progress, 80);
  assert.equal(confirmed?.stage, null);
  assert.equal(regressed?.status, "STEP1_CONFIRMED");
  assert.equal(regressed?.progress, 80);
});

test("shouldPollJobStatus only polls while upload or step1 processing is running", () => {
  assert.equal(shouldPollJobStatus("UPLOAD_READY"), true);
  assert.equal(shouldPollJobStatus("STEP1_RUNNING"), true);
  assert.equal(shouldPollJobStatus("STEP1_READY"), false);
  assert.equal(shouldPollJobStatus("STEP1_CONFIRMED"), false);
});
