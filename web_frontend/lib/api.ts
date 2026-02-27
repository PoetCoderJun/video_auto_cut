export type JobStatus =
  | "CREATED"
  | "UPLOAD_READY"
  | "STEP1_RUNNING"
  | "STEP1_READY"
  | "STEP1_CONFIRMED"
  | "STEP2_RUNNING"
  | "STEP2_READY"
  | "STEP2_CONFIRMED"
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
  output_name: string;
  composition: RenderComposition;
  input_props: RenderInputProps;
};

export type QueueAccepted = {
  accepted: boolean;
  task_id: number;
  job: Job;
};

export type UserProfile = {
  user_id: string;
  email: string | null;
  status: string;
  activated_at: string | null;
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

// Module-level JWT cache so we don't hit /api/auth/token on every request.
let tokenCache: { token: string; expiresAt: number } | null = null;
const TOKEN_CACHE_TTL_MS = 4 * 60 * 1000; // 4 minutes

export function invalidateTokenCache(): void {
  tokenCache = null;
}

type RequestOptions = {
  requireAuth?: boolean;
};

const base = (process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");

export class ApiClientError extends Error {
  code: string;
  status: number;

  constructor(message: string, code = "UNKNOWN_ERROR", status = 0) {
    super(message);
    this.name = "ApiClientError";
    this.code = String(code || "UNKNOWN_ERROR");
    this.status = Number.isFinite(status) ? intOrZero(status) : 0;
  }
}

function intOrZero(value: number): number {
  const normalized = Math.trunc(value);
  return Number.isFinite(normalized) ? normalized : 0;
}

function toMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  return String(err);
}

function parseApiErrorText(text: string, fallbackStatus: number): ApiClientError {
  const trimmed = String(text || "").trim();
  if (!trimmed) {
    return new ApiClientError(`HTTP ${fallbackStatus}`, "HTTP_ERROR", fallbackStatus);
  }
  try {
    const parsed = JSON.parse(trimmed) as ApiErrorResponse;
    const code = String(parsed?.error?.code || "HTTP_ERROR");
    const message = String(parsed?.error?.message || "").trim() || `HTTP ${fallbackStatus}`;
    return new ApiClientError(message, code, fallbackStatus);
  } catch {
    return new ApiClientError(trimmed, "HTTP_ERROR", fallbackStatus);
  }
}

async function assertOk(response: Response): Promise<void> {
  if (response.ok) return;
  const text = await response.text();
  throw parseApiErrorText(text, response.status);
}

export function setApiAuthTokenProvider(provider: AuthTokenProvider | null): void {
  authTokenProvider = provider;
}

async function resolveAuthToken(): Promise<string | null> {
  if (tokenCache && Date.now() < tokenCache.expiresAt) {
    return tokenCache.token;
  }
  if (!authTokenProvider) return null;
  try {
    const token = await authTokenProvider();
    if (token) {
      tokenCache = { token, expiresAt: Date.now() + TOKEN_CACHE_TTL_MS };
      return token;
    }
    tokenCache = null;
    return null;
  } catch {
    tokenCache = null;
    return null;
  }
}

async function request<T>(path: string, init?: RequestInit, options?: RequestOptions): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = await resolveAuthToken();
  const requireAuth = Boolean(options?.requireAuth);
  if (requireAuth && !token) {
    throw new ApiClientError("登录状态初始化中，请稍后重试。", "UNAUTHORIZED", 401);
  }
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
    throw new ApiClientError(`无法连接 API（${base}）：${toMessage(err)}`, "NETWORK_ERROR", 0);
  }

  await assertOk(response);

  const payload = (await response.json()) as ApiResponse<T>;
  return payload.data;
}

async function requestAuthed<T>(path: string, init?: RequestInit): Promise<T> {
  return request<T>(path, init, {requireAuth: true});
}

