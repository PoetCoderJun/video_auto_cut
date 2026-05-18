from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import srt

from video_auto_cut.asr.word_timing_sidecar import build_sidecar_from_dashscope_payload, write_sidecar
from web_api.services.render_web import (
    _resolve_dimensions,
    build_web_render_config,
    ensure_subtitle_render_v1_contract,
    warm_editor_subtitle_style_cache,
)


class RenderWebConfigTest(unittest.TestCase):
    def test_resolve_dimensions_rejects_non_positive_values_with_user_facing_message(self) -> None:
        with self.assertRaisesRegex(ValueError, "视频分辨率无效，请重新选择源文件后重试"):
            _resolve_dimensions(0, 0)

    @patch("web_api.services.render_web.get_job_files")
    def test_ensure_subtitle_render_v1_contract_reuses_existing_contract(self, mock_get_job_files) -> None:
        existing_contract = {
            "version": "subtitle-render.v1",
            "output_name": "job-existing_export.mp4",
            "subtitleTheme": "white",
            "captions": [{"index": 1, "start": 0.0, "end": 1.0, "text": "你好"}],
            "segments": [{"start": 0.0, "end": 1.0}],
            "topics": [],
        }
        mock_get_job_files.return_value = {
            "subtitle_render_v1": existing_contract,
        }

        contract = ensure_subtitle_render_v1_contract("job-existing")

        self.assertEqual(contract, existing_contract)

    @patch("web_api.services.render_web._generate_subtitle_render_v1_contract")
    @patch("web_api.services.render_web.get_job_files")
    def test_ensure_subtitle_render_v1_contract_reuses_existing_contract_for_matching_revision(
        self,
        mock_get_job_files,
        mock_generate_contract,
    ) -> None:
        existing_contract = {
            "version": "subtitle-render.v1",
            "sourceRevision": "rev-123",
            "output_name": "job-existing_export.mp4",
            "subtitleTheme": "white",
            "captions": [{"index": 1, "start": 0.0, "end": 1.0, "text": "你好"}],
            "segments": [{"start": 0.0, "end": 1.0}],
            "topics": [],
        }
        mock_get_job_files.return_value = {
            "subtitle_render_v1": existing_contract,
        }

        contract = ensure_subtitle_render_v1_contract(
            "job-existing",
            document_revision="rev-123",
        )

        self.assertEqual(contract, existing_contract)
        mock_generate_contract.assert_not_called()

    @patch("web_api.services.render_web._generate_subtitle_render_v1_contract")
    @patch("web_api.services.render_web.get_job_files")
    def test_ensure_subtitle_render_v1_contract_regenerates_for_revision_mismatch(
        self,
        mock_get_job_files,
        mock_generate_contract,
    ) -> None:
        mock_get_job_files.return_value = {
            "subtitle_render_v1": {
                "version": "subtitle-render.v1",
                "sourceRevision": "rev-old",
                "output_name": "job-existing_export.mp4",
                "subtitleTheme": "white",
                "captions": [{"index": 1, "start": 0.0, "end": 1.0, "text": "你好"}],
                "segments": [{"start": 0.0, "end": 1.0}],
                "topics": [],
            }
        }
        mock_generate_contract.return_value = {
            "version": "subtitle-render.v1",
            "sourceRevision": "rev-new",
            "output_name": "job-existing_export.mp4",
            "subtitleTheme": "white",
            "captions": [{"index": 1, "start": 0.0, "end": 1.0, "text": "你好"}],
            "segments": [{"start": 0.0, "end": 1.0}],
            "topics": [],
        }

        contract = ensure_subtitle_render_v1_contract(
            "job-existing",
            document_revision="rev-new",
        )

        self.assertEqual(contract["sourceRevision"], "rev-new")
        mock_generate_contract.assert_called_once()

    @patch("web_api.services.render_web.request_subtitle_style_contract")
    @patch("web_api.services.render_web.ensure_job_dirs")
    @patch("web_api.services.render_web.get_job_files")
    def test_warm_editor_subtitle_style_cache_includes_removed_lines(
        self,
        mock_get_job_files,
        mock_ensure_job_dirs,
        mock_request_style_contract,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            render_dir = Path(temp_dir)
            mock_get_job_files.return_value = {"subtitle_theme": "stroke-white"}
            mock_ensure_job_dirs.return_value = {"render": render_dir}
            mock_request_style_contract.return_value = {
                "version": "subtitle-style.v1",
                "subtitleTheme": "white",
                "captions": [
                    {"start": "00:00:00.000", "end": "00:00:01.000", "text": "保留句", "highlights": ["保留"]},
                    {"start": "00:00:01.000", "end": "00:00:02.000", "text": "已删句", "highlights": ["已删"]},
                ],
            }

            style_contract = warm_editor_subtitle_style_cache(
                "job-style-cache",
                lines=[
                    {
                        "line_id": 1,
                        "start": 0.0,
                        "end": 1.0,
                        "original_text": "保留句",
                        "optimized_text": "保留句",
                        "user_final_remove": False,
                    },
                    {
                        "line_id": 2,
                        "start": 1.0,
                        "end": 2.0,
                        "original_text": "已删句",
                        "optimized_text": "已删句",
                        "user_final_remove": True,
                    },
                ],
                document_revision="draft-rev-remove",
            )

        request_captions = mock_request_style_contract.call_args.kwargs["captions"]
        self.assertEqual([item["index"] for item in request_captions], [1, 2])
        self.assertEqual([item["text"] for item in request_captions], ["保留句", "已删句"])
        self.assertEqual(style_contract["sourceRevision"], "draft-rev-remove")

    @patch("web_api.services.render_web.upsert_job_files")
    @patch("web_api.services.render_web.write_subtitle_render_v1_contract")
    @patch("web_api.services.render_web.build_subtitle_render_v1_contract")
    @patch("web_api.services.render_web.attach_remapped_tokens_to_captions")
    @patch("web_api.services.render_web.build_cut_srt_from_optimized_srt")
    @patch("web_api.services.render_web.ensure_job_dirs")
    @patch("web_api.services.render_web.get_settings")
    @patch("web_api.services.render_web.get_job_files")
    def test_ensure_subtitle_render_v1_contract_uses_editor_style_cache_for_restored_line(
        self,
        mock_get_job_files,
        mock_get_settings,
        mock_ensure_job_dirs,
        mock_build_cut_srt,
        mock_attach_remapped_tokens,
        mock_build_contract,
        mock_write_contract,
        mock_upsert_job_files,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            render_dir = Path(temp_dir)
            (render_dir / "subtitle-style-editor.v1.json").write_text(
                json.dumps(
                    {
                        "version": "subtitle-style.v1",
                        "subtitleTheme": "white",
                        "captions": [
                            {
                                "index": 2,
                                "start": "00:00:01.000",
                                "end": "00:00:02.000",
                                "text": "之前被删、现在恢复",
                                "highlights": ["现在恢复"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            mock_get_job_files.return_value = {"subtitle_theme": "stroke-white"}
            mock_get_settings.return_value = type("Settings", (), {"cut_merge_gap": 0.0})()
            mock_ensure_job_dirs.return_value = {"render": render_dir}
            mock_build_cut_srt.return_value = {
                "captions": [
                    {"index": 2, "start": 0.0, "end": 1.0, "text": "之前被删、现在恢复"},
                ],
                "segments": [{"start": 0.0, "end": 1.0}],
                "kept_subtitles": [],
            }
            mock_attach_remapped_tokens.return_value = [
                {"index": 2, "start": 0.0, "end": 1.0, "text": "之前被删、现在恢复"}
            ]
            mock_build_contract.return_value = {
                "version": "subtitle-render.v1",
                "output_name": "job-restored_export.mp4",
                "subtitleTheme": "white",
                "captions": [{"index": 2, "start": 0.0, "end": 1.0, "text": "之前被删、现在恢复"}],
                "segments": [{"start": 0.0, "end": 1.0}],
                "topics": [],
            }
            mock_write_contract.return_value = render_dir / "subtitle-render.v1.json"

            ensure_subtitle_render_v1_contract(
                "job-restored",
                lines=[
                    {
                        "line_id": 2,
                        "start": 1.0,
                        "end": 2.0,
                        "original_text": "之前被删、现在恢复",
                        "optimized_text": "之前被删、现在恢复",
                        "user_final_remove": False,
                    }
                ],
                chapters=[],
                document_revision="rev-restored",
            )

        style_contract = mock_build_contract.call_args.kwargs["style_contract"]
        self.assertIsNotNone(style_contract)
        self.assertEqual(style_contract["captions"][0]["highlights"], ["现在恢复"])

    @patch("web_api.services.render_web.upsert_job_files")
    @patch("web_api.services.render_web.write_subtitle_render_v1_contract")
    @patch("web_api.services.render_web.build_subtitle_render_v1_contract")
    @patch("web_api.services.render_web.attach_remapped_tokens_to_captions")
    @patch("web_api.services.render_web.build_cut_srt_from_optimized_srt")
    @patch("web_api.services.render_web.ensure_job_dirs")
    @patch("web_api.services.render_web.get_settings")
    @patch("web_api.services.render_web.get_job_files")
    def test_ensure_subtitle_render_v1_contract_can_generate_from_editor_draft(
        self,
        mock_get_job_files,
        mock_get_settings,
        mock_ensure_job_dirs,
        mock_build_cut_srt,
        mock_attach_remapped_tokens,
        mock_build_contract,
        mock_write_contract,
        mock_upsert_job_files,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            render_dir = Path(temp_dir)
            mock_get_job_files.return_value = {"subtitle_theme": "stroke-white"}
            mock_get_settings.return_value = type("Settings", (), {"cut_merge_gap": 0.0})()
            mock_ensure_job_dirs.return_value = {"render": render_dir}
            mock_build_cut_srt.return_value = {
                "captions": [
                    {"index": 1, "start": 0.0, "end": 1.2, "text": "编辑阶段的字幕"},
                ],
                "segments": [
                    {"start": 0.0, "end": 1.2},
                ],
                "kept_subtitles": [],
            }
            mock_attach_remapped_tokens.return_value = [
                {"index": 1, "start": 0.0, "end": 1.2, "text": "编辑阶段的字幕"}
            ]
            mock_build_contract.return_value = {
                "version": "subtitle-render.v1",
                "output_name": "job-editor_export.mp4",
                "subtitleTheme": "white",
                "captions": [{"index": 1, "start": 0.0, "end": 1.2, "text": "编辑阶段的字幕"}],
                "segments": [{"start": 0.0, "end": 1.2}],
                "topics": [{"title": "草稿章节", "start": 0.0, "end": 1.2}],
            }
            mock_write_contract.return_value = render_dir / "subtitle-render.v1.json"

            contract = ensure_subtitle_render_v1_contract(
                "job-editor",
                lines=[
                    {
                        "line_id": 1,
                        "start": 0.0,
                        "end": 1.2,
                        "original_text": "编辑阶段的字幕",
                        "optimized_text": "编辑阶段的字幕",
                        "user_final_remove": False,
                    }
                ],
                chapters=[
                    {
                        "chapter_id": 1,
                        "title": "草稿章节",
                        "start": 0.0,
                        "end": 1.2,
                        "block_range": "1",
                    }
                ],
                document_revision="draft-rev-1",
            )

        self.assertEqual(contract["sourceRevision"], "draft-rev-1")
        self.assertEqual(
            mock_build_contract.call_args.kwargs["topics"],
            [{"title": "草稿章节", "start": 0.0, "end": 1.2}],
        )
        source_srt_path = mock_build_cut_srt.call_args.kwargs["source_srt_path"]
        self.assertTrue(source_srt_path.endswith("editor-ready.test.srt"))
        mock_upsert_job_files.assert_called_once_with(
            "job-editor",
            subtitle_render_v1_path=str(render_dir / "subtitle-render.v1.json"),
        )

    @patch("web_api.services.render_web.list_final_test_chapters")
    @patch("web_api.services.render_web.build_cut_srt_from_optimized_srt")
    @patch("web_api.services.render_web.ensure_job_dirs")
    @patch("web_api.services.render_web.get_settings")
    @patch("web_api.services.render_web.get_job_files")
    def test_ensure_subtitle_render_v1_contract_keeps_original_titles(
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

            contract = ensure_subtitle_render_v1_contract("job-render-test")

        self.assertEqual(
            [item["title"] for item in contract["topics"]],
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
    def test_ensure_subtitle_render_v1_contract_remaps_topics_to_cut_timeline(
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

            contract = ensure_subtitle_render_v1_contract("job-render-remap-test")

        self.assertEqual(
            contract["topics"],
            [
                {"title": "开场", "start": 0.0, "end": 4.0},
                {"title": "展开", "start": 4.0, "end": 10.0},
            ],
        )

    @patch("web_api.services.render_web.upsert_job_files")
    @patch("web_api.services.render_web.write_subtitle_render_v1_contract")
    @patch("web_api.services.render_web.build_subtitle_render_v1_contract")
    @patch("web_api.services.render_web.list_final_test_chapters")
    @patch("web_api.services.render_web.build_cut_srt_from_optimized_srt")
    @patch("web_api.services.render_web.ensure_job_dirs")
    @patch("web_api.services.render_web.get_settings")
    @patch("web_api.services.render_web.get_job_files")
    @patch("web_api.services.render_web.attach_remapped_tokens_to_captions")
    def test_ensure_subtitle_render_v1_contract_generates_contract_from_tokenized_captions(
        self,
        mock_attach_remapped_tokens,
        mock_get_job_files,
        mock_get_settings,
        mock_ensure_job_dirs,
        mock_build_cut_srt,
        mock_list_final_test_chapters,
        mock_build_subtitle_render_v1_contract,
        mock_write_subtitle_render_v1_contract,
        mock_upsert_job_files,
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
            generated_contract = {
                "version": "subtitle-render.v1",
                "output_name": "job-render-label-test_export.mp4",
                "subtitleTheme": "white",
                "captions": [
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
                            "highlights": [{"text": "重点结论"}],
                        },
                    }
                ],
                "segments": [{"start": 0.0, "end": 3.0}],
                "topics": [],
            }
            mock_build_subtitle_render_v1_contract.return_value = generated_contract
            mock_write_subtitle_render_v1_contract.return_value = render_dir / "subtitle-render.v1.json"
            mock_list_final_test_chapters.return_value = []

            contract = ensure_subtitle_render_v1_contract("job-render-label-test")

        self.assertEqual(
            mock_build_subtitle_render_v1_contract.call_args.kwargs["captions"][0]["tokens"][2]["text"],
            "重点",
        )
        self.assertEqual(
            mock_build_subtitle_render_v1_contract.call_args.kwargs["output_name"],
            "job-render-label-test_export.mp4",
        )
        self.assertEqual(contract["captions"][0]["label"]["highlights"][0]["text"], "重点结论")
        mock_upsert_job_files.assert_called_once_with(
            "job-render-label-test",
            subtitle_render_v1_path=str(render_dir / "subtitle-render.v1.json"),
        )

    @patch("web_api.services.render_web.list_final_test_chapters")
    @patch("web_api.services.render_web.build_cut_srt_from_optimized_srt")
    @patch("web_api.services.render_web.ensure_job_dirs")
    @patch("web_api.services.render_web.get_settings")
    @patch("web_api.services.render_web.get_job_files")
    def test_ensure_subtitle_render_v1_contract_includes_token_tracks_when_sidecar_exists(
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

            contract = ensure_subtitle_render_v1_contract("job-render-token-test")

        tokens = contract["captions"][0]["tokens"]
        self.assertEqual([token["text"] for token in tokens[:5]], ["哟，", "这", "里", "是", "俊。"])
        self.assertEqual(contract["captions"][0]["alignmentMode"], "fuzzy")

    @patch("web_api.services.render_web.get_job_files")
    def test_build_web_render_config_rejects_missing_contract(self, mock_get_job_files) -> None:
        mock_get_job_files.return_value = {
            "final_test_srt_path": "/tmp/final_test.srt",
        }

        with self.assertRaisesRegex(RuntimeError, "导出配置尚未准备完成，请返回上一步重新确认后再试。"):
            build_web_render_config("job-missing-contract")

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
                            "highlights": [
                                {"text": "先", "color": "#22c55e", "fontScale": 1.2}
                            ],
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
                "subtitleTheme": "black",
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
        self.assertEqual(config["input_props"]["captions"][0]["label"]["highlights"][0]["text"], "先")
        self.assertEqual(config["input_props"]["captions"][0]["alignmentMode"], "exact")
        self.assertEqual(config["input_props"]["subtitleTheme"], "stroke")

    @patch("web_api.services.render_web.get_job_files")
    def test_build_web_render_config_accepts_timed_string_highlights_without_segments(
        self,
        mock_get_job_files,
    ) -> None:
        mock_get_job_files.return_value = {
            "subtitle_render_v1": {
                "version": "subtitle-render.v1",
                "composition": {
                    "width": 1080,
                    "height": 1920,
                    "fps": 30,
                },
                "captions": [
                    {
                        "start": "00:00:00.000",
                        "end": "00:00:01.200",
                        "text": "重点结论先出来",
                        "label": {
                            "highlights": [
                                {"text": "重点", "color": "#f97316", "fontScale": 1.16}
                            ]
                        },
                    }
                ],
                "subtitleTheme": "white",
            }
        }

        config = build_web_render_config("job-render-highlight-contract")

        self.assertEqual(config["input_props"]["segments"], [{"start": 0.0, "end": 1.2}])
        self.assertEqual(config["input_props"]["subtitleTheme"], "stroke-white")
        self.assertEqual(config["input_props"]["captions"][0]["tokens"][0]["text"], "重")
        self.assertEqual(
            config["input_props"]["captions"][0]["label"]["highlights"][0],
            {
                "text": "重点",
                "startToken": 0,
                "endToken": 2,
                "color": "#f97316",
                "fontScale": 1.16,
            },
        )



if __name__ == "__main__":
    unittest.main()
