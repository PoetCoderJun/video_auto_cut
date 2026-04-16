from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_auto_cut.editing.chapter_domain import (
    build_document_revision,
    canonicalize_test_chapters,
)
from video_auto_cut.pi_agent_runner import TestPiArtifacts
from web_api.services.test import confirm_test
from web_api.services.step2 import generate_test_chapters


class TestChaptersTests(unittest.TestCase):
    def test_generate_test_chapters_uses_canonical_pi_chapter_path(self) -> None:
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
            source_srt = Path(tmpdir) / "final_test.srt"
            source_srt.write_text("placeholder", encoding="utf-8")

            with (
                patch("web_api.services.step2.build_pipeline_options"),
                patch(
                    "web_api.services.step2.build_llm_config",
                    return_value={"base_url": "http://x", "model": "test-model", "api_key": "k"},
                ),
                patch(
                    "web_api.services.step2.run_test_pi",
                    return_value=TestPiArtifacts(
                        task="chapter",
                        chapters=[
                            {"chapter_id": 1, "title": "开场", "start": 0.0, "end": 3.0, "block_range": "1-3"},
                            {"chapter_id": 2, "title": "结尾", "start": 3.0, "end": 6.0, "block_range": "4-6"},
                        ],
                    ),
                ) as mock_runner,
            ):
                chapters = generate_test_chapters(
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

    def test_canonicalize_test_chapters_recomputes_timings_from_block_range(self) -> None:
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

        chapters = canonicalize_test_chapters(
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

    def test_confirm_test_rejects_revision_conflict(self) -> None:
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
            patch("web_api.services.test.list_test_lines", return_value=lines),
            patch("web_api.services.test.list_test_chapters", return_value=chapters),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                confirm_test(
                    "job-1",
                    [{"line_id": 1, "optimized_text": "你好啊", "user_final_remove": False}],
                    [{"chapter_id": 1, "title": "开场", "block_range": "1"}],
                    expected_revision="stale-revision",
                )

        self.assertEqual(str(ctx.exception), "test document revision conflict")

    def test_confirm_test_returns_normalized_revision_and_chapters(self) -> None:
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
            test_dir = Path(tmpdir) / "test"
            test_dir.mkdir(parents=True, exist_ok=True)
            with (
                patch("web_api.services.test.list_test_lines", return_value=lines),
                patch("web_api.services.test.list_test_chapters", return_value=existing_chapters),
                patch("web_api.services.test.ensure_job_dirs", return_value={"base": Path(tmpdir), "test": test_dir}),
                patch("web_api.services.test.replace_test_lines"),
                patch("web_api.services.test.replace_test_chapters"),
                patch("web_api.services.test.upsert_job_files"),
                patch("web_api.services.test.update_job"),
            ):
                result = confirm_test(
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

    def test_document_revision_is_stable_for_semantically_equivalent_chapter_input(self) -> None:
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

        canonical_from_minimal = canonicalize_test_chapters(
            [{"chapter_id": 1, "title": "确认稿", "block_range": "1-2"}],
            lines,
        )
        canonical_from_stale_timing = canonicalize_test_chapters(
            [{"chapter_id": 1, "title": "确认稿", "start": 99.0, "end": 100.0, "block_range": "1-2"}],
            lines,
        )

        self.assertEqual(canonical_from_minimal, canonical_from_stale_timing)
        self.assertEqual(
            build_document_revision(lines, canonical_from_minimal),
            build_document_revision(lines, canonical_from_stale_timing),
        )

    def test_canonicalize_test_chapters_does_not_mutate_input_payload(self) -> None:
        lines = [
            {
                "line_id": 2,
                "start": 1.0,
                "end": 2.5,
                "original_text": "第二句",
                "optimized_text": "第二句",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
            {
                "line_id": 1,
                "start": 0.0,
                "end": 1.0,
                "original_text": "第一句",
                "optimized_text": "第一句",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
        ]
        source = [
            {"chapter_id": 10, "title": "前半", "block_range": "1-2"},
        ]
        snapshot = [dict(item) for item in source]

        normalized = canonicalize_test_chapters(source, lines)

        self.assertEqual(source, snapshot)
        self.assertEqual(
            normalized,
            [{"chapter_id": 10, "title": "前半", "start": 0.0, "end": 2.5, "block_range": "1-2"}],
        )


if __name__ == "__main__":
    unittest.main()