async function requestWithExplicitToken<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const normalizedToken = token.trim();
  if (!normalizedToken) {
    throw new ApiClientError("登录状态初始化中，请稍后重试。", "UNAUTHORIZED", 401);
  }
  headers.set("Authorization", `Bearer ${normalizedToken}`);

  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiClientError(`无法连接 API（${base}）：${toMessage(err)}`, "NETWORK_ERROR", 0);
  }

  await assertOk(response);

  const payload = (await response.json()) as ApiResponse<T>;
  return payload.data;
}

export async function createJob(): Promise<Job> {
  const data = await requestAuthed<{job: Job}>("/jobs", {method: "POST"});
  return data.job;
}

export async function getJob(jobId: string): Promise<Job> {
  const data = await requestAuthed<{job: Job}>(`/jobs/${jobId}`);
  return data.job;
}

export async function getMe(): Promise<UserProfile> {
  const data = await requestAuthed<{user: UserProfile}>("/me");
  return data.user;
}

export async function activateInviteCode(
  code: string,
  explicitToken?: string,
): Promise<{already_activated: boolean; coupon_redeemed: boolean; granted_credits: number; balance: number}> {
  const requestInit: RequestInit = {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({code}),
  };
  let data:
    | {
        coupon: {already_activated: boolean; coupon_redeemed: boolean; granted_credits: number; balance: number};
        user: UserProfile;
      }
    | undefined;

  if (explicitToken) {
    data = await requestWithExplicitToken<{
      coupon: {already_activated: boolean; coupon_redeemed: boolean; granted_credits: number; balance: number};
      user: UserProfile;
    }>("/auth/coupon/redeem", explicitToken, requestInit);
  } else {
    data = await requestAuthed<{
      coupon: {already_activated: boolean; coupon_redeemed: boolean; granted_credits: number; balance: number};
      user: UserProfile;
    }>("/auth/coupon/redeem", requestInit);
  }

  const resolved = data as {
    coupon: {already_activated: boolean; coupon_redeemed: boolean; granted_credits: number; balance: number};
    user: UserProfile;
  };
  return resolved.coupon;
}

export async function verifyCouponCode(code: string): Promise<{valid: boolean; code: string; credits: number}> {
  const data = await request<{coupon: {valid: boolean; code: string; credits: number}}>("/public/coupons/verify", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({code}),
  });
  return data.coupon;
}

export type OssUploadCreds =
  | {put_url: string; object_key: string; upload_mode?: "oss_presign"}
  | {
      upload_mode: "dashscope_temp";
      put_url: null;
      object_key: string;
      upload_host: string;
      policy: string;
      OSSAccessKeyId: string;
      signature: string;
      key: string;
      oss_url: string;
      x_oss_object_acl?: string;
      x_oss_forbid_overwrite?: string;
    };

export async function getOssUploadUrl(
  jobId: string,
  format: "mp3" | "wav" = "mp3"
): Promise<OssUploadCreds> {
  const params = new URLSearchParams({format});
  const data = await requestAuthed<OssUploadCreds>(
    `/jobs/${jobId}/oss-upload-url?${params.toString()}`,
    {method: "POST"}
  );
  return data;
}

export async function uploadAudioOssReady(
  jobId: string,
  objectKey: string
): Promise<Job> {
  const data = await requestAuthed<{job: Job}>(
    `/jobs/${jobId}/audio-oss-ready`,
    {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({object_key: objectKey}),
    }
  );
  return data.job;
}

/**
 * Upload audio via presigned OSS URL or DashScope temp OSS (direct browser -> OSS).
 * Bypasses Railway server, faster for users in China. Falls back to API upload if OSS fails.
 * - Own OSS: PUT to presigned URL (bucket must allow CORS)
 * - DashScope temp (USE_DASHSCOPE_TEMP_OSS_FRONTEND=1): POST form to 百炼 temp OSS (CORS may block)
 */
