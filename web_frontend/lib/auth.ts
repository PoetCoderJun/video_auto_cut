import {betterAuth} from "better-auth";
import {createAuthMiddleware, APIError} from "better-auth/api";
import {LibsqlDialect} from "@libsql/kysely-libsql";
import {jwt} from "better-auth/plugins";

const baseURL = process.env.BETTER_AUTH_URL || process.env.NEXT_PUBLIC_SITE_URL || "http://127.0.0.1:3000";
const apiBaseURL = (process.env.WEB_API_BASE || process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000/api/v1").replace(
  /\/$/,
  "",
);
const DEV_DEFAULT_SECRET = "video-auto-cut-dev-better-auth-secret-change-me";
const isProd = process.env.NODE_ENV === "production";
const configuredSecret = (process.env.BETTER_AUTH_SECRET || "").trim();
if (isProd && (!configuredSecret || configuredSecret === DEV_DEFAULT_SECRET)) {
  throw new Error("BETTER_AUTH_SECRET must be set to a strong non-default value in production");
}
if (isProd && configuredSecret.length < 32) {
  throw new Error("BETTER_AUTH_SECRET must be at least 32 characters in production");
}
const secret = configuredSecret || DEV_DEFAULT_SECRET;
const tursoUrl = (process.env.TURSO_DATABASE_URL || "").trim();
const tursoAuthToken = (process.env.TURSO_AUTH_TOKEN || "").trim();

if (!tursoUrl) {
  throw new Error("TURSO_DATABASE_URL is required for Better Auth");
}
if (!tursoAuthToken) {
  throw new Error("TURSO_AUTH_TOKEN is required for Better Auth");
}
if (!tursoUrl.startsWith("libsql://")) {
  throw new Error("TURSO_DATABASE_URL must use libsql:// to connect Turso");
}

declare global {
  // eslint-disable-next-line no-var
  var __videoAutoCutLibsqlDialect: LibsqlDialect | undefined;
}

const dialect =
  globalThis.__videoAutoCutLibsqlDialect ??
  new LibsqlDialect({
    url: tursoUrl,
    authToken: tursoAuthToken,
  });
if (!globalThis.__videoAutoCutLibsqlDialect) {
  globalThis.__videoAutoCutLibsqlDialect = dialect;
}

export const auth = betterAuth({
  appName: "video-auto-cut",
  baseURL,
  secret,
  database: {
    type: "sqlite",
    dialect,
  },
  emailAndPassword: {
    enabled: true,
    autoSignIn: true,
  },
  plugins: [
    jwt({
      jwks: {
        keyPairConfig: {
          alg: "RS256",
        },
      },
      jwt: {
        issuer: process.env.WEB_AUTH_ISSUER || baseURL,
        audience: process.env.WEB_AUTH_AUDIENCE || baseURL,
      },
    }),
  ],
  hooks: {
    before: createAuthMiddleware(async (ctx) => {
      if (ctx.path !== "/sign-up/email") {
        return;
      }
      const body = (ctx.body || {}) as Record<string, unknown>;
      const inviteCode = String(body.inviteCode || "").trim();
      if (!inviteCode) {
        throw new APIError("BAD_REQUEST", {
          message: "邀请码不能为空",
        });
      }
      try {
        const verifyResp = await fetch(`${apiBaseURL}/public/coupons/verify`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({code: inviteCode.toUpperCase()}),
          cache: "no-store",
        });
        if (!verifyResp.ok) {
          const text = await verifyResp.text();
          let message = "邀请码无效，请检查后重试";
          try {
            const payload = JSON.parse(text) as {error?: {message?: string}};
            message = payload?.error?.message || message;
          } catch {
            // Ignore parse failures and fallback to generic message.
          }
          throw new APIError("BAD_REQUEST", {message});
        }
      } catch (err) {
        if (err instanceof APIError) {
          throw err;
        }
        throw new APIError("BAD_REQUEST", {
          message: "邀请码校验失败，请稍后重试",
        });
      }
    }),
  },
});
