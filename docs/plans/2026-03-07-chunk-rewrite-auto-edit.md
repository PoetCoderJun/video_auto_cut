# Chunk Rewrite Auto Edit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Change auto-edit from line-by-line polish to chunk-level rewrite after removal and short-line merging.

**Architecture:** Keep the existing remove/boundary-review flow, then build merged keep-groups and send each batch of groups to the LLM for contextual rewrite. Convert the rewritten groups back into merged subtitles while preserving removed lines as explicit `<<REMOVE>>` markers for Step1 UI.

**Tech Stack:** Python, unittest, existing `video_auto_cut` PI-agent modules

---

### Task 1: Add failing tests for chunk-level rewrite

**Files:**
- Modify: `web_api/tests/test_pi_agent_polish.py`
- Modify: `web_api/tests/test_auto_edit_e2e.py`

**Step 1: Write the failing test**

Add coverage that:
- the polish loop can rewrite merged groups instead of single lines
- `_auto_edit_segments()` rewrites merged keep-groups with contextual prompts and emits merged Step1 lines

**Step 2: Run test to verify it fails**

Run: `python -m unittest web_api.tests.test_pi_agent_polish web_api.tests.test_auto_edit_e2e -v`

Expected: failures showing the current implementation still expects line-level polish

### Task 2: Implement chunk rewrite loop

**Files:**
- Modify: `video_auto_cut/editing/pi_agent_polish.py`
- Modify: `video_auto_cut/editing/auto_edit.py`

**Step 1: Write minimal implementation**

Add a merged-group rewrite loop that:
- accepts `MergedGroup` batches
- prompts the LLM to boldly rewrite chunk text with context
- preserves facts but allows fixing likely ASR errors and incomplete phrases
- returns rewritten `MergedGroup` values

**Step 2: Rebuild final optimized subtitles from rewritten groups**

Keep remove markers for deleted lines, and emit one merged subtitle per rewritten keep-group.

### Task 3: Verify

**Files:**
- Test: `web_api/tests/test_pi_agent_polish.py`
- Test: `web_api/tests/test_auto_edit_e2e.py`

**Step 1: Run targeted tests**

Run: `python -m unittest web_api.tests.test_pi_agent_polish web_api.tests.test_auto_edit_e2e -v`

**Step 2: Run broader regression tests if targeted tests pass**

Run: `python -m unittest web_api.tests.test_auto_edit_two_pass_rules -v`
