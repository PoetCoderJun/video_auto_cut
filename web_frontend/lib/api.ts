export type JobStatus =
  | "CREATED"
  | "UPLOAD_READY"
  | "STEP1_RUNNING"
  | "STEP1_READY"
  | "STEP1_CONFIRMED"
  | "STEP2_RUNNING"
  | "STEP2_READY"
  | "STEP2_CONFIRMED"
  | "RENDER_RUNNING"
  | "SUCCEEDED"
  | "FAILED";

export type Job = {
  job_id: string;
  status: JobStatus;
  progress: number;
  error: null | {code: string; message: string};
};

export type Step1Line = {
  line_id: number;
  start: number;
  end: number;
  original_text: string;
  optimized_text: string;
  ai_suggest_remove: boolean;
  user_final_remove: boolean;
};

export type Chapter = {
  chapter_id: number;
  title: string;
  summary: string;
  start: number;
  end: number;
  line_ids: number[];
};

type ApiResponse<T> = {
  request_id: string;
  data: T;
};

type ApiErrorResponse = {
  request_id: string;
  error: {
    code: string;
    message: string;
  };
};

const base = (process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      ...init,
      headers: {
        ...(init?.headers || {}),
      },
      cache: "no-store",
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new Error(`无法连接 API（${base}）：${message}`);
  }

  if (!response.ok) {
    const text = await response.text();
    try {
      const parsed = JSON.parse(text) as ApiErrorResponse;
      throw new Error(parsed.error.message || `HTTP ${response.status}`);
    } catch {
      throw new Error(text || `HTTP ${response.status}`);
    }
  }

  const payload = (await response.json()) as ApiResponse<T>;
  return payload.data;
}

export async function createJob(): Promise<Job> {
  const data = await request<{job: Job}>("/jobs", {method: "POST"});
  return data.job;
}

export async function getJob(jobId: string): Promise<Job> {
  const data = await request<{job: Job}>(`/jobs/${jobId}`);
  return data.job;
}

export async function uploadVideo(jobId: string, file: File): Promise<Job> {
  const form = new FormData();
  form.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${base}/jobs/${jobId}/upload`, {
      method: "POST",
      body: form,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    throw new Error(`无法连接 API（${base}）：${message}`);
  }

  if (!response.ok) {
    const text = await response.text();
    try {
      const parsed = JSON.parse(text) as ApiErrorResponse;
      throw new Error(parsed.error.message || `HTTP ${response.status}`);
    } catch {
      throw new Error(text || `HTTP ${response.status}`);
    }
  }

  const payload = (await response.json()) as ApiResponse<{job: Job}>;
  return payload.data.job;
}

export async function runStep1(jobId: string): Promise<void> {
  await request<{accepted: boolean}>(`/jobs/${jobId}/step1/run`, {method: "POST"});
}

export async function getStep1(jobId: string): Promise<Step1Line[]> {
  const data = await request<{lines: Step1Line[]}>(`/jobs/${jobId}/step1`);
  return data.lines;
}

export async function confirmStep1(jobId: string, lines: Step1Line[]): Promise<void> {
  await request<{confirmed: boolean}>(`/jobs/${jobId}/step1/confirm`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      lines: lines.map((line) => ({
        line_id: line.line_id,
        optimized_text: line.optimized_text,
        user_final_remove: line.user_final_remove,
      })),
    }),
  });
}

export async function runStep2(jobId: string): Promise<void> {
  await request<{accepted: boolean}>(`/jobs/${jobId}/step2/run`, {method: "POST"});
}

export async function getStep2(jobId: string): Promise<Chapter[]> {
  const data = await request<{chapters: Chapter[]}>(`/jobs/${jobId}/step2`);
  return data.chapters;
}

export async function confirmStep2(jobId: string, chapters: Chapter[]): Promise<void> {
  await request<{confirmed: boolean}>(`/jobs/${jobId}/step2/confirm`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({chapters}),
  });
}

export async function runRender(jobId: string): Promise<void> {
  await request<{accepted: boolean}>(`/jobs/${jobId}/render/run`, {method: "POST"});
}

export function getDownloadUrl(jobId: string): string {
  return `${base}/jobs/${jobId}/download`;
}
