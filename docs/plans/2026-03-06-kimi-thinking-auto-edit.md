# Kimi Thinking Auto Edit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add optional `enable_thinking` support to the shared LLM client, then rerun the existing subtitle optimization flow with `kimi-k2.5` in thinking mode and compare the output against the previous run.

**Architecture:** Keep the change narrow by extending the existing OpenAI-compatible LLM payload builder instead of branching in business logic. Control the behavior entirely through config so `auto_edit` and `topic_segment` can reuse it, then run a one-off experiment using the already-generated `audio.srt` input.

**Tech Stack:** Python, urllib, unittest, DashScope OpenAI-compatible API

---

### Task 1: Add a failing config/payload test

**Files:**
- Modify: `video_auto_cut/editing/llm_client.py`
- Create: `web_api/tests/test_llm_client_thinking.py`

**Step 1: Write the failing test**

Add tests that prove:
- `build_llm_config()` reads `LLM_ENABLE_THINKING=1`
- `chat_completion()` includes the thinking flag in the outgoing payload

**Step 2: Run test to verify it fails**

Run: `python -m unittest web_api.tests.test_llm_client_thinking -v`
Expected: FAIL because the config and payload do not yet include `enable_thinking`.

**Step 3: Write minimal implementation**

- Extend `build_llm_config()` with an `enable_thinking` boolean
- Teach `chat_completion()` to add the compatible extra payload field only when enabled

**Step 4: Run test to verify it passes**

Run: `python -m unittest web_api.tests.test_llm_client_thinking -v`
Expected: PASS

### Task 2: Verify regression safety

**Files:**
- Verify: `video_auto_cut/editing/auto_edit.py`
- Verify: `video_auto_cut/editing/topic_segment.py`
- Test: `web_api/tests/test_auto_edit_two_pass_rules.py`
- Test: `web_api/tests/test_auto_edit_e2e.py`

**Step 1: Run relevant tests**

Run: `python -m unittest discover -s web_api/tests -p 'test_*.py' -v`

**Step 2: Confirm expected behavior**

Expected: all existing tests still pass with thinking disabled by default.

### Task 3: Run the non-committed experiment

**Files:**
- Input: `workdir/manual_verify/audio_run_0014508c/dji_export_20260302_122707_1772425627574_compose_0.audio.srt`
- Output: `workdir/manual_verify/audio_run_<new>/...`

**Step 1: Run the experiment**

Use temporary environment overrides:
- `LLM_MODEL=kimi-k2.5`
- `LLM_ENABLE_THINKING=1`

Only rerun:
- `audio.srt -> auto_edit -> final_step1.srt -> step2 topics`

**Step 2: Compare outputs**

Check:
- duplicate-removal quality
- punctuation artifacts like `。，` and `，，`
- whether the "keep last duplicate" issue improves
