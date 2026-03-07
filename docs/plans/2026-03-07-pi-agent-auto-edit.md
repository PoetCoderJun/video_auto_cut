# PI Agent Auto-Edit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the current fixed two-pass auto-edit flow with a Kimi-driven PI agent that runs `删后置重复 -> 合并短句 -> 逐行润色` as an autonomous `改 + 查 + 改` loop, while keeping chunking mechanical and output state auditable.

**Architecture:** Keep chunking fixed at `30` lines with overlap, but move chunk execution into a dedicated orchestrator that manages explicit skills. Each chunk runs `inspect -> remove draft -> remove critique -> remove revise -> rule merge -> polish draft -> polish critique -> polish revise`, then a boundary pass reconciles overlap regions. Merge remains deterministic, but every merged line stores source line IDs so Step1 editing can stay debuggable.

**Tech Stack:** Python, `srt`, existing `video_auto_cut.editing.llm_client`, unittest, existing Step1 SRT pipeline.

---

### Task 1: Define PI agent state and contracts

**Files:**
- Create: `video_auto_cut/editing/pi_agent_models.py`
- Modify: `video_auto_cut/editing/auto_edit.py`
- Test: `web_api/tests/test_pi_agent_models.py`

**Step 1: Write the failing test**

Add tests for dataclasses / helpers covering:
- chunk window metadata (`chunk_id`, `core_start`, `core_end`, overlap ranges)
- per-line decision state (`line_id`, `original_text`, `remove_action`, `reason`, `confidence`)
- merged group state (`source_line_ids`, merged text, merged timing)

**Step 2: Run test to verify it fails**

Run: `python -m unittest web_api.tests.test_pi_agent_models -v`
Expected: FAIL because `pi_agent_models.py` does not exist.

**Step 3: Write minimal implementation**

Add typed dataclasses for:
- `ChunkWindow`
- `LineDecision`
- `MergedGroup`
- `ChunkExecutionState`
- `BoundaryReviewState`

Keep them serialization-friendly so they can be written into debug JSON later.

**Step 4: Run test to verify it passes**

Run: `python -m unittest web_api.tests.test_pi_agent_models -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add video_auto_cut/editing/pi_agent_models.py web_api/tests/test_pi_agent_models.py video_auto_cut/editing/auto_edit.py
git commit -m "feat(auto-edit): add pi agent state models"
```

### Task 2: Build fixed-size chunk planner with overlap

**Files:**
- Create: `video_auto_cut/editing/pi_agent_chunking.py`
- Modify: `video_auto_cut/editing/auto_edit.py`
- Test: `web_api/tests/test_pi_agent_chunking.py`

**Step 1: Write the failing test**

Add tests for:
- exact `30`-line chunking
- `4`-line overlap on both sides
- correct core/context slicing for first, middle, and last chunk

**Step 2: Run test to verify it fails**

Run: `python -m unittest web_api.tests.test_pi_agent_chunking -v`
Expected: FAIL because planner does not exist.

**Step 3: Write minimal implementation**

Implement a pure function that converts `segments` into `ChunkWindow` items without semantic decisions. Reuse current constants:
- `AUTO_EDIT_CHUNK_LINES`
- `AUTO_EDIT_CHUNK_OVERLAP_LINES`

**Step 4: Run test to verify it passes**

Run: `python -m unittest web_api.tests.test_pi_agent_chunking -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add video_auto_cut/editing/pi_agent_chunking.py web_api/tests/test_pi_agent_chunking.py video_auto_cut/editing/auto_edit.py
git commit -m "feat(auto-edit): add fixed chunk planner for pi agent"
```

### Task 3: Implement remove-phase PI skill loop

**Files:**
- Create: `video_auto_cut/editing/pi_agent_remove.py`
- Modify: `video_auto_cut/editing/llm_client.py`
- Modify: `video_auto_cut/editing/auto_edit.py`
- Test: `web_api/tests/test_pi_agent_remove.py`

**Step 1: Write the failing test**

Add tests that feed a chunk with retake chains and assert:
- draft pass can mark an earlier line `REMOVE`
- critique pass can overturn a bad `KEEP`
- revise pass returns final structured decisions with one row per source line
- removed lines cannot be restored silently in later phases

