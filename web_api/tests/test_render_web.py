from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_api.services.render_web import _resolve_dimensions, build_web_render_config


class RenderWebConfigTest(unittest.TestCase):
    def test_resolve_dimensions_rejects_non_positive_values_with_user_facing_message(self) -> None:
        with self.assertRaisesRegex(ValueError, "视频分辨率无效，请重新选择源文件后重试"):
            _resolve_dimensions(0, 0)

    @patch("web_api.services.render_web.list_final_test_chapters")
    @patch("web_api.services.render_web.build_cut_srt_from_optimized_srt")
    @patch("web_api.services.render_web.ensure_job_dirs")
    @patch("web_api.services.render_web.get_settings")
    @patch("web_api.services.render_web.get_job_files")
    def test_build_web_render_config_keeps_original_titles(
        self,
        mock_get_job_files,
        mock_get_settings,
        mock_ensure_job_dirs,
        mock_build_cut_srt,
        mock_list_final_test_chapters,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            render_dir = Path(temp_dir)
            mock_get_job_files.return_value = {"final_test_srt_path": render_dir / "final_test.srt"}
            mock_get_settings.return_value = type("Settings", (), {"cut_merge_gap": 0.0})()
            mock_ensure_job_dirs.return_value = {"render": render_dir}
            mock_build_cut_srt.return_value = {
                "captions": [
                    {"index": 1, "start": 0.0, "end": 8.0, "text": "讲创作者在节奏与效率之间失衡"},
                    {"index": 2, "start": 8.0, "end": 15.0, "text": "讲 AI 缩短协作工作"},
                    {"index": 3, "start": 15.0, "end": 22.0, "text": "讲持续输出与真实感受"},
                    {"index": 4, "start": 22.0, "end": 80.0, "text": "讲落回每天可执行流程"},
                ],
                "segments": [
                    {"start": 0.0, "end": 8.0},
                    {"start": 8.0, "end": 15.0},
                    {"start": 15.0, "end": 22.0},
                    {"start": 22.0, "end": 80.0},
                ],
            }
            mock_list_final_test_chapters.return_value = [
                {"title": "第一部分：为什么短视频创作者总在节奏与效率之间反复失衡", "start": 0.0, "end": 8.0},
                {"title": "第二部分：如何用AI把繁琐重复的协作工作真正缩短到可接受范围", "start": 8.0, "end": 15.0},
                {"title": "第三部分：怎样在持续输出时保留真实感受而不是机械生产内容", "start": 15.0, "end": 22.0},
                {"title": "第四部分：最后把这套方法落回每天都能执行的创作流程", "start": 22.0, "end": 80.0},
            ]

            config = build_web_render_config(
                "job-render-test",
                width=1080,
                height=1920,
                fps=30.0,
                duration_sec=80.0,
            )

        self.assertEqual(
            [item["title"] for item in config["input_props"]["topics"]],
            [
                "第一部分：为什么短视频创作者总在节奏与效率之间反复失衡",
                "第二部分：如何用AI把繁琐重复的协作工作真正缩短到可接受范围",
                "第三部分：怎样在持续输出时保留真实感受而不是机械生产内容",
                "第四部分：最后把这套方法落回每天都能执行的创作流程",
            ],
        )

    @patch("web_api.services.render_web.list_final_test_chapters")
    @patch("web_api.services.render_web.build_cut_srt_from_optimized_srt")
    @patch("web_api.services.render_web.ensure_job_dirs")
    @patch("web_api.services.render_web.get_settings")
    @patch("web_api.services.render_web.get_job_files")
    def test_build_web_render_config_remaps_topics_to_cut_timeline(
        self,
        mock_get_job_files,
        mock_get_settings,
        mock_ensure_job_dirs,
        mock_build_cut_srt,
        mock_list_final_test_chapters,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            render_dir = Path(temp_dir)
            mock_get_job_files.return_value = {"final_test_srt_path": render_dir / "final_test.srt"}
            mock_get_settings.return_value = type("Settings", (), {"cut_merge_gap": 0.0})()
            mock_ensure_job_dirs.return_value = {"render": render_dir}
            mock_build_cut_srt.return_value = {
                "captions": [
                    {"index": 1, "start": 0.0, "end": 4.0, "text": "第一章"},
                    {"index": 2, "start": 4.0, "end": 7.0, "text": "第二章前半"},
                    {"index": 3, "start": 7.0, "end": 10.0, "text": "第二章后半"},
                ],
                "segments": [
                    {"start": 10.0, "end": 14.0},
                    {"start": 20.0, "end": 23.0},
                    {"start": 30.0, "end": 33.0},
                ],
            }
            mock_list_final_test_chapters.return_value = [
                {"title": "开场", "start": 10.0, "end": 14.0},
                {"title": "展开", "start": 20.0, "end": 33.0},
            ]

            config = build_web_render_config(
                "job-render-remap-test",
                width=1080,
                height=1920,
                fps=30.0,
                duration_sec=33.0,
            )

        self.assertEqual(
            config["input_props"]["topics"],
            [
                {"title": "开场", "start": 0.0, "end": 4.0},
                {"title": "展开", "start": 4.0, "end": 10.0},
            ],
        )


if __name__ == "__main__":
    unittest.main()
