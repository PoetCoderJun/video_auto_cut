

## WORKING MEMORY
[2026-04-16T04:47:02.360Z] 2026-04-16: Started Ralph task for browser E2E upload of test_data/raw/1.MOV. Created context snapshot + PRD/test spec, updated docs/requirements_todo.md, next step is booting local Web MVP and automating sign-up/upload/export flow.

[2026-04-16T05:06:59.988Z] 2026-04-16: Browser E2E found stale API process missing /test/run, then worker queue stalled on transient Turso sync failures (tls handshake eof). Patched web_api/db.py to continue on local replica when open sync transiently fails; added web_api/tests/test_db_turso_fallback.py and verified targeted unittest + diagnostics.
[2026-04-16T05:14:03.711Z] 2026-04-16: Observed API/worker replica drift under Turso mode when sync is flaky: API queue replica showed task queued while worker replica failed it. For next verification attempt, switching API/worker to WEB_DB_LOCAL_ONLY=1 (shared local sqlite replica) while keeping Next auth on Turso, to stabilize true browser E2E.
[2026-04-16T05:23:18.003Z] 2026-04-16: Completed browser E2E for test_data/raw/1.MOV. Final successful path used WEB_DB_LOCAL_ONLY=1 start_web_mvp debug, job_id=job_958e68a210a6, export saved to workdir/e2e_1mov_browser/job_958e68a210a6_export.mp4. Code fix landed in web_api/db.py + test_db_turso_fallback.py for transient Turso open-sync fallback.