Include the regression example:
- `不用反复重复`
- `不用反复重头录制`

**Step 2: Run test to verify it fails**

Run: `python -m unittest web_api.tests.test_pi_agent_remove -v`
Expected: FAIL because PI remove skill does not exist.

**Step 3: Write minimal implementation**

Implement one class with three explicit prompt builders:
- `build_remove_inspect_prompt`
- `build_remove_critique_prompt`
- `build_remove_revise_prompt`

Execution contract:
- input: tagged lines for a chunk
- output: strict JSON containing `KEEP` / `REMOVE`, `reason`, `confidence`
- max loop: `2` iterations
- same Kimi backend as current shared client

Do not free-form agent tool use. The autonomy comes from controlled critique/revise rounds, not unconstrained planning.

**Step 4: Run test to verify it passes**

Run: `python -m unittest web_api.tests.test_pi_agent_remove -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add video_auto_cut/editing/pi_agent_remove.py video_auto_cut/editing/auto_edit.py video_auto_cut/editing/llm_client.py web_api/tests/test_pi_agent_remove.py
git commit -m "feat(auto-edit): add pi agent remove loop"
```

### Task 4: Move merge phase to explicit merged-group state

**Files:**
- Modify: `video_auto_cut/editing/auto_edit.py`
- Create: `video_auto_cut/editing/pi_agent_merge.py`
- Test: `web_api/tests/test_pi_agent_merge.py`

**Step 1: Write the failing test**

Add tests covering:
- only `KEEP` lines participate in merge
- `REMOVE` lines hard-stop merge chains
- merged output records `source_line_ids`
- question marks preserve hard boundary

**Step 2: Run test to verify it fails**

Run: `python -m unittest web_api.tests.test_pi_agent_merge -v`
Expected: FAIL because merged-group helper does not exist.

**Step 3: Write minimal implementation**

Extract the current deterministic merge logic into a reusable helper that returns:
- merged display text
- merged timing
- source line IDs

Do not let this phase lose provenance.

**Step 4: Run test to verify it passes**

Run: `python -m unittest web_api.tests.test_pi_agent_merge -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add video_auto_cut/editing/pi_agent_merge.py video_auto_cut/editing/auto_edit.py web_api/tests/test_pi_agent_merge.py
git commit -m "refactor(auto-edit): preserve merge provenance for pi agent"
```

### Task 5: Implement polish-phase PI skill loop

**Files:**
- Create: `video_auto_cut/editing/pi_agent_polish.py`
- Modify: `video_auto_cut/editing/auto_edit.py`
- Test: `web_api/tests/test_pi_agent_polish.py`

**Step 1: Write the failing test**

Add tests for:
- merged groups are polished one group at a time
- critique pass catches semantic drift and awkward phrases
- non-question lines end without punctuation
- the regression phrase `不用反复重复` is rejected when a more specific later line exists in the same chunk context

**Step 2: Run test to verify it fails**

Run: `python -m unittest web_api.tests.test_pi_agent_polish -v`
Expected: FAIL because polish PI skill does not exist.

**Step 3: Write minimal implementation**

Implement:
- `build_polish_draft_prompt`
- `build_polish_critique_prompt`
- `build_polish_revise_prompt`

The critique prompt must compare polished text back against source line IDs, so the agent can say “this rewrite preserved a bad early version” and regenerate.

**Step 4: Run test to verify it passes**

Run: `python -m unittest web_api.tests.test_pi_agent_polish -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add video_auto_cut/editing/pi_agent_polish.py video_auto_cut/editing/auto_edit.py web_api/tests/test_pi_agent_polish.py
git commit -m "feat(auto-edit): add pi agent polish loop"
```

### Task 6: Add overlap boundary reconciliation

**Files:**
- Create: `video_auto_cut/editing/pi_agent_boundary.py`
- Modify: `video_auto_cut/editing/auto_edit.py`
- Test: `web_api/tests/test_pi_agent_boundary.py`

**Step 1: Write the failing test**