export async function uploadAudioDirectToOss(jobId: string, file: File): Promise<Job> {
  try {
    const format = file.name.toLowerCase().endsWith(".mp3") ? "mp3" : "wav";
    const creds = await getOssUploadUrl(jobId, format);

    if (creds.upload_mode === "dashscope_temp") {
      const form = new FormData();
      form.append("OSSAccessKeyId", creds.OSSAccessKeyId);
      form.append("Signature", creds.signature);
      form.append("policy", creds.policy);
      form.append("key", creds.key);
      form.append("success_action_status", "200");
      if (creds.x_oss_object_acl) form.append("x-oss-object-acl", creds.x_oss_object_acl);
      if (creds.x_oss_forbid_overwrite)
        form.append("x-oss-forbid-overwrite", creds.x_oss_forbid_overwrite);
      form.append("file", file, file.name);
      const postResp = await fetch(creds.upload_host, {
        method: "POST",
        body: form,
      });
      if (!postResp.ok) {
        const text = await postResp.text();
        throw new Error(`DashScope temp OSS upload failed: ${postResp.status} ${text.slice(0, 200)}`);
      }
      return uploadAudioOssReady(jobId, creds.oss_url);
    }

    const putResp = await fetch(creds.put_url!, {
      method: "PUT",
      body: file,
      headers: {"Content-Type": file.type || "audio/wav"},
    });
    if (!putResp.ok) {
      const text = await putResp.text();
      throw new Error(`OSS upload failed: ${putResp.status} ${text.slice(0, 100)}`);
    }
    return uploadAudioOssReady(jobId, creds.object_key);
  } catch {
    return uploadAudio(jobId, file);
  }
}

export async function uploadAudio(jobId: string, file: File): Promise<Job> {
  const form = new FormData();
  form.append("file", file);
  const data = await requestAuthed<{job: Job}>(`/jobs/${jobId}/audio`, {
    method: "POST",
    body: form,
  });
  return data.job;
}

export async function runStep1(jobId: string): Promise<QueueAccepted> {
  return requestAuthed<QueueAccepted>(`/jobs/${jobId}/step1/run`, {method: "POST"});
}

export async function getStep1(jobId: string): Promise<Step1Line[]> {
  const data = await requestAuthed<{lines: Step1Line[]}>(`/jobs/${jobId}/step1`);
  return data.lines;
}

export async function confirmStep1(jobId: string, lines: Step1Line[]): Promise<JobStatus> {
  const data = await requestAuthed<{confirmed: boolean; status: JobStatus}>(`/jobs/${jobId}/step1/confirm`, {
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
  return data.status;
}

export async function runStep2(jobId: string): Promise<QueueAccepted> {
  return requestAuthed<QueueAccepted>(`/jobs/${jobId}/step2/run`, {method: "POST"});
}

export async function getStep2(jobId: string): Promise<Chapter[]> {
  const data = await requestAuthed<{chapters: Chapter[]}>(`/jobs/${jobId}/step2`);
  return data.chapters;
}

export async function confirmStep2(jobId: string, chapters: Chapter[]): Promise<JobStatus> {
  const data = await requestAuthed<{confirmed: boolean; status: JobStatus}>(`/jobs/${jobId}/step2/confirm`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({chapters}),
  });
  return data.status;
}

export type RenderMeta = {
  width: number;
  height: number;
  fps: number;
  duration_sec?: number;
};

export async function getWebRenderConfigWithMeta(jobId: string, meta: RenderMeta): Promise<WebRenderConfig> {
  const params = new URLSearchParams({
    width: String(meta.width),
    height: String(meta.height),
    fps: String(meta.fps),
  });
  if (typeof meta.duration_sec === "number" && Number.isFinite(meta.duration_sec) && meta.duration_sec > 0) {
    params.set("duration_sec", String(meta.duration_sec));
  }
  const data = await requestAuthed<{render: WebRenderConfig}>(`/jobs/${jobId}/render/config?${params.toString()}`);
  return data.render;
}
