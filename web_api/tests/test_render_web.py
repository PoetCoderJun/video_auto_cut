from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import srt

from video_auto_cut.asr.word_timing_sidecar import build_sidecar_from_dashscope_payload, write_sidecar
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

    @patch("web_api.services.render_web.list_final_test_chapters")
    @patch("web_api.services.render_web.build_cut_srt_from_optimized_srt")
    @patch("web_api.services.render_web.ensure_job_dirs")
    @patch("web_api.services.render_web.get_settings")
    @patch("web_api.services.render_web.get_job_files")
    @patch("web_api.services.render_web.attach_llm_labels_to_captions")
    @patch("web_api.services.render_web.attach_remapped_tokens_to_captions")
    def test_build_web_render_config_applies_caption_labels_after_token_remap(
        self,
        mock_attach_remapped_tokens,
        mock_attach_llm_labels,
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
                    {"index": 1, "start": 0.0, "end": 3.0, "text": "先讲重点结论"},
                ],
                "segments": [
                    {"start": 0.0, "end": 3.0},
                ],
            }
            mock_attach_remapped_tokens.return_value = [
                {
                    "index": 1,
                    "start": 0.0,
                    "end": 3.0,
                    "text": "先讲重点结论",
                    "tokens": [
                        {"text": "先", "start": 0.0, "end": 0.5},
                        {"text": "讲", "start": 0.5, "end": 1.0},
                        {"text": "重点", "start": 1.0, "end": 2.0},
                        {"text": "结论", "start": 2.0, "end": 3.0},
                    ],
                }
            ]
            mock_attach_llm_labels.return_value = [
                {
                    "index": 1,
                    "start": 0.0,
                    "end": 3.0,
                    "text": "先讲重点结论",
                    "tokens": [
                        {"text": "先", "start": 0.0, "end": 0.5},
                        {"text": "讲", "start": 0.5, "end": 1.0},
                        {"text": "重点", "start": 1.0, "end": 2.0},
                        {"text": "结论", "start": 2.0, "end": 3.0},
                    ],
                    "label": {
                        "badgeText": "结论",
                        "emphasisSpans": [{"startToken": 2, "endToken": 4}],
                    },
                }
            ]
            mock_list_final_test_chapters.return_value = []

            config = build_web_render_config(
                "job-render-label-test",
                width=1080,
                height=1920,
                fps=30.0,
            )

        self.assertEqual(
            mock_attach_llm_labels.call_args.kwargs["captions"][0]["tokens"][2]["text"],
            "重点",
        )
        self.assertEqual(mock_attach_llm_labels.call_args.kwargs["job_id"], "job-render-label-test")
        self.assertEqual(
            config["input_props"]["captions"][0]["label"],
            {
                "badgeText": "结论",
                "emphasisSpans": [{"startToken": 2, "endToken": 4}],
            },
        )

    @patch("web_api.services.render_web.list_final_test_chapters")
    @patch("web_api.services.render_web.build_cut_srt_from_optimized_srt")
    @patch("web_api.services.render_web.ensure_job_dirs")
    @patch("web_api.services.render_web.get_settings")
    @patch("web_api.services.render_web.get_job_files")
    def test_build_web_render_config_includes_token_tracks_when_sidecar_exists(
        self,
        mock_get_job_files,
        mock_get_settings,
        mock_ensure_job_dirs,
        mock_build_cut_srt,
        mock_list_final_test_chapters,
    ) -> None:
        raw_case_path = Path(__file__).resolve().parents[2] / "test_data" / "media" / "1.dashscope.raw.json"
        raw_payload = json.loads(raw_case_path.read_text(encoding="utf-8"))
        sidecar = build_sidecar_from_dashscope_payload(raw_payload, asset_id="fixture")
        assert sidecar is not None
        sentence = sidecar["sentences"][0]

        with tempfile.TemporaryDirectory() as temp_dir:
            render_dir = Path(temp_dir)
            sidecar_path = write_sidecar(render_dir / "audio.asr.words.json", sidecar)
            mock_get_job_files.return_value = {
                "final_test_srt_path": render_dir / "final_test.srt",
                "asr_words_sidecar_path": str(sidecar_path),
            }
            mock_get_settings.return_value = type("Settings", (), {"cut_merge_gap": 0.0})()
            mock_ensure_job_dirs.return_value = {"render": render_dir}
            mock_build_cut_srt.return_value = {
                "captions": [
                    {
                        "index": 1,
                        "start": 0.0,
                        "end": round((sentence["end_ms"] - sentence["start_ms"]) / 1000.0, 3),
                        "text": sentence["text"],
                    }
                ],
                "segments": [
                    {
                        "start": sentence["start_ms"] / 1000.0,
                        "end": sentence["end_ms"] / 1000.0,
                    }
                ],
                "kept_subtitles": [
                    srt.Subtitle(
                        index=1,
                        start=timedelta(seconds=sentence["start_ms"] / 1000.0),
                        end=timedelta(seconds=sentence["end_ms"] / 1000.0),
                        content=sentence["text"],
                    )
                ],
            }
            mock_list_final_test_chapters.return_value = []

            config = build_web_render_config(
                "job-render-token-test",
                width=1080,
                height=1920,
                fps=30.0,
            )

        tokens = config["input_props"]["captions"][0]["tokens"]
        self.assertEqual([token["text"] for token in tokens[:5]], ["哟，", "这", "里", "是", "俊。"])
        self.assertEqual(config["input_props"]["captions"][0]["alignmentMode"], "fuzzy")

    @patch("web_api.services.render_web.get_job_files")
    def test_build_web_render_config_reads_subtitle_render_v1_contract_object(
        self,
        mock_get_job_files,
    ) -> None:
        mock_get_job_files.return_value = {
            "subtitle_render_v1": {
                "version": "subtitle-render.v1",
                "output_name": "contract-output.mp4",
                "composition": {
                    "width": 720,
                    "height": 1280,
                    "fps": 24,
                },
                "captions": [
                    {
                        "index": 1,
                        "start": 0.0,
                        "end": 1.8,
                        "text": "先给一个最小合同",
                        "tokens": [
                            {"text": "先", "start": 0.0, "end": 0.3},
                            {"text": "给", "start": 0.3, "end": 0.6},
                        ],
                        "label": {
                            "badgeText": "重点",
                            "emphasisSpans": [{"startToken": 0, "endToken": 1}],
                        },
                        "alignmentMode": "exact",
                    }
                ],
                "segments": [
                    {"start": 3.0, "end": 4.8},
                ],
                "topics": [
                    {"title": "第一段", "start": 0.0, "end": 1.8},
                ],
                "subtitleTheme": "text-white",
            }
        }

        config = build_web_render_config("job-render-contract-test")

        self.assertEqual(config["output_name"], "contract-output.mp4")
        self.assertEqual(config["composition"]["width"], 720)
        self.assertEqual(config["composition"]["height"], 1280)
        self.assertEqual(config["composition"]["fps"], 24)
        self.assertEqual(config["composition"]["durationInFrames"], 44)
        self.assertEqual(config["input_props"]["segments"], [{"start": 3.0, "end": 4.8}])
        self.assertEqual(config["input_props"]["captions"][0]["tokens"][0]["text"], "先")
        self.assertEqual(config["input_props"]["captions"][0]["label"]["badgeText"], "重点")
        self.assertEqual(config["input_props"]["captions"][0]["alignmentMode"], "exact")
        self.assertEqual(config["input_props"]["subtitleTheme"], "text-white")



if __name__ == "__main__":
    unittest.main()
