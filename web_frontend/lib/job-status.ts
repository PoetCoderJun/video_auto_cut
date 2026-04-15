type JobStatus =
  | "CREATED"
  | "UPLOAD_READY"
  | "STEP1_RUNNING"
  | "STEP1_READY"
  | "STEP1_CONFIRMED"
  | "SUCCEEDED"
  | "FAILED";

type JobSnapshot = {
  job_id: string;
  status: JobStatus;
  progress: number;
  stage: null | { code: string; message: string };
  error: null | { code: string; message: string };
};

const STATUS_ORDER: JobStatus[] = [
  "CREATED",
  "UPLOAD_READY",
  "STEP1_RUNNING",
  "STEP1_READY",
  "STEP1_CONFIRMED",
  "SUCCEEDED",
  "FAILED",
];

const STATUS_PROGRESS_FLOOR: Record<JobStatus, number> = {
  CREATED: 0,
  UPLOAD_READY: 10,
  STEP1_RUNNING: 30,
  STEP1_READY: 60,
  STEP1_CONFIRMED: 80,
  SUCCEEDED: 100,
  FAILED: 0,
};

function getStatusRank(status: JobStatus): number {
  const rank = STATUS_ORDER.indexOf(status);
  return rank >= 0 ? rank : -1;
}

function getProgressFloor(status: JobStatus): number {
  return STATUS_PROGRESS_FLOOR[status] ?? 0;
}

export function shouldPollJobStatus(status: JobStatus): boolean {
  return (
    status === "UPLOAD_READY" ||
    status === "STEP1_RUNNING"
  );
}

export function mergeJobSnapshot(
  localJob: JobSnapshot | null,
  incomingJob: JobSnapshot,
): JobSnapshot {
  if (!localJob || localJob.job_id !== incomingJob.job_id) {
    return {
      ...incomingJob,
      progress: Math.max(
        incomingJob.progress,
        getProgressFloor(incomingJob.status),
      ),
    };
  }

  const localRank = getStatusRank(localJob.status);
  const incomingRank = getStatusRank(incomingJob.status);

  if (incomingRank < localRank) {
    return {
      ...incomingJob,
      status: localJob.status,
      progress: Math.max(
        localJob.progress,
        incomingJob.progress,
        getProgressFloor(localJob.status),
      ),
      stage: localJob.stage ?? incomingJob.stage,
      error: incomingJob.error ?? localJob.error,
    };
  }

  return {
    ...incomingJob,
    progress: Math.max(
      localJob.progress,
      incomingJob.progress,
      getProgressFloor(incomingJob.status),
    ),
  };
}

export function mergeJobStatus(
  localJob: JobSnapshot | null,
  nextStatus: JobStatus,
): JobSnapshot | null {
  if (!localJob) return localJob;

  const localRank = getStatusRank(localJob.status);
  const nextRank = getStatusRank(nextStatus);
  if (nextRank < localRank) {
    return localJob;
  }

  return {
    ...localJob,
    status: nextStatus,
    progress: Math.max(localJob.progress, getProgressFloor(nextStatus)),
    stage: null,
  };
}
