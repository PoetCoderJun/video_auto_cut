import {betterAuth} from "better-auth";
import {createAuthMiddleware, APIError} from "better-auth/api";
import {LibsqlDialect} from "@libsql/kysely-libsql";
import {jwt} from "better-auth/plugins";

const baseURL = process.env.BETTER_AUTH_URL || process.env.NEXT_PUBLIC_SITE_URL || "http://127.0.0.1:3000";
const secret = process.env.BETTER_AUTH_SECRET || "video-auto-cut-dev-better-auth-secret-change-me";
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
    }),
  },
});
