---
name: video-auto-cut-human-loop
description: Auto-cut a local talking-head video into a final clip from the input video path alone. Use this skill when the user wants a local video processed into step1 review subtitles, step2 review chapters, and a final exported cut; step1 and step2 human approval are the default behavior, and the output path should be inferred when omitted.
---

# Video Auto Cut Human Loop

Use this skill when the user gives a local video path and wants the agent to turn it into a final cut.

Do not require the user to ask for review checkpoints explicitly.
Step1 and Step2 review are part of the default workflow.

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

Collect or infer these values before running:

- `input_video_path`: absolute or repo-relative path to the source video

Treat `output_video_path` as optional:

- if the user specifies a path, use it
- otherwise default to `<current working directory>/<input_stem>_cut.mp4`
- tell the user which default path you chose, but do not ask them to repeat it

Optional but usually needed:

- `workdir_root`: where intermediate artifacts should be written
- `llm_base_url`
- `llm_model`
- `llm_api_key`
- ASR-related env/config

## Workflow

1. Resolve and validate `input_video_path`.
2. Infer `output_video_path` if the user omitted it, and tell the user the default you chose.
3. Derive a working artifact directory near the input video or under a user-provided workdir.
4. Use the repo's human-loop wrapper to generate Step1 draft artifacts.
5. Stop and present `step1/draft_step1.json` and `step1/draft_step1.srt` for human review.
6. After the human edits or approves Step1, continue into Step2.
7. Generate Step2 draft artifacts.
8. Stop and present `step2/draft_topics.json` for human review.
9. After the human edits or approves Step2, continue to render.
10. Export the final cut video.

Step1 and Step2 confirmation are the default behavior.
Never skip either checkpoint unless the user explicitly says to bypass human review.

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

Do not ask whether the user wants review checkpoints.
Assume they do unless they explicitly opt out.

The user should not need to say:

- that Step1 needs review
- that Step2 needs review
- that the output path should be auto-derived when omitted

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

## Trigger examples

This skill should trigger for prompts like:

- `把 /path/to/input.mp4 自动剪成成片`
- `处理这个视频：/path/to/input.mp4`
- `帮我剪一下这个口播视频 /path/to/input.mp4`

The user does not need to mention Step1, Step2, output path defaults, or internal scripts.
