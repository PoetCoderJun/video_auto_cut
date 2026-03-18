from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_api.constants import JOB_STATUS_STEP2_CONFIRMED, JOB_STATUS_STEP2_READY
from web_api.services.step2 import confirm_step2, run_step2


class Step2AutoConfirmTest(unittest.TestCase):
    def test_run_step2_leaves_generated_chapters_waiting_for_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            step2_dir = tmp_path / "step2"
            step2_dir.mkdir(parents=True, exist_ok=True)
            source_srt = tmp_path / "final_step1.srt"
            source_srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n你好\n", encoding="utf-8")

            def fake_topic_segmentation(**kwargs: object) -> None:
                output = Path(kwargs["topics_output_path"])
                output.write_text(
                    """
{
  "topics": [
    {
      "title": "开场",
      "start": 0.0,
      "end": 1.0,
      "block_range": "1"
    }
  ]
}
""".strip(),
                    encoding="utf-8",
                )

            with (
                patch(
                    "web_api.services.step2.get_job_files",
                    return_value={"final_step1_srt_path": str(source_srt)},
                ),
                patch(
                    "web_api.services.step2.ensure_job_dirs",
                    return_value={"step2": step2_dir},
                ),
                patch(
                    "web_api.services.step2.run_topic_segmentation_from_optimized_srt",
                    side_effect=fake_topic_segmentation,
                ),
                patch(
                    "web_api.services.step2.list_step1_lines",
                    return_value=[
                        {
                            "line_id": 1,
                            "start": 0.0,
                            "end": 1.0,
                            "original_text": "你好",
                            "optimized_text": "你好",
                            "ai_suggest_remove": False,
                            "user_final_remove": False,
                        }
                    ],
                ),
                patch("web_api.services.step2.build_pipeline_options"),
                patch("web_api.services.step2.replace_step2_chapters"),
                patch("web_api.services.step2.upsert_job_files"),
                patch("web_api.services.step2.update_job") as mock_update_job,
            ):
                run_step2("job-123")

        statuses = [call.kwargs.get("status") for call in mock_update_job.call_args_list]
        self.assertIn(JOB_STATUS_STEP2_READY, statuses)
        self.assertNotIn(JOB_STATUS_STEP2_CONFIRMED, statuses)
        self.assertEqual(statuses[-1], JOB_STATUS_STEP2_READY)

    def test_run_step2_accepts_segment_range_payload_and_saves_block_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            step2_dir = tmp_path / "step2"
            step2_dir.mkdir(parents=True, exist_ok=True)
            source_srt = tmp_path / "final_step1.srt"
            source_srt.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n第一句\n\n"
                "2\n00:00:01,000 --> 00:00:02,000\n第二句\n\n"
                "3\n00:00:02,000 --> 00:00:03,000\n第三句\n\n"
                "4\n00:00:03,000 --> 00:00:04,000\n第四句\n\n"
                "5\n00:00:04,000 --> 00:00:05,000\n第五句\n\n"
                "6\n00:00:05,000 --> 00:00:06,000\n第六句\n",
                encoding="utf-8",
            )

            def fake_topic_segmentation(**kwargs: object) -> None:
                output = Path(kwargs["topics_output_path"])
                output.write_text(
                    """
{
  "topics": [
    {
      "title": "开场",
      "start": 0.0,
      "end": 3.0,
      "segment_range": "1-3"
    },
    {
      "title": "结尾",
      "start": 3.0,
      "end": 6.0,
      "start_segment_id": 4,
      "end_segment_id": 6
    }
  ]
}
""".strip(),
                    encoding="utf-8",
                )

            with (
                patch(
                    "web_api.services.step2.get_job_files",
                    return_value={"final_step1_srt_path": str(source_srt)},
                ),
                patch(
                    "web_api.services.step2.ensure_job_dirs",
                    return_value={"step2": step2_dir},
                ),
                patch(
                    "web_api.services.step2.run_topic_segmentation_from_optimized_srt",
                    side_effect=fake_topic_segmentation,
                ),
                patch(
                    "web_api.services.step2.list_step1_lines",
                    return_value=[
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
                            "ai_suggest_remove": False,
                            "user_final_remove": False,
                        },
                        {
                            "line_id": 3,
                            "start": 2.0,
                            "end": 3.0,
                            "original_text": "第三句",
                            "optimized_text": "第三句",
                            "ai_suggest_remove": False,
                            "user_final_remove": False,
                        },
                        {
                            "line_id": 4,
                            "start": 3.0,
                            "end": 4.0,
                            "original_text": "第四句",
                            "optimized_text": "第四句",
                            "ai_suggest_remove": False,
                            "user_final_remove": False,
                        },
                        {
                            "line_id": 5,
                            "start": 4.0,
                            "end": 5.0,
                            "original_text": "第五句",
                            "optimized_text": "第五句",
                            "ai_suggest_remove": False,
                            "user_final_remove": False,
                        },
                        {
                            "line_id": 6,
                            "start": 5.0,
                            "end": 6.0,
                            "original_text": "第六句",
                            "optimized_text": "第六句",
                            "ai_suggest_remove": False,
                            "user_final_remove": False,
                        },
                    ],
                ),
                patch("web_api.services.step2.build_pipeline_options"),
                patch("web_api.services.step2.upsert_job_files"),
                patch("web_api.services.step2.update_job"),
                patch("web_api.services.step2.replace_step2_chapters") as mock_replace_step2_chapters,
            ):
                run_step2("job-123")

        saved_chapters = mock_replace_step2_chapters.call_args.args[1]
        self.assertEqual(
            saved_chapters,
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

    def test_run_step2_allows_generated_short_chapter_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            step2_dir = tmp_path / "step2"
            step2_dir.mkdir(parents=True, exist_ok=True)
            source_srt = tmp_path / "final_step1.srt"
            source_srt.write_text(
                "1\n00:00:00,000 --> 00:00:01,000\n第一句\n\n"
                "2\n00:00:01,000 --> 00:00:02,000\n第二句\n\n"
                "3\n00:00:02,000 --> 00:00:03,000\n第三句\n\n"
                "4\n00:00:03,000 --> 00:00:04,000\n第四句\n\n"
                "5\n00:00:04,000 --> 00:00:05,000\n第五句\n",
                encoding="utf-8",
            )

            def fake_topic_segmentation(**kwargs: object) -> None:
                output = Path(kwargs["topics_output_path"])
                output.write_text(
                    """
{
  "topics": [
    {
      "title": "开头动作",
      "start": 0.0,
      "end": 2.0,
      "block_range": "1-2"
    },
    {
      "title": "后续动作",
      "start": 2.0,
      "end": 5.0,
      "block_range": "3-5"
    }
  ]
}
""".strip(),
                    encoding="utf-8",
                )

            with (
                patch(
                    "web_api.services.step2.get_job_files",
                    return_value={"final_step1_srt_path": str(source_srt)},
                ),
                patch(
                    "web_api.services.step2.ensure_job_dirs",
                    return_value={"step2": step2_dir},
                ),
                patch(
                    "web_api.services.step2.run_topic_segmentation_from_optimized_srt",
                    side_effect=fake_topic_segmentation,
                ),
                patch(
                    "web_api.services.step2.list_step1_lines",
                    return_value=[
                        {
                            "line_id": index,
                            "start": float(index - 1),
                            "end": float(index),
                            "original_text": f"第{index}句",
                            "optimized_text": f"第{index}句",
                            "ai_suggest_remove": False,
                            "user_final_remove": False,
                        }
                        for index in range(1, 6)
                    ],
                ),
                patch("web_api.services.step2.build_pipeline_options"),
                patch("web_api.services.step2.upsert_job_files"),
                patch("web_api.services.step2.update_job"),
                patch("web_api.services.step2.replace_step2_chapters") as mock_replace_step2_chapters,
            ):
                run_step2("job-123")

        saved_chapters = mock_replace_step2_chapters.call_args.args[1]
        self.assertEqual([chapter["block_range"] for chapter in saved_chapters], ["1-2", "3-5"])

    def test_confirm_step2_allows_unchanged_generated_short_chapter_ranges(self) -> None:
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
            for index in range(1, 6)
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            step2_dir = Path(tmpdir) / "step2"
            step2_dir.mkdir(parents=True, exist_ok=True)
            with (
                patch("web_api.services.step2.list_step1_lines", return_value=kept_lines),
                patch(
                    "web_api.services.step2.list_step2_chapters",
                    return_value=[
                        {"chapter_id": 1, "title": "开头动作", "block_range": "1-2"},
                        {"chapter_id": 2, "title": "后续动作", "block_range": "3-5"},
                    ],
                ),
                patch("web_api.services.step2.ensure_job_dirs", return_value={"step2": step2_dir}),
                patch("web_api.services.step2.replace_step2_chapters"),
                patch("web_api.services.step2.upsert_job_files"),
                patch("web_api.services.step2.update_job"),
            ):
                chapters = confirm_step2(
                    "job-123",
                    [
                        {
                            "chapter_id": 1,
                            "title": "新标题",
                            "block_range": "1-2",
                        },
                        {
                            "chapter_id": 2,
                            "title": "正常",
                            "block_range": "3-5",
                        },
                    ],
                )

        self.assertEqual([chapter["block_range"] for chapter in chapters], ["1-2", "3-5"])

    def test_confirm_step2_allows_chapter_with_fewer_than_three_lines(self) -> None:
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
            step2_dir = Path(tmpdir) / "step2"
            step2_dir.mkdir(parents=True, exist_ok=True)
            with (
                patch("web_api.services.step2.list_step1_lines", return_value=kept_lines),
                patch("web_api.services.step2.ensure_job_dirs", return_value={"step2": step2_dir}),
                patch("web_api.services.step2.replace_step2_chapters"),
                patch("web_api.services.step2.upsert_job_files"),
                patch("web_api.services.step2.update_job"),
            ):
                chapters = confirm_step2(
                    "job-123",
                    [
                        {
                            "chapter_id": 1,
                            "title": "太短",
                            "block_range": "1-2",
                        },
                        {
                            "chapter_id": 2,
                            "title": "正常",
                            "block_range": "3-6",
                        },
                    ],
                )

        self.assertEqual([chapter["block_range"] for chapter in chapters], ["1-2", "3-6"])


if __name__ == "__main__":
    unittest.main()
