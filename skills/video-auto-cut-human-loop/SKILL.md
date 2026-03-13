---
name: video-auto-cut-human-loop
description: Human-in-the-loop video auto-cut workflow for Codex, Claude Code, or PI agents. Use this skill when the task is to turn a local video into reviewable step1 subtitles, reviewable step2 chapters, and a final cut video while requiring explicit human confirmation after step1 and step2.
---

# Video Auto Cut Human Loop

Use this skill when the user wants an agent to run the repo's existing video-auto-cut pipeline with mandatory human review checkpoints.

This skill is a top-level workflow skill, not a prompt-only rewrite skill.
It orchestrates existing repo modules for:

- ASR transcription
- step1 remove/polish
- human confirmation of step1
- step2 topic segmentation
- human confirmation of step2
- final cut video export

Do not reimplement the pipeline logic in the skill body.
Reuse the repo's local wrapper and Python pipeline.

## Required inputs

Collect or confirm these values before running:

- `input_video_path`: absolute or repo-relative path to the source video
- `output_video_path`: desired final output video path

If the user does not specify them, stop and ask.

Optional but usually needed:

- `workdir_root`: where intermediate artifacts should be written
- `llm_base_url`
- `llm_model`
- `llm_api_key`
- ASR-related env/config

## Primary entrypoint

Prefer `scripts/run_human_loop_pipeline.py`.

Use these subcommands:

- `run`
- `approve-step1`
- `approve-step2`
- `render`
- `status`

## Workflow

1. Resolve and validate `input_video_path`.
2. Derive a working artifact directory near the input video or under a user-provided workdir.
3. Run `python scripts/run_human_loop_pipeline.py run ...` to generate Step1 draft artifacts.
4. Stop and present `step1/draft_step1.json` and `step1/draft_step1.srt` for human review.
5. After the human edits or approves Step1, run `approve-step1`.
6. Run `run` again to generate Step2 draft artifacts.
7. Stop and present `step2/draft_topics.json` for human review.
8. After the human edits or approves Step2, run `approve-step2`.
9. Run `render` to export the final cut video.

Never skip the step1 or step2 confirmation checkpoint unless the user explicitly says to bypass human review.

## Human checkpoints

After step1, stop and ask the human to confirm or edit:

- kept/removed subtitle lines
- optimized subtitle wording
- any obvious ASR or semantic mistakes

After step2, stop and ask the human to confirm or edit:

- chapter titles
- chapter boundaries
- line-to-chapter coverage

Treat approval as a hard gate.
Do not continue to final cutting until the human explicitly confirms the current stage.

## Execution guidance

Prefer using:

- `scripts/run_human_loop_pipeline.py` for human-gated orchestration
- `video_auto_cut.orchestration.pipeline_service` for transcribe / step1 / step2 execution
- `video_auto_cut.rendering.cut_srt` and `video_auto_cut.rendering.cut.Cutter` for final output

Avoid ad hoc shell glue when the wrapper already supports the requested stage.

## Loop and chunk rules

The loop/chunk logic belongs in repo code, not in the main skill body.

Reason:

- it is fragile and benefits from deterministic reuse
- it already exists in the auto-edit implementation
- the skill should stay concise and orchestration-focused

Read [references/workflow.md](references/workflow.md) for:

- artifact contract
- recommended file layout
- how to model the two human approval gates
- where loop/chunk rules should live

## Output contract

The workflow should leave behind these user-visible outputs:

- editable `step1/draft_step1.*`
- confirmed `step1/final_step1.*`
- editable `step2/draft_topics.json`
- confirmed `step2/final_topics.json`
- cut subtitles/timeline for render
- final cut video at `output_video_path`

If final render is not possible, stop with the reason and preserve all intermediate approved artifacts.