Add tests for:
- duplicate meaning across chunk overlap
- earlier chunk tail removed because later chunk head is final version
- merged-group provenance survives boundary reconciliation

**Step 2: Run test to verify it fails**

Run: `python -m unittest web_api.tests.test_pi_agent_boundary -v`
Expected: FAIL because boundary reconciler does not exist.

**Step 3: Write minimal implementation**

Use only overlap lines as boundary context. The boundary skill may:
- drop duplicate earlier decisions
- block unsafe merges across chunk edges
- leave an audit trail in debug output

Do not re-run full chunk generation here.

**Step 4: Run test to verify it passes**

Run: `python -m unittest web_api.tests.test_pi_agent_boundary -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add video_auto_cut/editing/pi_agent_boundary.py video_auto_cut/editing/auto_edit.py web_api/tests/test_pi_agent_boundary.py
git commit -m "feat(auto-edit): add pi agent boundary reconciliation"
```

### Task 7: Wire PI agent into AutoEdit and Step1 outputs

**Files:**
- Modify: `video_auto_cut/editing/auto_edit.py`
- Modify: `video_auto_cut/orchestration/pipeline_service.py`
- Modify: `web_api/services/step1.py`
- Modify: `web_api/utils/srt_utils.py`
- Test: `web_api/tests/test_auto_edit_e2e.py`
- Test: `web_api/tests/test_step1_srt_utils.py`

**Step 1: Write the failing test**

Add end-to-end tests covering:
- `run_auto_edit()` uses PI agent path
- `optimized.srt` remains auditable with stable line IDs
- Step1 can read PI-agent output without losing remove markers
- merged groups keep provenance in debug JSON

**Step 2: Run test to verify it fails**

Run: `python -m unittest web_api.tests.test_auto_edit_e2e web_api.tests.test_step1_srt_utils -v`
Expected: FAIL until the new output contract is wired through.

**Step 3: Write minimal implementation**

Integrate the new orchestrator as the main auto-edit path. Keep the public API surface stable:
- `run_auto_edit()` still returns `optimized.srt`
- debug JSON gains PI-agent execution metadata

Step1 must consume the new SRT format without dropping editability. If merged display lines are produced for export, preserve source line IDs in debug / sidecar data.

**Step 4: Run test to verify it passes**

Run: `python -m unittest web_api.tests.test_auto_edit_e2e web_api.tests.test_step1_srt_utils -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add video_auto_cut/editing/auto_edit.py video_auto_cut/orchestration/pipeline_service.py web_api/services/step1.py web_api/utils/srt_utils.py web_api/tests/test_auto_edit_e2e.py web_api/tests/test_step1_srt_utils.py
git commit -m "feat(auto-edit): wire pi agent into step1 pipeline"
```

### Task 8: Verify on real media and compare prompts

**Files:**
- Modify: `docs/plans/2026-03-07-pi-agent-auto-edit.md`
- Output only: `workdir/model_compare/`

**Step 1: Run focused automated verification**

Run:

```bash
python -m unittest \
  web_api.tests.test_pi_agent_models \
  web_api.tests.test_pi_agent_chunking \
  web_api.tests.test_pi_agent_remove \
  web_api.tests.test_pi_agent_merge \
  web_api.tests.test_pi_agent_polish \
  web_api.tests.test_pi_agent_boundary \
  web_api.tests.test_auto_edit_e2e \
  web_api.tests.test_step1_srt_utils -v
```

Expected: PASS.

**Step 2: Run real-media verification**

Run the actual Step1 auto-edit flow against:
- `/Users/huzujun/Downloads/dji_export_20260302_122707_1772425627574_compose_0.MOV`

Compare:
- latency
- kept line count
- kept duration
- whether the `不用反复重复` class of error survives
- whether manual Step1 editing is easier because provenance is preserved

**Step 3: Record findings**

Append prompt/latency/quality notes to this plan file so later prompt tuning stays grounded in evidence.

**Step 4: Commit**

```bash
git add docs/plans/2026-03-07-pi-agent-auto-edit.md
git commit -m "docs: record pi agent verification results"
```

Plan complete and saved to `docs/plans/2026-03-07-pi-agent-auto-edit.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
