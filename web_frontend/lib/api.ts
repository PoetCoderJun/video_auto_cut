import {coerceWebRenderConfig} from "./remotion/subtitle-render-v1.ts";
import {buildGuestDeviceFingerprint} from "./device.ts";
import {GUEST_SESSION_STORAGE_KEY} from "./session.ts";

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
  chapter_key: string;
  chapter_id: number;
  title: string;
  start_line_id: number;
  end_line_id: number;
  active_start_line_id: number | null;
  active_end_line_id: number | null;
  active_line_count: number;
  start: number | null;
  end: number | null;
  block_range?: string;
};

export type TestDocument = {
  lines: TestLine[];
  chapters: Chapter[];
  document_revision: string;
};

export type TestConfirmChapter = Pick<
  Chapter,
  "chapter_key" | "chapter_id" | "title" | "start_line_id"
>;

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

export type RenderCaptionHighlight = {
  text?: string;
  startToken?: number;
  endToken?: number;
  color?: string;
  fontScale?: number;
  backgroundColor?: string;
};

export type RenderCaptionLabel = {
  badgeText?: string;
  emphasisSpans?: RenderCaptionEmphasisSpan[];
  highlights?: RenderCaptionHighlight[];
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

export type SubtitleTheme = "stroke" | "stroke-white";

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
  overlayReferenceWidth?: number;
  overlayReferenceHeight?: number;
  subtitleTheme?: SubtitleTheme;
  subtitleScale?: number;
  subtitleYPercent?: number;
  progressScale?: number;
  progressYPercent?: number;
  chapterScale?: number;
  showSubtitles?: boolean;
  showHighlights?: boolean;
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
  | "source_upload"
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
let guestTokenCache: string | null | undefined;

// Module-level JWT cache so we don't hit /api/auth/token on every request.
let tokenCache: { token: string; expiresAt: number } | null = null;
const TOKEN_CACHE_TTL_MS = 4 * 60 * 1000; // 4 minutes
const AUTH_TOKEN_INIT_MAX_WAIT_MS = 1500;
const AUTH_TOKEN_INIT_RETRY_DELAY_MS = 250;

export function invalidateTokenCache(): void {
  tokenCache = null;
  authTokenInflight = null;
}

function readStoredGuestToken(): string | null {
  if (guestTokenCache !== undefined) {
    return guestTokenCache;
  }
  if (typeof window === "undefined") {
    guestTokenCache = null;
    return guestTokenCache;
  }
  try {
    const raw = window.localStorage.getItem(GUEST_SESSION_STORAGE_KEY);
    if (!raw) {
      guestTokenCache = null;
      return guestTokenCache;
    }
    const parsed = JSON.parse(raw) as Partial<GuestSessionPayload>;
    const token = String(parsed?.token || "").trim();
    guestTokenCache = token || null;
    return guestTokenCache;
  } catch {
    guestTokenCache = null;
    return guestTokenCache;
  }
}

function writeStoredGuestSession(payload: GuestSessionPayload | null): void {
  guestTokenCache = payload?.token ? String(payload.token).trim() : null;
  if (typeof window === "undefined") return;
  try {
    if (!payload || !guestTokenCache) {
      window.localStorage.removeItem(GUEST_SESSION_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(
      GUEST_SESSION_STORAGE_KEY,
      JSON.stringify({
        guest_id: payload.guest_id,
        token: guestTokenCache,
        free_uses_remaining: payload.free_uses_remaining,
        job_id: payload.job_id,
        reused_existing: payload.reused_existing,
      }),
    );
  } catch {
    // Ignore storage failures.
  }
}

export function clearGuestSessionToken(): void {
  writeStoredGuestSession(null);
}

type RequestOptions = {
  authToken?: string;
  requireAuth?: boolean;
  keepalive?: boolean;
};

type GuestSessionPayload = {
  guest_id: string;
  token: string;
  free_uses_remaining: number;
  job_id: string | null;
  reused_existing: boolean;
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
  let guestToken: string | null = null;
  // Explicit caller token always wins; only consult the provider when no explicit token was supplied.
  if (hasExplicitAuthToken) {
    const normalizedExplicitToken = String(options?.authToken || "").trim();
    if (normalizedExplicitToken) {
      token = normalizedExplicitToken;
    } else if (requireAuth) {
      throw new ApiClientError("请先登录账号后继续使用。", "UNAUTHORIZED", 401);
    }
  } else {
    token = await resolveAuthToken();
    if (requireAuth && !token) {
      throw new ApiClientError("请先登录账号后继续使用。", "UNAUTHORIZED", 401);
    }
    if (!requireAuth && !token) {
      guestToken = readStoredGuestToken();
    }
  }

  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  } else if (guestToken) {
    headers.set("X-Guest-Token", guestToken);
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

export async function transcodeSourceVideoToBrowserCompatibleMp4(
  file: File
): Promise<File> {
  const token = await resolveAuthToken();
  if (!token) {
    throw new ApiClientError("请先登录账号后继续使用。", "UNAUTHORIZED", 401);
  }

  const formData = new FormData();
  formData.append("source_file", file, file.name);

  let response: Response;
  try {
    response = await fetch(`${base}/source/browser-compatible`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
      },
      body: formData,
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiClientError(
      `无法连接 API（${base}）：${toMessage(err)}`,
      "NETWORK_ERROR",
      0
    );
  }

  await assertOk(response);

  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") || "";
  const fileNameMatch =
    disposition.match(/filename\\*=UTF-8''([^;]+)/i) ??
    disposition.match(/filename=\"?([^\";]+)\"?/i);
  const outputName = fileNameMatch
    ? decodeURIComponent(String(fileNameMatch[1] || "").trim())
    : `${file.name.replace(/\\.[^.]+$/, "") || "source"}_browser_compatible.mp4`;

  return new File([blob], outputName, {
    type: "video/mp4",
    lastModified: Date.now(),
  });
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

export async function createJob(script?: string): Promise<Job> {
  const body = JSON.stringify({script: script?.trim() || ""});
  const data = await requestAuthed<{job: Job}>("/jobs", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body,
  });
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

export async function redeemCouponCode(
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

export async function claimGuestSession(
  deviceFingerprint = buildGuestDeviceFingerprint()
): Promise<GuestSessionPayload> {
  const data = await request<{guest: GuestSessionPayload}>(
    "/public/guest/session",
    {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        device_fingerprint: deviceFingerprint,
      }),
    }
  );
  writeStoredGuestSession(data.guest);
  return data.guest;
}

export async function ensureGuestSessionForUpload(
  deviceFingerprint = buildGuestDeviceFingerprint()
): Promise<GuestSessionPayload | null> {
  const token = readStoredGuestToken();
  if (token) {
    return {
      guest_id: "",
      token,
      free_uses_remaining: 0,
      job_id: null,
      reused_existing: true,
    };
  }
  return claimGuestSession(deviceFingerprint);
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

async function uploadAudioDirectToLocalApi(jobId: string, file: File): Promise<Job> {
  const formData = new FormData();
  formData.append("audio_file", file, file.name || "audio.mp3");
  const data = await requestAuthed<{job: Job}>(`/jobs/${jobId}/audio-upload-local`, {
    method: "POST",
    body: formData,
  });
  return data.job;
}

function shouldFallbackAudioUploadTargetError(error: unknown): boolean {
  return error instanceof ApiClientError && error.code === "SERVICE_UNAVAILABLE";
}

function shouldFallbackDirectAudioUploadError(error: unknown): boolean {
  return (
    error instanceof ApiClientError &&
    (error.code === "DIRECT_UPLOAD_FAILED" || error.code === "NETWORK_ERROR")
  );
}

export async function uploadAudio(jobId: string, file: File): Promise<Job> {
  let target: AudioDirectUploadTarget;
  try {
    target = await getAudioDirectUploadTarget(jobId);
  } catch (error) {
    if (shouldFallbackAudioUploadTargetError(error)) {
      return await uploadAudioDirectToLocalApi(jobId, file);
    }
    throw error;
  }

  try {
    await putAudioToOss(target.put_url, file);
  } catch (error) {
    if (shouldFallbackDirectAudioUploadError(error)) {
      return await uploadAudioDirectToLocalApi(jobId, file);
    }
    throw error;
  }

  return await markAudioOssReady(jobId, target.object_key);
}

export async function uploadSourceVideo(jobId: string, file: File): Promise<Job> {
  const formData = new FormData();
  formData.append("source_file", file, file.name || "source.mp4");
  const data = await requestAuthed<{job: Job}>(`/jobs/${jobId}/source-upload-local`, {
    method: "POST",
    body: formData,
  });
  return data.job;
}

export async function saveSourceVideoMetadata(
  jobId: string,
  meta: RenderMeta,
  file: File
): Promise<Job> {
  const data = await requestAuthed<{job: Job}>(`/jobs/${jobId}/source-metadata`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({
      width: meta.width,
      height: meta.height,
      fps: meta.fps,
      duration_sec: meta.duration_sec,
      file_name: file.name || "source.mp4",
      file_type: file.type || "",
      file_size_bytes: file.size,
    }),
  });
  return data.job;
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
        chapter_key: chapter.chapter_key,
        title: chapter.title,
        start_line_id: chapter.start_line_id,
      })),
      expected_revision: payload.expectedRevision,
    }),
  });
  return data.status;
}

export async function reopenTestForEditing(jobId: string): Promise<Job> {
  const data = await requestAuthed<{reopened: boolean; job: Job}>(
    `/jobs/${jobId}/test/reopen`,
    {method: "POST"},
  );
  return data.job;
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

export async function getWebRenderConfig(jobId: string): Promise<WebRenderConfig> {
  const data = await requestAuthed<{render: WebRenderConfig}>(`/jobs/${jobId}/render/config`);
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
