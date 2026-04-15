from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_api.services.render_web import (
    _fit_uniform_progress_font,
    _prepare_render_topics,
    _resolve_dimensions,
    build_web_render_config,
)


class _DummySettings:
    llm_base_url = "https://example.com"
    llm_model = "test-model"
    llm_api_key = "test-key"
    llm_timeout = 30
    llm_temperature = 0.2
    llm_max_tokens = None
    topic_title_max_chars = 6


class RenderWebTopicRewriteTest(unittest.TestCase):
    def test_resolve_dimensions_rejects_non_positive_values_with_user_facing_message(self) -> None:
        with self.assertRaisesRegex(ValueError, "视频分辨率无效，请重新选择源文件后重试"):
            _resolve_dimensions(0, 0)

    def _assert_progress_principles(
        self,
        topics: list[dict[str, object]],
        captions: list[dict[str, object]],
        *,
        width: int = 1080,
        height: int = 1920,
        min_font_size: int = 18,
    ) -> None:
        fit = _fit_uniform_progress_font(
            topics,
            width=width,
            height=height,
            captions=captions,
            segments=[{"start": 0.0, "end": max(float(item["end"]) for item in topics)}],
        )
        self.assertTrue(fit["fits_all"], "expected all progress labels to fit into their segments")
        self.assertGreaterEqual(
            fit["font_size"],
            min_font_size,
            f"expected shared progress label font >= {min_font_size}, got {fit['font_size']}",
        )

    def test_uniform_progress_font_is_driven_by_narrowest_segment(self) -> None:
        topics = [
            {"title": "创作与尝试", "start": 0.0, "end": 19.0},
            {"title": "掌控生活节奏", "start": 19.0, "end": 33.0},
            {"title": "AI高效协作", "start": 33.0, "end": 51.0},
            {"title": "尊重感受前行", "start": 51.0, "end": 81.0},
        ]
        captions = [{"start": 0.0, "end": 81.0, "text": "测试字幕"}]
        segments = [{"start": 0.0, "end": 81.0}]

        fit = _fit_uniform_progress_font(
            topics,
            width=1080,
            height=1920,
            captions=captions,
            segments=segments,
        )

        self.assertTrue(fit["fits_all"])
        self.assertLess(fit["font_size"], fit["base_font_size"])
        self.assertLess(fit["font_size"], math.floor(fit["base_font_size"] * 0.8))

    def test_uniform_progress_font_allows_two_lines_in_portrait(self) -> None:
        topics = [
            {"title": "为什么开头会拖沓", "start": 0.0, "end": 6.0},
            {"title": "怎样保留真实感受", "start": 6.0, "end": 14.0},
            {"title": "最后怎么落地执行", "start": 14.0, "end": 30.0},
        ]
        captions = [{"start": 0.0, "end": 30.0, "text": "测试字幕"}]
        segments = [{"start": 0.0, "end": 30.0}]

        fit = _fit_uniform_progress_font(
            topics,
            width=1080,
            height=1920,
            captions=captions,
            segments=segments,
        )

        self.assertTrue(fit["fits_all"])
        self.assertGreaterEqual(fit["font_size"], 12)
        self.assertEqual(fit["segment_metrics"][0]["max_lines"], 2)

    def test_prepare_render_topics_rewrites_titles_when_uniform_font_would_be_too_small(self) -> None:
        topics = [
            {"title": "创作与尝试", "start": 0.0, "end": 19.0},
            {"title": "掌控生活节奏", "start": 19.0, "end": 33.0},
            {"title": "AI高效协作", "start": 33.0, "end": 51.0},
            {"title": "尊重感受前行", "start": 51.0, "end": 81.0},
        ]
        captions = [
            {"start": 0.0, "end": 19.0, "text": "讲创作和试错"},
            {"start": 19.0, "end": 33.0, "text": "讲如何掌控节奏"},
            {"start": 33.0, "end": 51.0, "text": "讲 AI 协作效率"},
            {"start": 51.0, "end": 81.0, "text": "讲尊重感受继续前进"},
        ]
        segments = [{"start": 0.0, "end": 81.0}]
        settings = _DummySettings()

        original_fit = _fit_uniform_progress_font(
            topics,
            width=1080,
            height=1920,
            captions=captions,
            segments=segments,
        )

        rewritten_topics = _prepare_render_topics(
            topics,
            captions=captions,
            segments=segments,
            width=1080,
            height=1920,
            settings=settings,
            chat_completion_fn=lambda _cfg, _messages: (
                '{"titles":["创作","控节奏","AI协作","尊重前行"]}'
            ),
        )

        rewritten_fit = _fit_uniform_progress_font(
            rewritten_topics,
            width=1080,
            height=1920,
            captions=captions,
            segments=segments,
        )

        self.assertEqual([item["title"] for item in rewritten_topics], ["创作", "控节奏", "AI协作", "尊重前行"])
        self.assertGreater(rewritten_fit["font_size"], original_fit["font_size"])
        self._assert_progress_principles(rewritten_topics, captions)

    def test_prepare_render_topics_keeps_original_titles_after_rejected_rewrite(self) -> None:
        topics = [
            {"title": "开场", "start": 0.0, "end": 7.0},
            {"title": "非常非常长的节奏控制方法论", "start": 7.0, "end": 16.0},
            {"title": "利用AI建立真正高效的协作流程", "start": 16.0, "end": 28.0},
            {"title": "尊重内在感受同时继续向前行动", "start": 28.0, "end": 81.0},
        ]
        captions = [
            {"start": 0.0, "end": 7.0, "text": "讲开场"},
            {"start": 7.0, "end": 16.0, "text": "讲如何控制生活节奏和工作节奏"},
            {"start": 16.0, "end": 28.0, "text": "讲 AI 协作提效方法"},
            {"start": 28.0, "end": 81.0, "text": "讲尊重感受也继续前行"},
        ]
        segments = [{"start": 0.0, "end": 81.0}]
        settings = _DummySettings()
        rewritten_topics = _prepare_render_topics(
            topics,
            captions=captions,
            segments=segments,
            width=1080,
            height=1920,
            settings=settings,
            chat_completion_fn=lambda _cfg, _messages: (
                '{"titles":["开场","控节奏","AI协效","感行并进"]}'
            ),
        )
        self.assertEqual([item["title"] for item in rewritten_topics], [item["title"] for item in topics])

    def test_prepare_render_topics_handles_dense_long_title_case(self) -> None:
        topics = [
            {"title": "第一部分：为什么短视频创作者总在节奏与效率之间反复失衡", "start": 0.0, "end": 8.0},
            {"title": "第二部分：如何用AI把繁琐重复的协作工作真正缩短到可接受范围", "start": 8.0, "end": 15.0},
            {"title": "第三部分：怎样在持续输出时保留真实感受而不是机械生产内容", "start": 15.0, "end": 22.0},
            {"title": "第四部分：最后把这套方法落回每天都能执行的创作流程", "start": 22.0, "end": 80.0},
        ]
        captions = [
            {"start": 0.0, "end": 8.0, "text": "讲创作者在节奏与效率之间失衡"},
            {"start": 8.0, "end": 15.0, "text": "讲 AI 缩短协作工作"},
            {"start": 15.0, "end": 22.0, "text": "讲持续输出与真实感受"},
            {"start": 22.0, "end": 80.0, "text": "讲落回每天可执行流程"},
        ]
        rewritten_topics = _prepare_render_topics(
            topics,
            captions=captions,
            segments=[{"start": 0.0, "end": 80.0}],
            width=1080,
            height=1920,
            settings=_DummySettings(),
            chat_completion_fn=lambda _cfg, _messages: (
                '{"titles":["失衡","减负","真实","落地执行"]}'
            ),
        )

        self.assertEqual([item["title"] for item in rewritten_topics], ["失衡", "减负", "真实", "落地执行"])
        self._assert_progress_principles(rewritten_topics, captions, min_font_size=20)

    def test_prepare_render_topics_handles_six_mixed_topics(self) -> None:
        topics = [
            {"title": "第一段：为什么开头总是拖沓又没重点", "start": 0.0, "end": 6.0},
            {"title": "第二段：怎样用试错把表达慢慢磨出来", "start": 6.0, "end": 12.0},
            {"title": "第三段：把生活节奏重新拉回正轨", "start": 12.0, "end": 20.0},
            {"title": "第四段：利用AI建立更高效的协作方式", "start": 20.0, "end": 35.0},
            {"title": "第五段：持续输出时如何保留真实感", "start": 35.0, "end": 50.0},
            {"title": "第六段：最后回到每天都能执行的流程", "start": 50.0, "end": 90.0},
        ]
        captions = [
            {"start": 0.0, "end": 6.0, "text": "讲开头拖沓没重点"},
            {"start": 6.0, "end": 12.0, "text": "讲试错和打磨表达"},
            {"start": 12.0, "end": 20.0, "text": "讲把生活节奏拉回正轨"},
            {"start": 20.0, "end": 35.0, "text": "讲 AI 协作提效"},
            {"start": 35.0, "end": 50.0, "text": "讲持续输出保留真实感"},
            {"start": 50.0, "end": 90.0, "text": "讲每天可执行流程"},
        ]
        rewritten_topics = _prepare_render_topics(
            topics,
            captions=captions,
            segments=[{"start": 0.0, "end": 90.0}],
            width=1080,
            height=1920,
            settings=_DummySettings(),
            chat_completion_fn=lambda _cfg, _messages: (
                '{"titles":["破题","试错","节奏","AI协作","保真实","落地执行"]}'
            ),
        )

        self.assertEqual(
            [item["title"] for item in rewritten_topics],
            ["破题", "试错", "节奏", "AI协作", "保真实", "落地执行"],
        )
        self._assert_progress_principles(rewritten_topics, captions, min_font_size=20)

    def test_prepare_render_topics_handles_seven_topic_mixed_widths(self) -> None:
        topics = [
            {"title": "为什么开头会拖沓", "start": 0.0, "end": 5.0},
            {"title": "如何快速破题", "start": 5.0, "end": 10.0},
            {"title": "怎么删掉废话", "start": 10.0, "end": 15.0},
            {"title": "AI怎样参与协作", "start": 15.0, "end": 21.0},
            {"title": "怎样保留真实感受", "start": 21.0, "end": 28.0},
            {"title": "如何保持稳定输出", "start": 28.0, "end": 36.0},
            {"title": "最后怎么落地执行", "start": 36.0, "end": 90.0},
        ]
        captions = [
            {"start": 0.0, "end": 5.0, "text": "讲开头拖沓"},
            {"start": 5.0, "end": 10.0, "text": "讲快速破题"},
            {"start": 10.0, "end": 15.0, "text": "讲删废话"},
            {"start": 15.0, "end": 21.0, "text": "讲 AI 协作"},
            {"start": 21.0, "end": 28.0, "text": "讲保留真实感受"},
            {"start": 28.0, "end": 36.0, "text": "讲稳定输出"},
            {"start": 36.0, "end": 90.0, "text": "讲最后落地执行"},
        ]
        rewritten_topics = _prepare_render_topics(
            topics,
            captions=captions,
            segments=[{"start": 0.0, "end": 90.0}],
            width=1080,
            height=1920,
            settings=_DummySettings(),
            chat_completion_fn=lambda _cfg, _messages: (
                '{"titles":["破题","重点","删繁","协作","真实","输出","落地执行"]}'
            ),
        )

        self.assertEqual(
            [item["title"] for item in rewritten_topics],
            ["破题", "重点", "删繁", "协作", "真实", "输出", "落地执行"],
        )
        self._assert_progress_principles(rewritten_topics, captions, min_font_size=17)

    def test_prepare_render_topics_handles_five_topics_with_short_front_segments(self) -> None:
        topics = [
            {"title": "开场为什么总讲不清楚", "start": 0.0, "end": 5.0},
            {"title": "如何立刻进入重点", "start": 5.0, "end": 11.0},
            {"title": "怎样缩短协作链路", "start": 11.0, "end": 18.0},
            {"title": "持续输出时保留感受", "start": 18.0, "end": 28.0},
            {"title": "最后把方法落回日常", "start": 28.0, "end": 90.0},
        ]
        captions = [
            {"start": 0.0, "end": 5.0, "text": "讲开场说不清"},
            {"start": 5.0, "end": 11.0, "text": "讲进入重点"},
            {"start": 11.0, "end": 18.0, "text": "讲缩短协作链路"},
            {"start": 18.0, "end": 28.0, "text": "讲持续输出保留感受"},
            {"start": 28.0, "end": 90.0, "text": "讲方法落回日常"},
        ]
        rewritten_topics = _prepare_render_topics(
            topics,
            captions=captions,
            segments=[{"start": 0.0, "end": 90.0}],
            width=1080,
            height=1920,
            settings=_DummySettings(),
            chat_completion_fn=lambda _cfg, _messages: (
                '{"titles":["破题","重点","提效","保真","落地日常"]}'
            ),
        )

        self.assertEqual(
            [item["title"] for item in rewritten_topics],
            ["破题", "重点", "提效", "保真", "落地日常"],
        )
        self._assert_progress_principles(rewritten_topics, captions, min_font_size=17)

    def test_prepare_render_topics_handles_landscape_initial_case(self) -> None:
        topics = [
            {"title": "创作与尝试", "start": 0.0, "end": 19.0},
            {"title": "掌控生活节奏", "start": 19.0, "end": 33.0},
            {"title": "AI高效协作", "start": 33.0, "end": 51.0},
            {"title": "尊重感受前行", "start": 51.0, "end": 81.0},
        ]
        captions = [
            {"start": 0.0, "end": 19.0, "text": "讲创作与尝试"},
            {"start": 19.0, "end": 33.0, "text": "讲掌控生活节奏"},
            {"start": 33.0, "end": 51.0, "text": "讲 AI 高效协作"},
            {"start": 51.0, "end": 81.0, "text": "讲尊重感受继续前行"},
        ]
        prepared_topics = _prepare_render_topics(
            topics,
            captions=captions,
            segments=[{"start": 0.0, "end": 81.0}],
            width=1920,
            height=1080,
            settings=_DummySettings(),
            chat_completion_fn=lambda _cfg, _messages: (
                '{"titles":["创作尝试","掌控节奏","AI协作","尊重前行"]}'
            ),
        )

        self._assert_progress_principles(prepared_topics, captions, width=1920, height=1080, min_font_size=20)

    def test_prepare_render_topics_handles_landscape_dense_long_titles(self) -> None:
        topics = [
            {"title": "第一部分：为什么短视频创作者总在节奏与效率之间反复失衡", "start": 0.0, "end": 8.0},
            {"title": "第二部分：如何用AI把繁琐重复的协作工作真正缩短到可接受范围", "start": 8.0, "end": 15.0},
            {"title": "第三部分：怎样在持续输出时保留真实感受而不是机械生产内容", "start": 15.0, "end": 22.0},
            {"title": "第四部分：最后把这套方法落回每天都能执行的创作流程", "start": 22.0, "end": 80.0},
        ]
        captions = [
            {"start": 0.0, "end": 8.0, "text": "讲创作者在节奏与效率之间失衡"},
            {"start": 8.0, "end": 15.0, "text": "讲 AI 缩短协作工作"},
            {"start": 15.0, "end": 22.0, "text": "讲持续输出与真实感受"},
            {"start": 22.0, "end": 80.0, "text": "讲落回每天可执行流程"},
        ]
        rewritten_topics = _prepare_render_topics(
            topics,
            captions=captions,
            segments=[{"start": 0.0, "end": 80.0}],
            width=1920,
            height=1080,
            settings=_DummySettings(),
            chat_completion_fn=lambda _cfg, _messages: (
                '{"titles":["失衡","减负","真实","落地执行"]}'
            ),
        )

        self.assertEqual([item["title"] for item in rewritten_topics], ["失衡", "减负", "真实", "落地执行"])
        self._assert_progress_principles(rewritten_topics, captions, width=1920, height=1080, min_font_size=22)

    def test_prepare_render_topics_handles_landscape_seven_topic_case(self) -> None:
        topics = [
            {"title": "为什么开头会拖沓", "start": 0.0, "end": 5.0},
            {"title": "如何快速破题", "start": 5.0, "end": 10.0},
            {"title": "怎么删掉废话", "start": 10.0, "end": 15.0},
            {"title": "AI怎样参与协作", "start": 15.0, "end": 21.0},
            {"title": "怎样保留真实感受", "start": 21.0, "end": 28.0},
            {"title": "如何保持稳定输出", "start": 28.0, "end": 36.0},
            {"title": "最后怎么落地执行", "start": 36.0, "end": 90.0},
        ]
        captions = [
            {"start": 0.0, "end": 5.0, "text": "讲开头拖沓"},
            {"start": 5.0, "end": 10.0, "text": "讲快速破题"},
            {"start": 10.0, "end": 15.0, "text": "讲删废话"},
            {"start": 15.0, "end": 21.0, "text": "讲 AI 协作"},
            {"start": 21.0, "end": 28.0, "text": "讲保留真实感受"},
            {"start": 28.0, "end": 36.0, "text": "讲稳定输出"},
            {"start": 36.0, "end": 90.0, "text": "讲最后落地执行"},
        ]
        rewritten_topics = _prepare_render_topics(
            topics,
            captions=captions,
            segments=[{"start": 0.0, "end": 90.0}],
            width=1920,
            height=1080,
            settings=_DummySettings(),
            chat_completion_fn=lambda _cfg, _messages: (
                '{"titles":["破题","重点","删繁","AI协作","真实感","稳输出","落地执行"]}'
            ),
        )

        self.assertEqual(
            [item["title"] for item in rewritten_topics],
            ["破题", "重点", "删繁", "AI协作", "真实感", "稳输出", "落地执行"],
        )
        self._assert_progress_principles(rewritten_topics, captions, width=1920, height=1080, min_font_size=22)

    @patch("web_api.services.render_web.list_final_step1_chapters")
    @patch("web_api.services.render_web.build_cut_srt_from_optimized_srt")
    @patch("web_api.services.render_web.ensure_job_dirs")
    @patch("web_api.services.render_web.get_settings")
    @patch("web_api.services.render_web.get_job_files")
    def test_build_web_render_config_end_to_end_keeps_user_confirmed_titles(
        self,
        mock_get_job_files,
        mock_get_settings,
        mock_ensure_job_dirs,
        mock_build_cut_srt,
        mock_list_final_step1_chapters,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            render_dir = Path(temp_dir)
            mock_get_job_files.return_value = {"final_step1_srt_path": render_dir / "final_step1.srt"}
            mock_get_settings.return_value = _DummySettings()
            mock_get_settings.return_value.cut_merge_gap = 0.0
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
            mock_list_final_step1_chapters.return_value = [
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
                chat_completion_fn=lambda _cfg, _messages: (
                    '{"titles":["失衡","减负","真实","落地执行"]}'
                ),
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

    @patch("web_api.services.render_web.list_final_step1_chapters")
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
        mock_list_final_step1_chapters,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            render_dir = Path(temp_dir)
            mock_get_job_files.return_value = {"final_step1_srt_path": render_dir / "final_step1.srt"}
            mock_get_settings.return_value = _DummySettings()
            mock_get_settings.return_value.cut_merge_gap = 0.0
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
            mock_list_final_step1_chapters.return_value = [
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
