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

export type RenderCaption = {
  index: number;
  start: number;
  end: number;
  text: string;
};

export type RenderSegment = {
  start: number;
  end: number;
};

export type RenderTopic = {
  title: string;
  summary: string;
  start: number;
  end: number;
};

export type SubtitleTheme =
  | "text-black"
  | "text-white"
  | "box-white-on-black"
  | "box-black-on-white";

export type RenderComposition = {
  id: string;
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
};

export type RenderInputProps = {
  src: string;
  captions: RenderCaption[];
  segments: RenderSegment[];
  topics: RenderTopic[];
  fps: number;
  width: number;
  height: number;
  subtitleTheme?: SubtitleTheme;
};

export type WebRenderConfig = {
  source_url: string;
  output_name: string;
  composition: RenderComposition;
  input_props: RenderInputProps;
};

export type UserProfile = {
  user_id: string;
  email: string | null;
  status: string;
  invite_activated_at: string | null;
  credits: {
    balance: number;
    recent_ledger: Array<{
      entry_id: number;
      delta: number;
      reason: string;
      job_id: string | null;
      idempotency_key: string;
      created_at: string;
    }>;
  };
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

type AuthTokenProvider = () => Promise<string | null>;
let authTokenProvider: AuthTokenProvider | null = null;

const base = (process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");

export function setApiAuthTokenProvider(provider: AuthTokenProvider | null): void {
  authTokenProvider = provider;
}

async function resolveAuthToken(): Promise<string | null> {
  if (!authTokenProvider) return null;
  try {
    return await authTokenProvider();
  } catch {
    return null;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = await resolveAuthToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      ...init,
      headers,
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

export async function getMe(): Promise<UserProfile> {
  const data = await request<{user: UserProfile}>("/me");
  return data.user;
}

export async function activateInviteCode(
  code: string,
): Promise<{already_activated: boolean; coupon_redeemed: boolean; granted_credits: number; balance: number}> {
  const data = await request<{
    coupon: {already_activated: boolean; coupon_redeemed: boolean; granted_credits: number; balance: number};
    user: UserProfile;
  }>("/auth/coupon/redeem", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({code}),
  });
  return data.coupon;
}

export async function uploadVideo(jobId: string, file: File): Promise<Job> {
  const form = new FormData();
  form.append("file", file);
  const token = await resolveAuthToken();
  const headers = new Headers();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${base}/jobs/${jobId}/upload`, {
      method: "POST",
      body: form,
      headers,
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

export async function getWebRenderConfig(jobId: string): Promise<WebRenderConfig> {
  const data = await request<{render: WebRenderConfig}>(`/jobs/${jobId}/render/config`);
  return data.render;
}

export async function getRenderSourceBlob(jobId: string): Promise<Blob> {
  const headers = new Headers();
  const token = await resolveAuthToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${base}/jobs/${jobId}/render/source`, {
      method: "GET",
      headers,
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

  return response.blob();
}

function parseFilenameFromDisposition(disposition: string | null): string | null {
  if (!disposition) return null;
  const match = disposition.match(/filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)\"?/i);
  const encoded = match?.[1];
  if (encoded) {
    try {
      return decodeURIComponent(encoded);
    } catch {
      return encoded;
    }
  }
  const plain = match?.[2];
  return plain || null;
}

export async function downloadRenderedVideo(jobId: string): Promise<{blob: Blob; filename: string}> {
  const headers = new Headers();
  const token = await resolveAuthToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${base}/jobs/${jobId}/download`, {
      method: "GET",
      headers,
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

  const blob = await response.blob();
  const filename = parseFilenameFromDisposition(response.headers.get("content-disposition")) || "output.mp4";
  return {blob, filename};
}
