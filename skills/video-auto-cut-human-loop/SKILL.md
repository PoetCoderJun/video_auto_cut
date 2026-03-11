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
Reuse the existing repo code and scripts whenever possible.

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

## Workflow

1. Resolve and validate `input_video_path`.
2. Derive a working artifact directory near the input video or under a user-provided workdir.
3. Run transcription and step1 auto-edit with the repo's existing pipeline.
4. Stop and present the step1 artifacts for human review.
5. Apply human edits to step1 outputs or wait for explicit approval.
6. Run step2 topic segmentation from the human-confirmed step1 result.
7. Stop and present the step2 artifacts for human review.
8. Apply human edits to step2 outputs or wait for explicit approval.
9. Build cut subtitles/timeline from the confirmed artifacts.
10. Render or cut the final video to `output_video_path`.

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

Prefer using existing repo modules:

- `video_auto_cut.orchestration.full_pipeline` for transcribe + auto-edit
- `video_auto_cut.orchestration.pipeline_service` for stage-specific orchestration
- `video_auto_cut.editing.topic_segment.TopicSegmenter` for step2
- `video_auto_cut.rendering.cut_srt` and `video_auto_cut.rendering.cut.Cutter` for final cut outputs

When the user wants a robust reusable workflow, prefer adding or using a dedicated wrapper script rather than embedding long ad hoc shell or Python snippets into the conversation.

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

- confirmed `step1` subtitles/json
- confirmed `step2` topics/json
- cut subtitles/timeline for render
- final cut video at `output_video_path`

If final render is not possible, stop with the reason and preserve all intermediate approved artifacts.
