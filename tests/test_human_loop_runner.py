from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_auto_cut.human_loop.artifacts import (
    STATUS_STEP1_CONFIRMED,
    STATUS_STEP1_READY,
    STATUS_STEP2_READY,
    derive_output_video_path,
)
from video_auto_cut.human_loop.runner import approve_step1, run_until_human_gate
from video_auto_cut.human_loop.runner import advance_workflow
from video_auto_cut.orchestration.pipeline_service import PipelineOptions


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class HumanLoopRunnerTests(unittest.TestCase):
    def test_default_output_path_uses_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_video = root / "nested" / "demo.mov"
            input_video.parent.mkdir(parents=True, exist_ok=True)
            input_video.write_bytes(b"video")
            cwd = root / "cwd"
            cwd.mkdir(parents=True, exist_ok=True)

            output_path = derive_output_video_path(input_video, cwd=cwd)

            self.assertEqual(output_path, (cwd / "demo_cut.mp4").resolve())

    def test_run_until_human_gate_creates_step1_review_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_video = root / "demo.mp4"
            input_video.write_bytes(b"video")
            output_video = root / "output.mp4"
            artifact_root = root / "artifacts"

            def fake_transcribe(video_path: Path, options: PipelineOptions) -> Path:
                srt_path = video_path.with_suffix(".srt")
                _write_text(
                    srt_path,
                    "1\n00:00:00,000 --> 00:00:01,000\n第一句\n\n2\n00:00:01,000 --> 00:00:02,000\n第二句\n",
                )
                return srt_path

            def fake_auto_edit(srt_path: Path, options: PipelineOptions) -> Path:
                optimized_path = srt_path.with_name(f"{srt_path.stem}.optimized.srt")
                _write_text(
                    optimized_path,
                    "1\n00:00:00,000 --> 00:00:01,000\n第一句\n\n2\n00:00:01,000 --> 00:00:02,000\n<<REMOVE>> 第二句\n",
                )
                optimized_path.with_suffix(".step1.json").write_text(
                    json.dumps(
                        {
                            "lines": [
                                {
                                    "line_id": 1,
                                    "start": 0.0,
                                    "end": 1.0,
                                    "original_text": "第一句",
                                    "optimized_text": "第一句",
                                    "ai_suggest_remove": False,
                                    "user_final_remove": False,
                                },
                                {
                                    "line_id": 2,
                                    "start": 1.0,
                                    "end": 2.0,
                                    "original_text": "第二句",
                                    "optimized_text": "第二句",
                                    "ai_suggest_remove": True,
                                    "user_final_remove": True,
                                },
                            ]
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                return optimized_path

            with patch("video_auto_cut.human_loop.runner.run_transcribe", side_effect=fake_transcribe), patch(
                "video_auto_cut.human_loop.runner.run_auto_edit",
                side_effect=fake_auto_edit,
            ):
                state = run_until_human_gate(
                    input_video_path=input_video,
                    output_video_path=output_video,
                    artifact_root=str(artifact_root),
                    options=PipelineOptions(llm_base_url="https://example.com", llm_model="test-model"),
                )

            self.assertEqual(state["status"], STATUS_STEP1_READY)
            self.assertTrue((artifact_root / "step1" / "draft_step1.json").exists())
            self.assertTrue((artifact_root / "step1" / "draft_step1.srt").exists())

    def test_advance_workflow_auto_approves_step1_and_runs_step2(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_video = root / "demo.mp4"
            input_video.write_bytes(b"video")
            artifact_root = root / "artifacts"
            output_video = root / "output.mp4"

            (artifact_root / "step1").mkdir(parents=True, exist_ok=True)
            (artifact_root / "state.json").write_text(
                json.dumps(
                    {
                        "status": "STEP1_READY",
                        "input_video_path": str(input_video),
                        "output_video_path": str(output_video),
                        "step1_confirmed": False,
                        "step2_confirmed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            draft_step1 = artifact_root / "step1" / "draft_step1.json"
            draft_step1.write_text(
                json.dumps(
                    {
                        "lines": [
                            {
                                "line_id": 1,
                                "start": 0.0,
                                "end": 1.0,
                                "original_text": "第一句",
                                "optimized_text": "第一句",
                                "ai_suggest_remove": False,
                                "user_final_remove": False,
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            def fake_topic_segmentation(
                optimized_srt_path: Path,
                cut_srt_output_path: Path,
                topics_output_path: Path,
                options: PipelineOptions,
            ) -> Path:
                _write_text(cut_srt_output_path, "1\n00:00:00,000 --> 00:00:01,000\n第一句\n")
                topics_output_path.write_text(
                    json.dumps(
                        {
                            "topics": [
                                {
                                    "chapter_id": 1,
                                    "title": "开场",
                                    "start": 0.0,
                                    "end": 1.0,
                                    "line_ids": [1],
                                }
                            ]
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                return topics_output_path

            with patch(
                "video_auto_cut.human_loop.runner.run_topic_segmentation_from_optimized_srt",
                side_effect=fake_topic_segmentation,
            ):
                state = advance_workflow(
                    input_video_path=input_video,
                    output_video_path=output_video,
                    artifact_root=str(artifact_root),
                    options=PipelineOptions(llm_base_url="https://example.com", llm_model="test-model"),
                    encoding="utf-8",
                )

            self.assertEqual(state["status"], STATUS_STEP2_READY)
            self.assertTrue((artifact_root / "step1" / "final_step1.json").exists())
            self.assertTrue((artifact_root / "step2" / "draft_topics.json").exists())

    def test_confirmed_step1_resumes_to_step2_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_video = root / "demo.mp4"
            input_video.write_bytes(b"video")
            artifact_root = root / "artifacts"
            output_video = root / "output.mp4"

            draft_step1 = artifact_root / "step1" / "draft_step1.json"
            draft_step1.parent.mkdir(parents=True, exist_ok=True)
            draft_step1.write_text(
                json.dumps(
                    {
                        "lines": [
                            {
                                "line_id": 1,
                                "start": 0.0,
                                "end": 1.0,
                                "original_text": "第一句",
                                "optimized_text": "第一句",
                                "ai_suggest_remove": False,
                                "user_final_remove": False,
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            approve_step1(
                input_video_path=input_video,
                artifact_root=str(artifact_root),
                review_json_path=draft_step1,
                encoding="utf-8",
            )

            def fake_topic_segmentation(
                optimized_srt_path: Path,
                cut_srt_output_path: Path,
                topics_output_path: Path,
                options: PipelineOptions,
            ) -> Path:
                _write_text(cut_srt_output_path, "1\n00:00:00,000 --> 00:00:01,000\n第一句\n")
                topics_output_path.write_text(
                    json.dumps(
                        {
                            "topics": [
                                {
                                    "chapter_id": 1,
                                    "title": "开场",
                                    "start": 0.0,
                                    "end": 1.0,
                                    "line_ids": [1],
                                }
                            ]
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                return topics_output_path

            with patch(
                "video_auto_cut.human_loop.runner.run_topic_segmentation_from_optimized_srt",
                side_effect=fake_topic_segmentation,
            ):
                state = run_until_human_gate(
                    input_video_path=input_video,
                    output_video_path=output_video,
                    artifact_root=str(artifact_root),
                    options=PipelineOptions(llm_base_url="https://example.com", llm_model="test-model"),
                )

            self.assertEqual(load_state := state["status"], STATUS_STEP2_READY)
            self.assertEqual(
                approve_step1(
                    input_video_path=input_video,
                    artifact_root=str(artifact_root),
                    review_json_path=draft_step1,
                    encoding="utf-8",
                )["status"],
                STATUS_STEP1_CONFIRMED,
            )
            self.assertTrue((artifact_root / "step2" / "draft_topics.json").exists())


if __name__ == "__main__":
    unittest.main()
