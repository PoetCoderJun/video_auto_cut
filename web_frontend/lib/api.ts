import {coerceWebRenderConfig} from "./remotion/subtitle-render-v1.ts";

export type JobStatus =
  | "CREATED"
  | "UPLOAD_READY"
  | "TEST_RUNNING"
  | "TEST_READY"
  | "TEST_CONFIRMED"
  | "SUCCEEDED"
  | "FAILED";

export type Job = {
  job_id: string;
  status: JobStatus;
  progress: number;
  stage: null | {code: string; message: string};
  error: null | {code: string; message: string};
};

export type TestLine = {
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
  start: number;
  end: number;
  block_range: string;
};

export type TestDocument = {
  lines: TestLine[];
  chapters: Chapter[];
  document_revision: string;
};

export type TestConfirmChapter = Pick<Chapter, "chapter_id" | "title" | "block_range">;

export type RenderCaptionToken = {
  text: string;
  start: number;
  end: number;
  sourceWordIndex?: number;
};

export type RenderCaptionEmphasisSpan = {
  startToken: number;
  endToken: number;
};

export type RenderCaptionLabel = {
  badgeText?: string;
  emphasisSpans?: RenderCaptionEmphasisSpan[];
};

export type RenderCaption = {
  index: number;
  start: number;
  end: number;
  text: string;
  tokens?: RenderCaptionToken[];
  label?: RenderCaptionLabel;
  alignmentMode?: "exact" | "fuzzy" | "degraded" | "missing";
};

export type RenderSegment = {
  start: number;
  end: number;
};

export type RenderTopic = {
  title: string;
  start: number;
  end: number;
};

export type SubtitleTheme =
  | "text-black"
  | "text-white"
  | "box-white-on-black"
  | "box-black-on-white";

export type ProgressLabelMode = "auto" | "single" | "double";

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
  subtitleScale?: number;
  subtitleYPercent?: number;
  progressScale?: number;
  progressYPercent?: number;
  chapterScale?: number;
  showSubtitles?: boolean;
  showProgress?: boolean;
  showChapter?: boolean;
  progressLabelMode?: ProgressLabelMode;
};

export type WebRenderConfig = {
  output_name: string;
  composition: RenderComposition;
  input_props: RenderInputProps;
};

export type TestRunAccepted = {
  accepted: boolean;
  job: Job;
};

export type ClientUploadIssueStage =
  | "session_check"
  | "profile_check"
  | "source_preflight"
  | "render_validation"
  | "job_create"
  | "audio_extract"
  | "audio_upload"
  | "source_cache";

