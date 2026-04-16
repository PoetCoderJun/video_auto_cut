from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

import srt

from video_auto_cut.editing.topic_segment import (
    PiAgentTopicLoop,
    TopicSegment,
    TopicSegmenter,
    _build_candidate_blocks,
    _build_segmentation_prompt,
    _find_topic_plan_issues,
    _is_topic_plan_valid,
    _parse_segment_plan,
    _recommended_topic_budget,
    _topic_count_range,
)
from video_auto_cut.orchestration.pipeline_options_builder import build_pipeline_options_from_settings
from video_auto_cut.rendering.cut_srt import build_cut_srt_from_optimized_srt
from video_auto_cut.shared.interfaces import PipelineOptions


class Step2TopicModelConfigTest(unittest.TestCase):
    def test_build_pipeline_options_defaults_topic_model_to_main_model_and_caps_topic_count(self) -> None:
        class DummySettings:
            lang = "Chinese"
            asr_dashscope_base_url = "https://dashscope.aliyuncs.com"
            asr_dashscope_model = "qwen3-asr-flash-filetrans"
            asr_dashscope_task = ""
            asr_dashscope_api_key = "asr-key"
            asr_dashscope_poll_seconds = 2.0
            asr_dashscope_timeout_seconds = 3600.0
            asr_dashscope_language = "zh"
            asr_dashscope_language_hints = ()
            asr_dashscope_context = ""
            asr_dashscope_enable_itn = False
            asr_dashscope_enable_words = True
            asr_dashscope_channel_ids = (0,)
            asr_dashscope_sentence_rule_with_punc = True
            asr_dashscope_word_split_enabled = True
            asr_dashscope_word_split_on_comma = True
            asr_dashscope_word_split_comma_pause_s = 0.4
            asr_dashscope_word_split_min_chars = 12
            asr_dashscope_word_vad_gap_s = 1.0
            asr_dashscope_word_max_segment_s = 8.0
            asr_dashscope_no_speech_gap_s = 1.0
            asr_dashscope_insert_no_speech = True
            asr_dashscope_insert_head_no_speech = True
            asr_oss_endpoint = None
            asr_oss_bucket = None
            asr_oss_access_key_id = None
            asr_oss_access_key_secret = None
            asr_oss_prefix = "video-auto-cut/asr"
            asr_oss_signed_url_ttl_seconds = 86400
            llm_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            llm_model = "kimi-k2.5"
            llm_api_key = "llm-key"
            llm_timeout = 300
            llm_temperature = 0.2
            llm_max_tokens = None
            cut_merge_gap = 0.0
            topic_max_topics = 8
            topic_title_max_chars = 6
            topic_llm_model = "qwen-flash"

        options = build_pipeline_options_from_settings(DummySettings())

        self.assertEqual(options.llm_model, "kimi-k2.5")
        self.assertEqual(options.topic_llm_model, "kimi-k2.5")
        self.assertEqual(options.topic_max_topics, 6)

    def test_topic_segmenter_direct_options_uses_main_llm_model(self) -> None:
        options = PipelineOptions(
            llm_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            llm_model="kimi-k2.5",
            topic_llm_model="qwen-flash",
            llm_api_key="llm-key",
        )

        segmenter = TopicSegmenter(
            Path("/tmp/input.srt"),
            options,
            output_path=Path("/tmp/topics.json"),
        )

        self.assertEqual(segmenter.llm_config["model"], "kimi-k2.5")

    def test_build_candidate_blocks_skips_pre_chunking_when_target_blocks_exceed_segments(self) -> None:
        segments = [
            TopicSegment(segment_id=1, start=0.0, end=5.0, text="a"),
            TopicSegment(segment_id=2, start=5.0, end=10.0, text="b"),
            TopicSegment(segment_id=3, start=10.0, end=15.0, text="c"),
        ]

        blocks = _build_candidate_blocks(segments, recommended_topics=4)

        self.assertEqual(
            [(block.block_id, block.segment_ids) for block in blocks],
            [(1, [1]), (2, [2]), (3, [3])],
        )

    def test_build_candidate_blocks_skips_pre_chunking_when_average_block_too_small(self) -> None:
        segments = [
            TopicSegment(segment_id=index, start=(index - 1) * 5.0, end=index * 5.0, text=f"句子{index}")
            for index in range(1, 25)
        ]

        blocks = _build_candidate_blocks(segments, recommended_topics=4)

        self.assertEqual(len(blocks), len(segments))
        self.assertEqual(blocks[0].segment_ids, [1])
        self.assertEqual(blocks[-1].segment_ids, [24])

    def test_build_candidate_blocks_compacts_longer_input(self) -> None:
        segments = [
            TopicSegment(segment_id=index, start=(index - 1) * 5.0, end=index * 5.0, text=f"句子{index}")
            for index in range(1, 49)
        ]

        blocks = _build_candidate_blocks(segments, recommended_topics=4)

        self.assertLess(len(blocks), len(segments))
        self.assertEqual(blocks[0].segment_ids[0], 1)
        self.assertEqual(blocks[-1].segment_ids[-1], 48)

    def test_parse_segment_plan_reads_block_ranges(self) -> None:
        plan = _parse_segment_plan(
            """
            {
              "topics": [
                {"block_range": "1-2", "title": "开场"},
                {"block_range": "3-4", "title": "打法"}
              ]
            }
            """
        )

        self.assertEqual(plan, [[1, 2], [3, 4]])

    def test_parse_segment_plan_rejects_legacy_segment_ranges(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "empty segmentation plan"):
            _parse_segment_plan(
                """
                {
                  "topics": [
                    {"segment_range": "1-2", "title": "开场"},
                    {"segment_range": "3-4", "title": "打法"}
                  ]
                }
                """
            )

    def test_parse_segment_plan_rejects_legacy_segment_ids(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "empty segmentation plan"):
            _parse_segment_plan(
                """
                {
                  "topics": [
                    {"segment_ids": [1, 2], "title": "开场"},
                    {"segment_ids": [3, 4], "title": "打法"}
                  ]
                }
                """
            )

    def test_parse_segment_plan_rejects_legacy_range_alias(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "empty segmentation plan"):
            _parse_segment_plan(
                """
                {
                  "topics": [
                    {"range": "1-2", "title": "开场"},
                    {"range": "3-4", "title": "打法"}
                  ]
                }
                """
            )

    def test_topic_segmentation_uses_simple_duration_bands(self) -> None:
        self.assertEqual(_recommended_topic_budget(90.0), 4)
        self.assertEqual(_recommended_topic_budget(240.0), 5)
        self.assertEqual(_recommended_topic_budget(420.0), 6)

    def test_topic_segmentation_allows_up_to_six_topics_across_duration_bands(self) -> None:
        self.assertEqual(_topic_count_range(90.0), (4, 4, 6))
        self.assertEqual(_topic_count_range(240.0), (4, 5, 6))
        self.assertEqual(_topic_count_range(420.0), (4, 6, 6))

    def test_topic_plan_issues_allow_non_empty_placeholder_titles(self) -> None:
        issues = _find_topic_plan_issues(
            {
                "topics": [
                    {"block_range": "1-3", "title": "剪辑耗时长的问题与解决方案"},
                    {"block_range": "4", "title": "章节2"},
                ]
            },
            segments=[
                TopicSegment(segment_id=1, start=0.0, end=1.0, text="a"),
                TopicSegment(segment_id=2, start=1.0, end=2.0, text="b"),
                TopicSegment(segment_id=3, start=2.0, end=3.0, text="c"),
                TopicSegment(segment_id=4, start=3.0, end=4.0, text="d"),
            ],
        )

        self.assertEqual(issues, [])

    def test_topic_plan_issues_allow_short_chapters(self) -> None:
        issues = _find_topic_plan_issues(
            {
                "topics": [
                    {"block_range": "1-2", "title": "开场说明"},
                    {"block_range": "3-5", "title": "解决方法"},
                ]
            },
            segments=[
                TopicSegment(segment_id=1, start=0.0, end=1.0, text="a"),
                TopicSegment(segment_id=2, start=1.0, end=2.0, text="b"),
                TopicSegment(segment_id=3, start=2.0, end=3.0, text="c"),
                TopicSegment(segment_id=4, start=3.0, end=4.0, text="d"),
                TopicSegment(segment_id=5, start=4.0, end=5.0, text="e"),
            ],
        )

        self.assertEqual(issues, [])

    def test_topic_plan_issues_flag_empty_titles(self) -> None:
        issues = _find_topic_plan_issues(
            {
                "topics": [
                    {"block_range": "1-2", "title": "开场说明"},
                    {"block_range": "3-5", "title": ""},
                ]
            },
            segments=[
                TopicSegment(segment_id=1, start=0.0, end=1.0, text="a"),
                TopicSegment(segment_id=2, start=1.0, end=2.0, text="b"),
                TopicSegment(segment_id=3, start=2.0, end=3.0, text="c"),
                TopicSegment(segment_id=4, start=3.0, end=4.0, text="d"),
                TopicSegment(segment_id=5, start=4.0, end=5.0, text="e"),
            ],
        )

        self.assertTrue(any("标题为空" in issue["message"] for issue in issues))

    def test_topic_plan_does_not_hard_fail_for_long_titles(self) -> None:
        payload = {
            "topics": [
                {"block_range": "1-2", "title": "这是一个很长的标题"},
            ]
        }
        segments = [
            TopicSegment(segment_id=1, start=0.0, end=1.0, text="a"),
            TopicSegment(segment_id=2, start=1.0, end=2.0, text="b"),
        ]

        self.assertTrue(
            _is_topic_plan_valid(
                payload,
                segments,
            )
        )

    def test_segmentation_prompt_includes_computed_max_topics(self) -> None:
        blocks = _build_candidate_blocks(
            [
                TopicSegment(segment_id=index, start=float(index - 1), end=float(index), text=f"句子{index}")
                for index in range(1, 11)
            ],
            recommended_topics=3,
        )

        messages = _build_segmentation_prompt(
            blocks,
            total_segments=10,
            min_topics=3,
            max_topics=3,
            recommended_topics=3,
            title_max_chars=6,
            min_segments_per_topic=3,
        )

        self.assertIn("基于当前共 10 句字幕、每章至少 3 句，本次最多只能分成 3 章", messages[0]["content"])
        self.assertIn("block_range 虽沿用旧字段名，但这里必须填写连续字幕 segment 编号范围", messages[0]["content"])

    def test_pi_agent_topic_loop_allows_single_chapter_when_coverage_is_valid(self) -> None:
        segments = [
            TopicSegment(segment_id=1, start=0.0, end=5.0, text="先讲开场"),
            TopicSegment(segment_id=2, start=5.0, end=10.0, text="继续开场"),
            TopicSegment(segment_id=3, start=10.0, end=15.0, text="开场结束"),
            TopicSegment(segment_id=4, start=15.0, end=20.0, text="开始方法"),
            TopicSegment(segment_id=5, start=20.0, end=25.0, text="展开方法"),
            TopicSegment(segment_id=6, start=25.0, end=30.0, text="方法收束"),
        ]
        response = """
        {
          "topics": [
            {"block_range": "1-6", "title": "整体方案"}
          ]
        }
        """

        loop = PiAgentTopicLoop(
            llm_config={"base_url": "https://example.com", "model": "test-model"},
            min_topics=2,
            max_topics=6,
            recommended_topics=2,
            title_max_chars=6,
            chat_completion_fn=lambda _config, _messages: response,
        )

        result = loop.run(segments)

        self.assertEqual([topic["block_range"] for topic in result.payload["topics"]], ["1-6"])

    def test_pi_agent_topic_loop_allows_short_generated_chapter(self) -> None:
        segments = [
            TopicSegment(segment_id=index, start=float(index - 1), end=float(index), text=f"句子{index}")
            for index in range(1, 11)
        ]
        response = """
        {
          "topics": [
            {"block_range": "1-4", "title": "开场说明"},
            {"block_range": "5-8", "title": "中段推进"},
            {"block_range": "9-10", "title": "最后动作"}
          ]
        }
        """

        loop = PiAgentTopicLoop(
            llm_config={"base_url": "https://example.com", "model": "test-model"},
            min_topics=3,
            max_topics=6,
            recommended_topics=3,
            title_max_chars=6,
            chat_completion_fn=lambda _config, _messages: response,
        )

        result = loop.run(segments)

        self.assertEqual([topic["block_range"] for topic in result.payload["topics"]], ["1-4", "5-8", "9-10"])
        self.assertEqual(result.debug["final_source"], "draft")

    def test_topic_plan_issues_allow_too_few_topics_for_long_video(self) -> None:
        issues = _find_topic_plan_issues(
            {
                "topics": [
                    {"block_range": "1-6", "title": "整体方案"},
                ]
            },
            segments=[
                TopicSegment(segment_id=1, start=0.0, end=45.0, text="a"),
                TopicSegment(segment_id=2, start=45.0, end=90.0, text="b"),
                TopicSegment(segment_id=3, start=90.0, end=135.0, text="c"),
                TopicSegment(segment_id=4, start=135.0, end=180.0, text="d"),
                TopicSegment(segment_id=5, start=180.0, end=225.0, text="e"),
                TopicSegment(segment_id=6, start=225.0, end=270.0, text="f"),
            ],
        )

        self.assertEqual(issues, [])

    def test_topic_plan_can_exceed_max_topics_without_hard_failure(self) -> None:
        issues = _find_topic_plan_issues(
            {
                "topics": [
                    {"block_range": "1", "title": "开场说明"},
                    {"block_range": "2", "title": "第一重点"},
                    {"block_range": "3", "title": "第二重点"},
                    {"block_range": "4", "title": "第三重点"},
                    {"block_range": "5", "title": "第四重点"},
                    {"block_range": "6", "title": "收尾总结"},
                ]
            },
            segments=[
                TopicSegment(segment_id=1, start=0.0, end=10.0, text="a"),
                TopicSegment(segment_id=2, start=10.0, end=20.0, text="b"),
                TopicSegment(segment_id=3, start=20.0, end=30.0, text="c"),
                TopicSegment(segment_id=4, start=30.0, end=40.0, text="d"),
                TopicSegment(segment_id=5, start=40.0, end=50.0, text="e"),
                TopicSegment(segment_id=6, start=50.0, end=60.0, text="f"),
            ],
        )

        self.assertEqual(issues, [])

    def test_topic_loop_fails_when_draft_payload_has_invalid_range_syntax(self) -> None:
        segments = [
            TopicSegment(segment_id=index, start=(index - 1) * 5.0, end=index * 5.0, text=f"句子{index}")
            for index in range(1, 7)
        ]
        response = """
        {
          "topics": [
            {"block_range": "1,4", "title": "坏计划"}
          ]
        }
        """

        loop = PiAgentTopicLoop(
            llm_config={"base_url": "https://example.com", "model": "test-model"},
            min_topics=2,
            max_topics=6,
            recommended_topics=2,
            title_max_chars=6,
            chat_completion_fn=lambda _config, _messages: response,
        )

        with self.assertRaisesRegex(RuntimeError, "empty segmentation plan"):
            loop.run(segments)

    def test_topic_loop_rejects_block_numbered_draft_when_blocks_are_compacted(self) -> None:
        segments = [
            TopicSegment(segment_id=index, start=(index - 1) * 5.0, end=index * 5.0, text=f"句子{index}")
            for index in range(1, 49)
        ]
        block_count = len(_build_candidate_blocks(segments, recommended_topics=4))
        response = f"""
        {{
          "topics": [
            {{"block_range": "1-{block_count}", "title": "按 block 编号误返回"}}
          ]
        }}
        """

        loop = PiAgentTopicLoop(
            llm_config={"base_url": "https://example.com", "model": "test-model"},
            min_topics=2,
            max_topics=6,
            recommended_topics=4,
            title_max_chars=6,
            strict=True,
            chat_completion_fn=lambda _config, _messages: response,
        )

        with self.assertRaisesRegex(RuntimeError, "does not fully cover input"):
            loop.run(segments)

    def test_topic_loop_accepts_valid_draft_without_retry(self) -> None:
        segments = [
            TopicSegment(segment_id=index, start=(index - 1) * 5.0, end=index * 5.0, text=f"句子{index}")
            for index in range(1, 7)
        ]
        response = """
        {
          "topics": [
            {"block_range": "1-3", "title": "切入话题"},
            {"block_range": "4-6", "title": "解决方法"}
          ]
        }
        """

        loop = PiAgentTopicLoop(
            llm_config={"base_url": "https://example.com", "model": "test-model"},
            min_topics=2,
            max_topics=6,
            recommended_topics=2,
            title_max_chars=6,
            chat_completion_fn=lambda _config, _messages: response,
        )

        result = loop.run(segments)

        self.assertEqual(result.debug["iterations"], 1)
        self.assertEqual(result.debug["final_source"], "draft")
        self.assertEqual([topic["block_range"] for topic in result.payload["topics"]], ["1-3", "4-6"])
        self.assertEqual(result.debug["issues"], [])

    def test_topic_loop_accepts_block_ranges_in_draft(self) -> None:
        segments = [
            TopicSegment(segment_id=index, start=(index - 1) * 5.0, end=index * 5.0, text=f"句子{index}")
            for index in range(1, 7)
        ]
        response = """
        {
          "topics": [
            {"block_range": "1-3", "title": "切入话题"},
            {"block_range": "4-6", "title": "解决方法"}
          ]
        }
        """

        loop = PiAgentTopicLoop(
            llm_config={"base_url": "https://example.com", "model": "test-model"},
            min_topics=2,
            max_topics=6,
            recommended_topics=2,
            title_max_chars=6,
            chat_completion_fn=lambda _config, _messages: response,
        )

        result = loop.run(segments)

        self.assertEqual([topic["block_range"] for topic in result.payload["topics"]], ["1-3", "4-6"])

    def test_topic_loop_fails_immediately_when_invalid_json_is_returned(self) -> None:
        segments = [
            TopicSegment(segment_id=index, start=(index - 1) * 5.0, end=index * 5.0, text=f"句子{index}")
            for index in range(1, 7)
        ]
        response = """
        {
          "topics": [
            {"block_range": "1-3", "title": "切入话题"}
            {"block_range": "4-6", "title": "解决方法"}
          ]
        }
        """
        calls = 0

        def fake_chat(_config, _messages):
            nonlocal calls
            calls += 1
            return response

        loop = PiAgentTopicLoop(
            llm_config={"base_url": "https://example.com", "model": "test-model", "repair_retries": 2},
            min_topics=2,
            max_topics=6,
            recommended_topics=2,
            title_max_chars=6,
            chat_completion_fn=fake_chat,
        )

        with self.assertRaisesRegex(RuntimeError, "Failed to parse LLM JSON payload"):
            loop.run(segments)
        self.assertEqual(calls, 1)

    def test_topic_loop_non_strict_mode_no_longer_attempts_repair_follow_up_call(self) -> None:
        segments = [
            TopicSegment(segment_id=index, start=(index - 1) * 5.0, end=index * 5.0, text=f"句子{index}")
            for index in range(1, 7)
        ]
        responses = [
            """
            {
              "topics": [
                {"block_range": "1-3", "title": "切入话题"}
                {"block_range": "4-6", "title": "解决方法"}
              ]
            }
            """,
            """
            {
              "topics": [
                {"block_range": "1-3", "title": "切入话题"},
                {"block_range": "4-6", "title": "解决方法"}
              ]
            }
            """,
        ]
        calls = 0

        def fake_chat(_config, _messages):
            nonlocal calls
            reply = responses[calls]
            calls += 1
            return reply

        loop = PiAgentTopicLoop(
            llm_config={"base_url": "https://example.com", "model": "test-model", "repair_retries": 1},
            min_topics=2,
            max_topics=6,
            recommended_topics=2,
            title_max_chars=6,
            chat_completion_fn=fake_chat,
        )

        with self.assertRaisesRegex(RuntimeError, "Failed to parse LLM JSON payload"):
            loop.run(segments)
        self.assertEqual(calls, 1)

    def test_topic_loop_keeps_strict_mode_for_invalid_json(self) -> None:
        segments = [
            TopicSegment(segment_id=index, start=(index - 1) * 5.0, end=index * 5.0, text=f"句子{index}")
            for index in range(1, 7)
        ]
        response = """
        {
          "topics": [
            {"block_range": "1-3", "title": "切入话题"}
            {"block_range": "4-6", "title": "解决方法"}
          ]
        }
        """

        loop = PiAgentTopicLoop(
            llm_config={"base_url": "https://example.com", "model": "test-model"},
            min_topics=2,
            max_topics=6,
            recommended_topics=2,
            title_max_chars=6,
            strict=True,
            chat_completion_fn=lambda _config, _messages: response,
        )

        with self.assertRaisesRegex(RuntimeError, "Failed to parse LLM JSON payload"):
            loop.run(segments)

    def test_build_cut_srt_can_reindex_sequentially_for_topic_segmentation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "input.optimized.srt"
            out = Path(tmpdir) / "cut.srt"
            src.write_text(
                "\n".join(
                    [
                        "2",
                        "00:00:00,000 --> 00:00:01,000",
                        "第一句",
                        "",
                        "5",
                        "00:00:01,000 --> 00:00:02,000",
                        "第二句",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            build_cut_srt_from_optimized_srt(
                source_srt_path=str(src),
                output_srt_path=str(out),
                encoding="utf-8",
                merge_gap_s=0.0,
                preserve_input_indices=False,
            )

            subs = list(srt.parse(out.read_text(encoding="utf-8")))
            self.assertEqual([sub.index for sub in subs], [1, 2])


if __name__ == "__main__":
    unittest.main()
