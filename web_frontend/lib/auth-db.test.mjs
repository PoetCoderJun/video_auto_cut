import test from "node:test";
import assert from "node:assert/strict";
import path from "node:path";

import {buildBetterAuthLibsqlConfig, createBetterAuthLibsqlClient} from "./auth-db.ts";

test("buildBetterAuthLibsqlConfig prefers embedded replica when TURSO_LOCAL_REPLICA_PATH is set", () => {
  const config = buildBetterAuthLibsqlConfig({
    TURSO_DATABASE_URL: "libsql://example.turso.io",
    TURSO_AUTH_TOKEN: "token",
    TURSO_LOCAL_REPLICA_PATH: "./workdir/web_api_turso_replica.db",
    TURSO_SYNC_INTERVAL: "2",
  });

  assert.equal(config.authToken, "token");
  assert.equal(config.syncUrl, "libsql://example.turso.io");
  assert.equal(config.syncInterval, 2000);
  assert.equal(
    config.url,
    `file:${path.resolve("./workdir/web_api_turso_replica.auth.db")}`,
  );
});

test("buildBetterAuthLibsqlConfig honors explicit Better Auth replica path", () => {
  const config = buildBetterAuthLibsqlConfig({
    TURSO_DATABASE_URL: "libsql://example.turso.io",
    TURSO_AUTH_TOKEN: "token",
    TURSO_LOCAL_REPLICA_PATH: "./workdir/web_api_turso_replica.db",
    BETTER_AUTH_TURSO_LOCAL_REPLICA_PATH: "./workdir/custom-auth-replica.db",
  });

  assert.equal(
    config.url,
    `file:${path.resolve("./workdir/custom-auth-replica.db")}`,
  );
});

test("buildBetterAuthLibsqlConfig falls back to remote Turso when no replica path is provided", () => {
  const config = buildBetterAuthLibsqlConfig({
    TURSO_DATABASE_URL: "libsql://example.turso.io",
    TURSO_AUTH_TOKEN: "token",
    TURSO_LOCAL_REPLICA_PATH: "",
  });

  assert.equal(config.url, "libsql://example.turso.io");
  assert.equal(config.authToken, "token");
  assert.equal(config.syncUrl, undefined);
});

test("buildBetterAuthLibsqlConfig can force Better Auth to local-only replica mode", () => {
  const config = buildBetterAuthLibsqlConfig({
    TURSO_DATABASE_URL: "libsql://example.turso.io",
    TURSO_AUTH_TOKEN: "token",
    TURSO_LOCAL_REPLICA_PATH: "./workdir/web_api_turso_replica.db",
    BETTER_AUTH_LOCAL_ONLY: "1",
  });

  assert.equal(
    config.url,
    `file:${path.resolve("./workdir/web_api_turso_replica.auth.db")}`,
  );
  assert.equal(config.syncUrl, undefined);
  assert.equal(config.authToken, undefined);
});

test("createBetterAuthLibsqlClient falls back to local replica when sync connect fails", () => {
  const calls = [];
  const createClientStub = (config) => {
    calls.push(config);
    if (calls.length === 1) {
      throw new Error("sync error: error trying to connect: tls handshake eof");
    }
    return {kind: "local"};
  };

  const client = createBetterAuthLibsqlClient(
    buildBetterAuthLibsqlConfig({
      TURSO_DATABASE_URL: "libsql://example.turso.io",
      TURSO_AUTH_TOKEN: "token",
      TURSO_LOCAL_REPLICA_PATH: "./workdir/web_api_turso_replica.db",
    }),
    createClientStub,
  );

  assert.deepEqual(client, {kind: "local"});
  assert.equal(calls.length, 2);
  assert.equal(calls[0].syncUrl, "libsql://example.turso.io");
  assert.equal(calls[1].url, `file:${path.resolve("./workdir/web_api_turso_replica.auth.db")}`);
  assert.equal(calls[1].syncUrl, undefined);
});
