# Shared LLM SDK Util Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the mainline shared LLM client with the Aliyun-documented OpenAI SDK compatible implementation so all `video_auto_cut/` and `web_api/` LLM calls use one standard util.

**Architecture:** Keep `video_auto_cut/editing/llm_client.py` as the only shared entry point. Move transport logic from hand-written `urllib` to the OpenAI SDK, preserve the existing config surface (`build_llm_config`, `chat_completion`, `extract_json`), and route `enable_thinking` through the standard request shape.

**Tech Stack:** Python, OpenAI SDK, unittest

---

### Task 1: Convert the client contract test-first

**Files:**
- Modify: `web_api/tests/test_llm_client_thinking.py`
- Modify: `video_auto_cut/editing/llm_client.py`

**Step 1: Write the failing test**

Add tests that prove:
- `build_llm_config()` still reads `LLM_ENABLE_THINKING`
- `chat_completion()` instantiates `OpenAI(api_key=..., base_url=...)`
- `chat_completion()` calls `client.chat.completions.create(...)`
- the outgoing request includes `enable_thinking=True` when enabled

**Step 2: Run test to verify it fails**

Run: `python -m unittest web_api.tests.test_llm_client_thinking -v`
Expected: FAIL because the current implementation still patches `_post_json` instead of the SDK client.

**Step 3: Write minimal implementation**

- Replace the internal HTTP transport with the OpenAI SDK
- Preserve existing return shape and retries

**Step 4: Run test to verify it passes**

Run: `python -m unittest web_api.tests.test_llm_client_thinking -v`
Expected: PASS

### Task 2: Verify mainline regressions

**Files:**
- Verify: `video_auto_cut/editing/auto_edit.py`
- Verify: `video_auto_cut/editing/topic_segment.py`
- Verify: `video_auto_cut/asr/qwen3_asr.py`

**Step 1: Run tests**

Run: `python -m unittest discover -s web_api/tests -p 'test_*.py' -v`

**Step 2: Confirm expected behavior**

Expected: all tests pass with the SDK-backed shared util.

### Task 3: Re-run the real subtitle optimization experiment

**Files:**
- Input: `workdir/manual_verify/audio_run_0014508c/dji_export_20260302_122707_1772425627574_compose_0.audio.srt`
- Output: `workdir/manual_verify/sdk_kimi_thinking_<id>/...`

**Step 1: Run the experiment**

Use temporary env:
- `LLM_MODEL=kimi-k2.5`
- `LLM_ENABLE_THINKING=1`

Only rerun:
- `audio.srt -> auto_edit -> final_step1.srt`

**Step 2: Compare outputs**

Check:
- whether the run completes stably
- whether duplicate-removal quality improves
- whether punctuation artifacts remain