export type ClientUploadIssueReport = {
  stage: ClientUploadIssueStage;
  page?: string;
  file_name?: string;
  file_type?: string;
  file_size_bytes?: number;
  error_name?: string;
  error_message?: string;
  friendly_message?: string;
  user_agent?: string;
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

type AudioDirectUploadTarget = {
  put_url: string;
  object_key: string;
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
  detail?: string;
};

type AuthTokenProvider = () => Promise<string | null>;
let authTokenProvider: AuthTokenProvider | null = null;
let authTokenInflight: Promise<string | null> | null = null;

// Module-level JWT cache so we don't hit /api/auth/token on every request.
let tokenCache: { token: string; expiresAt: number } | null = null;
const TOKEN_CACHE_TTL_MS = 4 * 60 * 1000; // 4 minutes
const AUTH_TOKEN_INIT_MAX_WAIT_MS = 1500;
const AUTH_TOKEN_INIT_RETRY_DELAY_MS = 250;

export function invalidateTokenCache(): void {
  tokenCache = null;
  authTokenInflight = null;
}

type RequestOptions = {
  authToken?: string;
  requireAuth?: boolean;
  keepalive?: boolean;
};

export type RenderCompletionPendingMarker = {
  job_id: string;
  createdAt: number;
  attempts: number;
  lastError?: string;
};

const base = (process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api/v1").replace(/\/$/, "");
const RENDER_COMPLETION_PENDING_STORAGE_KEY = "video_auto_cut_render_completion_pending";
const RENDER_COMPLETION_PENDING_TTL_MS = 7 * 24 * 60 * 60 * 1000;

export class ApiClientError extends Error {
  code: string;
  status: number;
  details: string | null;

  constructor(message: string, code = "UNKNOWN_ERROR", status = 0, details?: string | null) {
    super(message);
    this.name = "ApiClientError";
    this.code = String(code || "UNKNOWN_ERROR");
    this.status = Number.isFinite(status) ? intOrZero(status) : 0;
    this.details = String(details || "").trim() || null;
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
    const fallbackDetail = String(parsed?.detail || "").trim();
    const code = String(parsed?.error?.code || "HTTP_ERROR");
    const message =
      String(parsed?.error?.message || "").trim() || fallbackDetail || `HTTP ${fallbackStatus}`;
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
  authTokenInflight = null;
  if (!provider) {
    tokenCache = null;
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    globalThis.setTimeout(resolve, ms);
  });
}

async function requestFreshAuthToken(): Promise<string | null> {
  if (!authTokenProvider) return null;

  const deadline = Date.now() + AUTH_TOKEN_INIT_MAX_WAIT_MS;
  while (true) {
    try {
      const token = await authTokenProvider();
      if (token) {
        tokenCache = { token, expiresAt: Date.now() + TOKEN_CACHE_TTL_MS };
        return token;
      }
    } catch {
      // Treat provider failures as transient until the grace window expires.
    }

    const remainingMs = deadline - Date.now();
    if (remainingMs <= 0) {
      tokenCache = null;
      return null;
    }

    await sleep(Math.min(AUTH_TOKEN_INIT_RETRY_DELAY_MS, remainingMs));
  }
}

async function resolveAuthToken(): Promise<string | null> {
  if (tokenCache && Date.now() < tokenCache.expiresAt) {
    return tokenCache.token;
  }
  if (!authTokenProvider) return null;
  if (!authTokenInflight) {
    authTokenInflight = requestFreshAuthToken().finally(() => {
      authTokenInflight = null;
    });
  }
  return authTokenInflight;
}

async function request<T>(path: string, init?: RequestInit, options?: RequestOptions): Promise<T> {
  const headers = new Headers(init?.headers);
  const requireAuth = Boolean(options?.requireAuth);
  const hasExplicitAuthToken = Boolean(
    options && Object.prototype.hasOwnProperty.call(options, "authToken")
  );

  let token: string | null = null;
  // Explicit caller token always wins; only consult the provider when no explicit token was supplied.
  if (hasExplicitAuthToken) {
    const normalizedExplicitToken = String(options?.authToken || "").trim();
    if (normalizedExplicitToken) {
      token = normalizedExplicitToken;
    } else if (requireAuth) {
      throw new ApiClientError("登录状态初始化中，请稍后重试。", "UNAUTHORIZED", 401);
    }
  } else {
    token = await resolveAuthToken();
    if (requireAuth && !token) {
      throw new ApiClientError("登录状态初始化中，请稍后重试。", "UNAUTHORIZED", 401);
    }
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
      keepalive: options?.keepalive ?? false,
    });
  } catch (err) {
    throw new ApiClientError(`无法连接 API（${base}）：${toMessage(err)}`, "NETWORK_ERROR", 0);
  }

  await assertOk(response);

  const payload = (await response.json()) as ApiResponse<T>;
  return payload.data;
}

async function requestAuthed<T>(
  path: string,
  init?: RequestInit,
  options?: RequestOptions
): Promise<T> {
  return request<T>(path, init, {requireAuth: true, ...options});
}

function getRenderCompletionStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage ?? null;
  } catch {
    return null;
  }
}

