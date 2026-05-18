import {betterAuth} from "better-auth";
import {LibsqlDialect} from "@libsql/kysely-libsql";
import {jwt} from "better-auth/plugins";

import {getBetterAuthLibsqlClient} from "./auth-db";

const baseURL = process.env.BETTER_AUTH_URL || process.env.NEXT_PUBLIC_SITE_URL || "http://127.0.0.1:3000";
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

declare global {
  // eslint-disable-next-line no-var
  var __videoAutoCutLibsqlDialect: LibsqlDialect | undefined;
}

const dialect =
  globalThis.__videoAutoCutLibsqlDialect ??
  new LibsqlDialect({
    // `@libsql/kysely-libsql` vendors its own `@libsql/client` types, so the
    // runtime-compatible client instance needs a narrow cast here.
    client: getBetterAuthLibsqlClient() as any,
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
        disablePrivateKeyEncryption: true,
        // Filter out any rows where privateKey was stored as NULL (e.g. from a
        // partial write or Turso column-mapping bug). Returning no keys causes
        // Better Auth to call createJwk() and generate a fresh valid pair.
        // This prevents the cascade: JSON.parse(null) → null → importJWK(null)
        //   → TypeError: JWK must be an object
      },
      jwt: {
        issuer: process.env.WEB_AUTH_ISSUER || baseURL,
        audience: process.env.WEB_AUTH_AUDIENCE || baseURL,
      },
      adapter: {
        getJwks: async (ctx) => {
          const keys = await ctx.context.adapter.findMany<{
            id: string;
            publicKey: string;
            privateKey: string;
            createdAt: Date;
            expiresAt?: Date;
            alg?: string;
          }>({ model: "jwks" });
          return (keys ?? []).filter((k: { privateKey: string | null | undefined }) => {
            if (!k.privateKey) return false;
            try {
              const parsed = JSON.parse(k.privateKey);
              return parsed !== null && typeof parsed === "object";
            } catch {
              return false;
            }
          });
        },
      },
    }),
  ],
});
