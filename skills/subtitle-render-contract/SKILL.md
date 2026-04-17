---
name: subtitle-render-contract
description: Use when Pi Agent receives plain timed subtitle text and must emit strict subtitle-render.v1 JSON for the renderer.
---

# Subtitle Render Contract

Pi Agent uses this skill for one job only: convert plain timed subtitle text into renderer-ready `subtitle-render.v1` JSON.

## Exact input
Accept only line-based subtitle text in this format:

`【HH:MM:SS.mmm-HH:MM:SS.mmm】文本`

Rules:
- one subtitle per line
- timestamps use 24-hour clock and millisecond precision
- `end` must be greater than `start`
- keep the subtitle text exactly as written after the closing bracket
- reject blank, malformed, or partial lines instead of guessing
- do not accept prose, markdown, bullets, tables, or mixed metadata

## Exact output
Return one JSON object only.

Forbidden:
- any text before or after the JSON
- markdown or code fences
- arrays at the top level
- alternate schema names
- extra top-level keys
- wrapper objects such as `render`, `input_props`, `props`, `payload`, `topics`, or `chapters`
- invented timings, labels, tokens, or layout fields

## Required top-level shape
```json
{
  "schema": "subtitle-render.v1",
  "source_format": "plain_timed_subtitle_text",
  "captions": [
    {
      "index": 1,
      "start": 0,
      "end": 1.8,
      "text": "..."
    }
  ],
  "segments": [
    {
      "start": 0,
      "end": 1.8
    }
  ]
}
```

## Caption rules
- `index` is 1-based and must preserve input order
- `start` and `end` are numbers in seconds, rounded to 3 decimals
- `text` is the source subtitle text
- `tokens`, `label`, and `alignmentMode` are optional
- if you include `tokens`, each token must have `text`, `start`, and `end`
- `sourceWordIndex` is optional on tokens; do not invent it
- if you include `label`, it may contain `badgeText` and `emphasisSpans`
- `emphasisSpans` use `{startToken, endToken}` with `endToken` exclusive
- `alignmentMode`, when present, must be one of `exact`, `fuzzy`, `degraded`, `missing`
- do not invent token timings, badge text, or emphasis spans

## Segment rules
- `segments` must be valid timeline ranges with `end > start`
- keep them in source order
- if no separate segment map exists, mirror the caption timeline

## Validation checklist
- JSON parses cleanly
- `schema` is exactly `subtitle-render.v1`
- `source_format` is exactly `plain_timed_subtitle_text`
- caption indexes are consecutive starting at 1
- every caption and segment has `end > start`
- every token span, if present, stays within its caption
- every emphasis span, if present, stays within its caption token range
- no extra fields are emitted
