# Test Single Source Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make Test, Test.5, and Step2 each consume only the previous step's output, with Test lines built directly from `optimized_srt`.

**Architecture:** Remove the legacy Test "original SRT vs optimized SRT alignment" assumption. Treat `optimized_srt` as the sole source of truth for Test editable lines, preserving `<<REMOVE>>` lines as recoverable rows and keeping downstream `final_test.srt` / Step2 behavior unchanged.

**Tech Stack:** Python, FastAPI service layer, `srt`, unittest

---

### Task 1: Replace Test line-builder contract

**Files:**
- Modify: `web_api/utils/srt_utils.py`
- Modify: `web_api/services/test.py`
- Test: `web_api/tests/test_test_srt_utils.py`

**Step 1: Write the failing test**

Add tests that prove:
- Test lines can be built from a single `optimized_srt`
- merged lines stay merged instead of expanding back to original ASR granularity
- `<<REMOVE>>` lines remain present and recoverable

**Step 2: Run test to verify it fails**

Run: `python -m unittest web_api.tests.test_test_srt_utils -v`
Expected: FAIL because the current API still expects `original_srt` + `optimized_srt`.

**Step 3: Write minimal implementation**

- Add a single-source builder in `web_api/utils/srt_utils.py`
- Update `web_api/services/test.py` to call it with `optimized_srt_path`
- Keep the existing output schema so frontend and Step2 do not need protocol changes

**Step 4: Run test to verify it passes**

Run: `python -m unittest web_api.tests.test_test_srt_utils -v`
Expected: PASS

**Step 5: Commit**

```bash
git add web_api/utils/srt_utils.py web_api/services/test.py web_api/tests/test_test_srt_utils.py
git commit -m "fix(web): make test consume optimized srt only"
```

### Task 2: Verify downstream compatibility

**Files:**
- Verify: `web_api/services/step2.py`
- Verify: `web_frontend/components/job-workspace.tsx`
- Test: `web_api/tests/test_auto_edit_e2e.py`

**Step 1: Write or adjust the failing test**

Only if needed, add a regression assertion that Step2 still consumes `final_test.srt` / kept `line_id`s without requiring original ASR rows.

**Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s web_api/tests -p 'test_*.py' -v`
Expected: FAIL only if downstream still depends on original-row alignment.

**Step 3: Write minimal implementation**

Adjust only the minimum downstream code required by the new Test source-of-truth model.

**Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s web_api/tests -p 'test_*.py' -v`
Expected: PASS

**Step 5: Commit**

```bash
git add web_api web_frontend
git commit -m "test(web): verify test single-source downstream flow"
```

### Task 3: Verify frontend/build impact

**Files:**
- Verify: `web_frontend/lib/api.ts`
- Verify: `web_frontend/components/job-workspace.tsx`

**Step 1: Run focused verification**

Run:
- `cd web_frontend && npx tsc --noEmit`
- `cd web_frontend && BETTER_AUTH_SECRET=codex-temporary-build-secret-20260306 npm run build`

**Step 2: Confirm expected behavior**

Expected:
- typecheck passes
- production build passes
- no new contract changes required in frontend code

**Step 3: Commit**

```bash
git add web_frontend
git commit -m "chore(web): verify test single-source build flow"
```