function readRenderCompletionStore(
  storage: Storage
): Record<string, RenderCompletionPendingMarker> {
  try {
    const raw = storage.getItem(RENDER_COMPLETION_PENDING_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return parsed as Record<string, RenderCompletionPendingMarker>;
  } catch {
    return {};
  }
}

function pruneExpiredRenderCompletionMarkers(store: Record<string, RenderCompletionPendingMarker>): void {
  const now = Date.now();
  for (const [jobId, marker] of Object.entries(store)) {
    if (!marker || typeof marker.createdAt !== "number") {
      delete store[jobId];
      continue;
    }
    if (now - marker.createdAt > RENDER_COMPLETION_PENDING_TTL_MS) {
      delete store[jobId];
    }
  }
}

function saveRenderCompletionStore(
  storage: Storage,
  store: Record<string, RenderCompletionPendingMarker>
): void {
  try {
    if (!store || Object.keys(store).length === 0) {
      storage.removeItem(RENDER_COMPLETION_PENDING_STORAGE_KEY);
      return;
    }
    storage.setItem(RENDER_COMPLETION_PENDING_STORAGE_KEY, JSON.stringify(store));
  } catch {
    storage.removeItem(RENDER_COMPLETION_PENDING_STORAGE_KEY);
  }
}

function withRenderCompletionStore<T>(
  callback: (store: Record<string, RenderCompletionPendingMarker>) => T
): T | null {
  const storage = getRenderCompletionStorage();
  if (!storage) return null;
  const store = readRenderCompletionStore(storage);
  pruneExpiredRenderCompletionMarkers(store);
  const result = callback(store);
  saveRenderCompletionStore(storage, store);
  return result;
}

export function getRenderCompletionPending(jobId: string): RenderCompletionPendingMarker | null {
  if (!jobId) return null;
  return withRenderCompletionStore((store) => store[jobId] ?? null) ?? null;
}

export function setRenderCompletionPending(
  jobId: string,
  lastError?: string
): RenderCompletionPendingMarker | null {
  if (!jobId) return null;
  return withRenderCompletionStore((store) => {
    const existing = store[jobId];
    const marker: RenderCompletionPendingMarker = {
      job_id: jobId,
      createdAt: existing?.createdAt || Date.now(),
      attempts: typeof existing?.attempts === "number" ? existing.attempts + 1 : 1,
      lastError: lastError || existing?.lastError,
    };
    store[jobId] = marker;
    return marker;
  }) ?? null;
}

export function clearRenderCompletionPending(jobId: string): void {
  if (!jobId) return;
  withRenderCompletionStore((store) => {
    delete store[jobId];
    return null;
  });
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

export async function reportClientUploadIssue(
  payload: ClientUploadIssueReport
): Promise<void> {
  await requestAuthed<{accepted: boolean}>("/client/upload-issues", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  }, {
    keepalive: true,
  });
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
  const hasExplicitTokenArg = arguments.length >= 2;
  const data = await requestAuthed<{
    coupon: {already_activated: boolean; coupon_redeemed: boolean; granted_credits: number; balance: number};
    user: UserProfile;
  }>(
    "/auth/coupon/redeem",
    requestInit,
    hasExplicitTokenArg ? {authToken: explicitToken} : undefined
  );

  return data.coupon;
}

export async function claimPublicInviteCode(): Promise<{code: string; credits: number; already_claimed: boolean}> {
  const data = await request<{invite: {code: string; credits: number; already_claimed: boolean}}>(
    "/public/invites/claim",
    {
      method: "POST",
    }
  );
  return data.invite;
}

async function getAudioDirectUploadTarget(jobId: string): Promise<AudioDirectUploadTarget> {
  return requestAuthed<AudioDirectUploadTarget>(`/jobs/${jobId}/oss-upload-url`, {
    method: "POST",
  });
}

async function putAudioToOss(putUrl: string, file: File): Promise<void> {
  let response: Response;
  try {
    response = await fetch(putUrl, {
      method: "PUT",
      headers: {
        "Content-Type": file.type || "audio/mpeg",
      },
      body: file,
    });
  } catch (err) {
    throw new ApiClientError(
      "音频上传失败，请稍后重试。",
      "NETWORK_ERROR",
      0,
      `PUT network error: ${toMessage(err)}`
    );
  }

  if (!response.ok) {
    const responseText = (await response.text().catch(() => "")).trim();
    const detail = responseText
      ? `PUT ${response.status}: ${responseText.slice(0, 300)}`
      : `PUT ${response.status}`;
    throw new ApiClientError(
      "音频上传失败，请稍后重试。",
      "DIRECT_UPLOAD_FAILED",
      response.status,
      detail
    );
  }
}

async function markAudioOssReady(jobId: string, objectKey: string): Promise<Job> {
  const data = await requestAuthed<{job: Job}>(`/jobs/${jobId}/audio-oss-ready`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({object_key: objectKey}),
  });
  return data.job;
}

export async function uploadAudio(jobId: string, file: File): Promise<Job> {
  const target = await getAudioDirectUploadTarget(jobId);
  await putAudioToOss(target.put_url, file);
  return markAudioOssReady(jobId, target.object_key);
}

export async function runTest(jobId: string): Promise<TestRunAccepted> {
  return requestAuthed<TestRunAccepted>(`/jobs/${jobId}/test/run`, {method: "POST"});
}

export async function getTest(jobId: string): Promise<TestDocument> {
  return requestAuthed<TestDocument>(`/jobs/${jobId}/test`);
}

export async function confirmTest(
  jobId: string,
  payload: {
    lines: TestLine[];
    chapters: TestConfirmChapter[];
    expectedRevision: string;
  }
): Promise<JobStatus> {
  const data = await requestAuthed<{confirmed: boolean; status: JobStatus}>(`/jobs/${jobId}/test/confirm`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      lines: payload.lines.map((line) => ({
        line_id: line.line_id,
        optimized_text: line.optimized_text,
        user_final_remove: line.user_final_remove,
      })),
      chapters: payload.chapters.map((chapter) => ({
        chapter_id: chapter.chapter_id,
        title: chapter.title,
        block_range: chapter.block_range,
      })),
      expected_revision: payload.expectedRevision,
    }),
  });
  return data.status;
}

export type RenderMeta = {
  width: number;
  height: number;
  fps: number;
  duration_sec?: number;
  source_overall_bitrate?: number;
  source_video_bitrate?: number;
  source_audio_bitrate?: number;
  source_video_codec?: string;
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
  return coerceWebRenderConfig(data.render);
}

export async function markRenderSucceeded(
  jobId: string,
  options?: { keepalive?: boolean }
): Promise<{job: Job; billing: {consumed: boolean; balance: number}}> {
  return requestAuthed<{job: Job; billing: {consumed: boolean; balance: number}}>(
    `/jobs/${jobId}/render/complete`,
    {method: "POST"},
    {keepalive: options?.keepalive}
  );
}
