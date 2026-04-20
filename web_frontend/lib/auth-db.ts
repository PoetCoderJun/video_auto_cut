import {createClient, type Client, type Config} from "@libsql/client";
import path from "node:path";
import fs from "node:fs";

const DEFAULT_SYNC_INTERVAL_MS = 2_000;
const TURSO_CONNECT_ONLY_SIGNALS = [
  "error trying to connect",
  "tls handshake eof",
  "temporarily unavailable",
  "timed out",
  "timeout",
];

function trimEnv(value: string | undefined): string {
  return String(value || "").trim();
}

function normalizeReplicaUrl(replicaPath: string): string {
  const resolvedPath = path.resolve(replicaPath);
  return `file:${resolvedPath}`;
}

function defaultBetterAuthReplicaPath(replicaPath: string): string {
  const resolvedPath = path.resolve(replicaPath);
  const parsed = path.parse(resolvedPath);
  return path.join(parsed.dir, `${parsed.name}.auth${parsed.ext || ".db"}`);
}

export function buildBetterAuthLibsqlConfig(
  env: Record<string, string | undefined> = process.env,
): Config {
  const tursoUrl = trimEnv(env.TURSO_DATABASE_URL);
  const tursoAuthToken = trimEnv(env.TURSO_AUTH_TOKEN);
  const sharedReplicaPath = trimEnv(env.TURSO_LOCAL_REPLICA_PATH);
  const replicaPath =
    trimEnv(env.BETTER_AUTH_TURSO_LOCAL_REPLICA_PATH) ||
    (sharedReplicaPath ? defaultBetterAuthReplicaPath(sharedReplicaPath) : "");
  const betterAuthLocalOnly = ["1", "true", "yes"].includes(
    trimEnv(env.BETTER_AUTH_LOCAL_ONLY).toLowerCase(),
  );
  const syncIntervalSeconds = Number.parseFloat(trimEnv(env.TURSO_SYNC_INTERVAL) || "2");
  const syncIntervalMs = Number.isFinite(syncIntervalSeconds) && syncIntervalSeconds > 0
    ? Math.max(500, Math.round(syncIntervalSeconds * 1000))
    : DEFAULT_SYNC_INTERVAL_MS;

  if (!tursoUrl) {
    throw new Error("TURSO_DATABASE_URL is required for Better Auth");
  }
  if (!tursoAuthToken) {
    throw new Error("TURSO_AUTH_TOKEN is required for Better Auth");
  }
  if (!tursoUrl.startsWith("libsql://")) {
    throw new Error("TURSO_DATABASE_URL must use libsql:// to connect Turso");
  }

  if (!replicaPath) {
    return {
      url: tursoUrl,
      authToken: tursoAuthToken,
    };
  }

  const resolvedReplicaPath = path.resolve(replicaPath);
  fs.mkdirSync(path.dirname(resolvedReplicaPath), {recursive: true});
  if (betterAuthLocalOnly) {
    return {
      url: normalizeReplicaUrl(resolvedReplicaPath),
    };
  }
  return {
    url: normalizeReplicaUrl(resolvedReplicaPath),
    syncUrl: tursoUrl,
    authToken: tursoAuthToken,
    syncInterval: syncIntervalMs,
  };
}

function buildLocalReplicaOnlyConfig(config: Config): Config {
  return {
    url: String(config.url || ""),
  };
}

function isRetryableTursoConnectError(error: unknown): boolean {
  const message = String(error || "").trim().toLowerCase();
  if (!message) return false;
  return TURSO_CONNECT_ONLY_SIGNALS.some((signal) => message.includes(signal));
}

export function createBetterAuthLibsqlClient(
  config: Config,
  createClientImpl: (config: Config) => Client = createClient,
): Client {
  try {
    return createClientImpl(config);
  } catch (error) {
    const isReplicaConfig = String(config.url || "").startsWith("file:");
    if (!isReplicaConfig || !isRetryableTursoConnectError(error)) {
      throw error;
    }
    return createClientImpl(buildLocalReplicaOnlyConfig(config));
  }
}

declare global {
  // eslint-disable-next-line no-var
  var __videoAutoCutBetterAuthClient: Client | undefined;
}

export function getBetterAuthLibsqlClient(
  env: Record<string, string | undefined> = process.env,
): Client {
  if (!globalThis.__videoAutoCutBetterAuthClient) {
    const config = buildBetterAuthLibsqlConfig(env);
    globalThis.__videoAutoCutBetterAuthClient = createBetterAuthLibsqlClient(config);
  }
  return globalThis.__videoAutoCutBetterAuthClient;
}
