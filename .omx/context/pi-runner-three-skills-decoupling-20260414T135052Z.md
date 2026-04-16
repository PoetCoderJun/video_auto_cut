task statement
Refine the current video_auto_cut PI editing architecture so the repo keeps only three editing skills (delete, polish, chapter), removes chunk-centric and JSON-repair-centric design, centralizes task framing in one system prompt, and uses one clean PI runner decoupled from skills.

desired outcome
A consensus-ready architecture where video_auto_cut owns a single clean PI runner and canonical Step1 editing path, while skills become thin contracts for delete/polish/chapter only.

known facts/evidence
- auto_edit.py directly instantiates PI loops and llm config internally.
- current design depends on chunking, boundary reconciliation, and explicit JSON repair fallbacks.
- top-level skill doc says skill should orchestrate repo modules, not own loop/chunk rules.
- pipeline_service exposes run_auto_edit and topic segmentation separately.
- step1 backend still immediately generates chapters and step2 holds chapter invariants.
- full_pipeline.py is stale/broken.
- editing/__init__.py eagerly imports TopicSegmenter.
- targeted PI tests pass under python 3.9 while python3.8 fails on newer typing syntax.

constraints
- Fix THIS repo, not tracking_agent.
- Keep only delete/polish/chapter skills.
- No chunk-driven design.
- No explicit JSON repair/fixup prompt dependency.
- Put full task framing into one system prompt.
- Preserve direct-runnable decoupling goal.

unknowns/open questions
- Exact final placement of chapter invariants after Step2 simplification.
- Whether chapter remains a separate optional capability or folded into runner output contract.
- Minimal wrapper shape for web_api after seam cleanup.

likely codebase touchpoints
- video_auto_cut/editing/auto_edit.py
- video_auto_cut/editing/pi_agent_remove.py
- video_auto_cut/editing/pi_agent_polish.py
- video_auto_cut/editing/pi_agent_boundary.py
- video_auto_cut/editing/pi_agent_chunking.py
- video_auto_cut/editing/pi_agent_merge.py
- video_auto_cut/orchestration/pipeline_service.py
- video_auto_cut/orchestration/full_pipeline.py
- web_api/services/step1.py
- web_api/services/step2.py
- skills/video-auto-cut-human-loop/SKILL.md
