---
name: video-auto-cut-human-loop
description: Auto-cut a local talking-head or oral presentation video into a final clip from the input video path alone. Use this skill when the user wants a local video edited into a concise final cut; step1 subtitle review and step2 chapter review are the default behavior, and the output path should be inferred when omitted.
---

# Video Auto Cut Human Loop

Use this skill when the user gives a local video path and wants the agent to produce a cleaned-up final cut.

This is a top-level workflow skill for剪辑口播视频.
Treat it as the default way to process a local talking-head video in this repo.

The user should only need to provide the input video path.
Review checkpoints and output-path inference are built into the workflow.

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

## Default behavior

1. Resolve and validate the input video path.
2. Infer the output path if the user omitted it, and tell the user which default path will be used.
3. Generate Step1 review artifacts from the source video.
4. Pause for Step1 human review.
5. Generate Step2 review artifacts from the human-confirmed Step1 result.
6. Pause for Step2 human review.
7. Render and export the final cut video after both checkpoints are approved.

Step1 and Step2 confirmation are the default behavior.
Never skip either checkpoint unless the user explicitly says to bypass human review.

## Review protocol

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

## Agent contract

Use the repo's existing orchestration entrypoint for this workflow rather than inventing ad hoc glue.
Keep implementation details out of the user conversation unless they are needed to explain a failure or request confirmation.

## Design rule

Loop, chunking, and intermediate orchestration rules belong in repo code, not in user-facing explanations.
This skill should stay focused on task intent, default behavior, review gates, and outputs.

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

## Natural triggers

This skill should trigger for prompts like:

- `把 /path/to/input.mp4 自动剪成成片`
- `处理这个视频：/path/to/input.mp4`
- `帮我剪一下这个口播视频 /path/to/input.mp4`
- `把这个口播视频剪一下 /path/to/input.mp4`
- `帮我自动剪辑这个讲解视频 /path/to/input.mp4`

The user does not need to mention:

- Step1 review
- Step2 review
- output path defaults
- internal scripts
