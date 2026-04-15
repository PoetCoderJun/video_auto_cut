from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_auto_cut.editing.chapter_domain import (
    build_document_revision,
    canonicalize_step1_chapters,
)
from video_auto_cut.pi_agent_runner import Step1PiArtifacts
from web_api.services.step1 import confirm_step1
from web_api.services.step2 import generate_step1_chapters


class Step1ChaptersTests(unittest.TestCase):
    def test_generate_step1_chapters_uses_canonical_pi_chapter_path(self) -> None:
        kept_lines = [
            {
                "line_id": index,
                "start": float(index - 1),
                "end": float(index),
                "original_text": f"第{index}句",
                "optimized_text": f"第{index}句",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            }
            for index in range(1, 7)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "chapters_draft.json"
            source_srt = Path(tmpdir) / "final_step1.srt"
            source_srt.write_text("placeholder", encoding="utf-8")

            with (
                patch("web_api.services.step2.build_pipeline_options"),
                patch(
                    "web_api.services.step2.build_llm_config",
                    return_value={"base_url": "http://x", "model": "test-model", "api_key": "k"},
                ),
                patch(
                    "web_api.services.step2.run_step1_pi",
                    return_value=Step1PiArtifacts(
                        task="chapter",
                        chapters=[
                            {"chapter_id": 1, "title": "开场", "start": 0.0, "end": 3.0, "block_range": "1-3"},
                            {"chapter_id": 2, "title": "结尾", "start": 3.0, "end": 6.0, "block_range": "4-6"},
                        ],
                    ),
                ) as mock_runner,
            ):
                chapters = generate_step1_chapters(
                    source_srt=source_srt,
                    output_path=output_path,
                    kept_lines=kept_lines,
                )

        self.assertEqual(
            chapters,
            [
                {
                    "chapter_id": 1,
                    "title": "开场",
                    "start": 0.0,
                    "end": 3.0,
                    "block_range": "1-3",
                },
                {
                    "chapter_id": 2,
                    "title": "结尾",
                    "start": 3.0,
                    "end": 6.0,
                    "block_range": "4-6",
                },
            ],
        )
        mock_runner.assert_called_once()

    def test_canonicalize_step1_chapters_recomputes_timings_from_block_range(self) -> None:
        kept_lines = [
            {
                "line_id": index,
                "start": float(index - 1) * 1.5,
                "end": float(index) * 1.5,
                "original_text": f"第{index}句",
                "optimized_text": f"第{index}句",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            }
            for index in range(1, 5)
        ]

        chapters = canonicalize_step1_chapters(
            [
                {"chapter_id": 10, "title": "前半", "block_range": "1-2"},
                {"chapter_id": 20, "title": "后半", "block_range": "3-4"},
            ],
            kept_lines,
        )

        self.assertEqual(
            chapters,
            [
                {"chapter_id": 10, "title": "前半", "start": 0.0, "end": 3.0, "block_range": "1-2"},
                {"chapter_id": 20, "title": "后半", "start": 3.0, "end": 6.0, "block_range": "3-4"},
            ],
        )

    def test_confirm_step1_rejects_revision_conflict(self) -> None:
        lines = [
            {
                "line_id": 1,
                "start": 0.0,
                "end": 1.0,
                "original_text": "你好",
                "optimized_text": "你好",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            }
        ]
        chapters = [{"chapter_id": 1, "title": "开场", "start": 0.0, "end": 1.0, "block_range": "1"}]

        with (
            patch("web_api.services.step1.list_step1_lines", return_value=lines),
            patch("web_api.services.step1.list_step1_chapters", return_value=chapters),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                confirm_step1(
                    "job-1",
                    [{"line_id": 1, "optimized_text": "你好啊", "user_final_remove": False}],
                    [{"chapter_id": 1, "title": "开场", "block_range": "1"}],
                    expected_revision="stale-revision",
                )

        self.assertEqual(str(ctx.exception), "step1 document revision conflict")

    def test_confirm_step1_returns_normalized_revision_and_chapters(self) -> None:
        lines = [
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
                "end": 2.5,
                "original_text": "第二句",
                "optimized_text": "第二句",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
        ]
        existing_chapters = [
            {"chapter_id": 1, "title": "初稿", "start": 0.0, "end": 2.5, "block_range": "1-2"}
        ]
        expected_revision = build_document_revision(lines, existing_chapters)

        with tempfile.TemporaryDirectory() as tmpdir:
            step1_dir = Path(tmpdir) / "step1"
            step1_dir.mkdir(parents=True, exist_ok=True)
            with (
                patch("web_api.services.step1.list_step1_lines", return_value=lines),
                patch("web_api.services.step1.list_step1_chapters", return_value=existing_chapters),
                patch("web_api.services.step1.ensure_job_dirs", return_value={"step1": step1_dir}),
                patch("web_api.services.step1.replace_step1_lines"),
                patch("web_api.services.step1.replace_step1_chapters"),
                patch("web_api.services.step1.upsert_job_files"),
                patch("web_api.services.step1.update_job"),
            ):
                result = confirm_step1(
                    "job-1",
                    [
                        {"line_id": 1, "optimized_text": "第一句", "user_final_remove": False},
                        {"line_id": 2, "optimized_text": "第二句-编辑后", "user_final_remove": False},
                    ],
                    [{"chapter_id": 9, "title": "确认稿", "block_range": "1-2"}],
                    expected_revision=expected_revision,
                )

        self.assertEqual(
            result["chapters"],
            [
                {
                    "chapter_id": 9,
                    "title": "确认稿",
                    "start": 0.0,
                    "end": 2.5,
                    "block_range": "1-2",
                }
            ],
        )
        self.assertTrue(result["document_revision"])


if __name__ == "__main__":
    unittest.main()
