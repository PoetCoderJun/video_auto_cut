from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_auto_cut.editing.chapter_domain import (
    build_document_revision,
    canonicalize_test_chapters,
)
from video_auto_cut.pi_agent_runner import TestPiArtifacts
from web_api.job_file_repository import list_test_chapters, list_test_lines
from web_api.services.test import confirm_test, generate_test_chapters


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
            output_path = Path(tmpdir) / "chapters_draft.txt"

            with (
                patch("web_api.services.test.build_pipeline_options_from_settings"),
                patch(
                    "web_api.services.test.build_llm_config",
                    return_value={"base_url": "http://x", "model": "test-model", "api_key": "k"},
                ),
                patch(
                    "web_api.services.test.run_test_pi",
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

    def test_generate_test_chapters_limits_landscape_jobs_to_six(self) -> None:
        kept_lines = [
            {
                "line_id": index,
                "start": float((index - 1) * 3),
                "end": float(index * 3),
                "original_text": f"第{index}句内容比较完整",
                "optimized_text": f"第{index}句内容比较完整",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            }
            for index in range(1, 19)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "chapters_draft.txt"
            video_path = Path(tmpdir) / "source.mp4"
            video_path.write_bytes(b"fake")
            with (
                patch("web_api.services.test.build_pipeline_options_from_settings"),
                patch(
                    "web_api.services.test.build_llm_config",
                    return_value={"base_url": "http://x", "model": "test-model", "api_key": "k"},
                ),
                patch(
                    "web_api.services.test.subprocess.run",
                    return_value=subprocess.CompletedProcess(
                        args=["ffprobe"],
                        returncode=0,
                        stdout='{"streams":[{"width":1920,"height":1080}]}',
                        stderr="",
                    ),
                ),
                patch(
                    "web_api.services.test.run_test_pi",
                    return_value=TestPiArtifacts(
                        task="chapter",
                        chapters=[
                            {"chapter_id": 1, "title": "开场", "block_range": "1-3"},
                            {"chapter_id": 2, "title": "重点一", "block_range": "4-6"},
                            {"chapter_id": 3, "title": "重点二", "block_range": "7-9"},
                            {"chapter_id": 4, "title": "重点三", "block_range": "10-12"},
                            {"chapter_id": 5, "title": "重点四", "block_range": "13-14"},
                            {"chapter_id": 6, "title": "重点五", "block_range": "15-16"},
                            {"chapter_id": 7, "title": "收尾", "block_range": "17-18"},
                        ],
                    ),
                ) as mock_runner,
            ):
                chapters = generate_test_chapters(
                    output_path=output_path,
                    kept_lines=kept_lines,
                    video_path=video_path,
                )

        request = mock_runner.call_args.args[0]
        self.assertEqual(request.max_chapters, 6)
        self.assertEqual(request.chapter_policy_hint, "横屏视频章节约束")
        self.assertEqual(len(chapters), 6)
        self.assertEqual([chapter["block_range"] for chapter in chapters], ["1-3", "4-6", "7-9", "10-12", "13-16", "17-18"])

    def test_generate_test_chapters_limits_portrait_jobs_to_four(self) -> None:
        kept_lines = [
            {
                "line_id": index,
                "start": float((index - 1) * 3),
                "end": float(index * 3),
                "original_text": f"第{index}句内容比较完整",
                "optimized_text": f"第{index}句内容比较完整",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            }
            for index in range(1, 19)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "chapters_draft.txt"
            video_path = Path(tmpdir) / "source.mp4"
            video_path.write_bytes(b"fake")
            with (
                patch("web_api.services.test.build_pipeline_options_from_settings"),
                patch(
                    "web_api.services.test.build_llm_config",
                    return_value={"base_url": "http://x", "model": "test-model", "api_key": "k"},
                ),
                patch(
                    "web_api.services.test.subprocess.run",
                    return_value=subprocess.CompletedProcess(
                        args=["ffprobe"],
                        returncode=0,
                        stdout='{"streams":[{"width":1080,"height":1920}]}',
                        stderr="",
                    ),
                ),
                patch(
                    "web_api.services.test.run_test_pi",
                    return_value=TestPiArtifacts(
                        task="chapter",
                        chapters=[
                            {"chapter_id": 1, "title": "开场", "block_range": "1-4"},
                            {"chapter_id": 2, "title": "重点一", "block_range": "5-8"},
                            {"chapter_id": 3, "title": "重点二", "block_range": "9-12"},
                            {"chapter_id": 4, "title": "重点三", "block_range": "13-14"},
                            {"chapter_id": 5, "title": "重点四", "block_range": "15-18"},
                        ],
                    ),
                ) as mock_runner,
            ):
                chapters = generate_test_chapters(
                    output_path=output_path,
                    kept_lines=kept_lines,
                    video_path=video_path,
                )

        request = mock_runner.call_args.args[0]
        self.assertEqual(request.max_chapters, 4)
        self.assertEqual(request.chapter_policy_hint, "竖屏视频章节约束")
        self.assertEqual([chapter["block_range"] for chapter in chapters], ["1-4", "5-8", "9-14", "15-18"])

    def test_generate_test_chapters_merges_insubstantial_single_block_bridge(self) -> None:
        kept_lines = [
            {
                "line_id": 1,
                "start": 0.0,
                "end": 4.0,
                "original_text": "前面先交代完整背景",
                "optimized_text": "前面先交代完整背景",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
            {
                "line_id": 2,
                "start": 4.0,
                "end": 8.0,
                "original_text": "继续把背景说明完整",
                "optimized_text": "继续把背景说明完整",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
            {
                "line_id": 3,
                "start": 8.0,
                "end": 12.0,
                "original_text": "最后补一句关键结论",
                "optimized_text": "最后补一句关键结论",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
            {
                "line_id": 4,
                "start": 12.0,
                "end": 14.0,
                "original_text": "嗯",
                "optimized_text": "嗯",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
            {
                "line_id": 5,
                "start": 14.0,
                "end": 18.0,
                "original_text": "然后开始第二段完整方法",
                "optimized_text": "然后开始第二段完整方法",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
            {
                "line_id": 6,
                "start": 18.0,
                "end": 22.0,
                "original_text": "把第二段方法继续展开",
                "optimized_text": "把第二段方法继续展开",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
            {
                "line_id": 7,
                "start": 22.0,
                "end": 26.0,
                "original_text": "最后把方法收住",
                "optimized_text": "最后把方法收住",
                "ai_suggest_remove": False,
                "user_final_remove": False,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "chapters_draft.txt"
            with (
                patch("web_api.services.test.build_pipeline_options_from_settings"),
                patch(
                    "web_api.services.test.build_llm_config",
                    return_value={"base_url": "http://x", "model": "test-model", "api_key": "k"},
                ),
                patch(
                    "web_api.services.test.run_test_pi",
                    return_value=TestPiArtifacts(
                        task="chapter",
                        chapters=[
                            {"chapter_id": 1, "title": "前情", "block_range": "1-3"},
                            {"chapter_id": 2, "title": "过渡", "block_range": "4"},
                            {"chapter_id": 3, "title": "方法", "block_range": "5-7"},
                        ],
                    ),
                ),
            ):
                chapters = generate_test_chapters(
                    output_path=output_path,
                    kept_lines=kept_lines,
                )

        self.assertEqual([chapter["block_range"] for chapter in chapters], ["1-4", "5-7"])

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

    def test_list_test_lines_reads_text_draft(self) -> None:
        job_id = "job-text-only"
        with tempfile.TemporaryDirectory() as tmpdir:
            job_root = Path(tmpdir) / job_id / "test"
            job_root.mkdir(parents=True, exist_ok=True)
            (job_root / "lines_draft.txt").write_text("【00:00:00.000-00:00:01.000】TXT 第一行\n", encoding="utf-8")

            with patch("web_api.job_file_repository.job_dir", side_effect=lambda current_job_id: Path(tmpdir) / current_job_id):
                self.assertEqual(
                    list_test_lines(job_id),
                    [
                        {
                            "line_id": 1,
                            "start": 0.0,
                            "end": 1.0,
                            "original_text": "TXT 第一行",
                            "optimized_text": "TXT 第一行",
                            "ai_suggest_remove": False,
                            "user_final_remove": False,
                        }
                    ],
                )

    def test_list_test_lines_returns_empty_when_draft_is_missing(self) -> None:
        job_id = "job-missing-lines"

        with tempfile.TemporaryDirectory() as tmpdir:
            job_root = Path(tmpdir) / job_id / "test"
            job_root.mkdir(parents=True, exist_ok=True)

            with patch("web_api.job_file_repository.job_dir", side_effect=lambda current_job_id: Path(tmpdir) / current_job_id):
                self.assertEqual(list_test_lines(job_id), [])

    def test_list_test_chapters_reads_text_draft(self) -> None:
        job_id = "job-text-chapters"

        with tempfile.TemporaryDirectory() as tmpdir:
            job_root = Path(tmpdir) / job_id / "test"
            job_root.mkdir(parents=True, exist_ok=True)
            (job_root / "lines_draft.txt").write_text(
                "【00:00:00.000-00:00:01.000】第一句\n【00:00:01.000-00:00:02.500】第二句\n",
                encoding="utf-8",
            )
            (job_root / "chapters_draft.txt").write_text("【1-2】确认稿\n", encoding="utf-8")

            with patch("web_api.job_file_repository.job_dir", side_effect=lambda current_job_id: Path(tmpdir) / current_job_id):
                self.assertEqual(
                    list_test_chapters(job_id),
                    [{"chapter_id": 1, "title": "确认稿", "start": 0.0, "end": 2.5, "block_range": "1-2"}],
                )


if __name__ == "__main__":
    unittest.main()
