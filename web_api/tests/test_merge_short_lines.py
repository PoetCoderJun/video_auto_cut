"""Tests for _merge_short_lines function in auto_edit module."""

import unittest
import datetime

import srt

from video_auto_cut.editing.auto_edit import (
    AutoEdit,
    REMOVE_TOKEN,
    _merge_short_lines,
    MERGE_SHORT_LINES_THRESHOLD,
)


class DummyArgs:
    def __init__(self) -> None:
        self.inputs = []
        self.encoding = "utf-8"
        self.force = False
        self.auto_edit_llm = True
        self.auto_edit_merge_gap = 0.5
        self.auto_edit_pad_head = 0.0
        self.auto_edit_pad_tail = 0.0
        self.auto_edit_topics = False
        self.topic_strict = False
        self.topic_output = None
        self.llm_base_url = "http://localhost:8000"
        self.llm_model = "test-model"
        self.llm_api_key = None
        self.llm_timeout = 60
        self.llm_temperature = 0.0
        self.llm_max_tokens = None
        self.auto_edit_llm_concurrency = 1


class TestMergeShortLines(unittest.TestCase):
    """Test cases for the _merge_short_lines function."""

    def _make_segments(self, texts):
        """Helper to create segments from text list."""
        segments = []
        start = 0.0
        for i, text in enumerate(texts):
            duration = 1.0
            segments.append({
                "id": i + 1,
                "start": start,
                "end": start + duration,
                "duration": duration,
                "text": text,
            })
            start += duration + 0.2
        return segments

    def test_no_merge_when_all_long_enough(self):
        """Test that no merging occurs when all lines are above threshold."""
        texts = [
            "这是一句足够长的字幕文本，超过了二十个字的阈值",
            "这也是一句很长的字幕文本内容，不需要合并",
            "第三句同样是很长的文本，超过了阈值限制",
        ]
        segments = self._make_segments(texts)
        remove_flags = [False, False, False]

        merged = _merge_short_lines(segments, remove_flags, threshold=20)

        # 行数不变
        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[0]["text"], texts[0])
        self.assertEqual(merged[1]["text"], texts[1])
        self.assertEqual(merged[2]["text"], texts[2])

    def test_merge_short_line_with_next(self):
        """Test that short lines are merged with the next line."""
        texts = [
            "短句",  # 2 chars, < 20
            "这是一句很长的字幕文本内容，超过了二十个字的阈值",
            "正常长度的文本",
        ]
        segments = self._make_segments(texts)
        remove_flags = [False, False, False]

        merged = _merge_short_lines(segments, remove_flags, threshold=20)

        # 两行变成一行，短句和下一行合并
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["text"], "短句，这是一句很长的字幕文本内容，超过了二十个字的阈值")
        self.assertEqual(merged[1]["text"], texts[2])
        
        # Check time merging
        self.assertEqual(merged[0]["start"], segments[0]["start"])
        self.assertEqual(merged[0]["end"], segments[1]["end"])

    def test_merge_skips_removed_lines(self):
        """Test that already removed lines are skipped during merge."""
        texts = [
            "短句",  # 2 chars
            "<<REMOVE>>",  # Already removed
            "这是保留的行",
        ]
        segments = self._make_segments(texts)
        remove_flags = [False, True, False]

        merged = _merge_short_lines(segments, remove_flags, threshold=20)

        # 短句应该与第3行合并（跳过第2行），最终只剩1行
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["text"], "短句，这是保留的行")

    def test_short_last_line_not_merged(self):
        """Test that short last line is not merged (no next line to merge with)."""
        texts = [
            "这是一句很长的字幕文本内容，超过了二十个字的阈值",
            "短句",  # Last line, short
        ]
        segments = self._make_segments(texts)
        remove_flags = [False, False]

        merged = _merge_short_lines(segments, remove_flags, threshold=20)

        # 两行都保留
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["text"], texts[0])
        self.assertEqual(merged[1]["text"], texts[1])

    def test_chain_merge(self):
        """Test continuous merging: short lines keep merging until threshold reached."""
        texts = [
            "短",      # 1 char
            "句",      # 1 char
            "合并",    # 2 chars
            "这句足够长不需要再合并了因为已经超过阈值",  # 20 chars
        ]
        segments = self._make_segments(texts)
        remove_flags = [False, False, False, False]

        merged = _merge_short_lines(segments, remove_flags, threshold=20)

        # All short lines keep merging until reaching the long one
        # Total: 1+1+2+20 = 24 chars > 20, so all merged into 1 line
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["text"], "短，句，合并，这句足够长不需要再合并了因为已经超过阈值")

    def test_multiple_merges(self):
        """Test multiple independent merges."""
        texts = [
            "短句一",  # short
            "这句很长超过了二十个字的阈值限制",
            "短二",    # short
            "这句同样很长不需要合并",
        ]
        segments = self._make_segments(texts)
        remove_flags = [False, False, False, False]

        merged = _merge_short_lines(segments, remove_flags, threshold=20)

        # 1+2 合并，3+4 合并，最终2行
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["text"], "短句一，这句很长超过了二十个字的阈值限制")
        self.assertEqual(merged[1]["text"], "短二，这句同样很长不需要合并")

    def test_default_threshold(self):
        """Test that default threshold is 20."""
        self.assertEqual(MERGE_SHORT_LINES_THRESHOLD, 20)


class TestMergeShortLinesInSubs(unittest.TestCase):
    """Tests for Step 1.5 behavior in _merge_short_lines_in_subs."""

    @staticmethod
    def _make_sub(index: int, start: float, end: float, content: str) -> srt.Subtitle:
        return srt.Subtitle(
            index=index,
            start=datetime.timedelta(seconds=start),
            end=datetime.timedelta(seconds=end),
            content=content,
        )

    def test_keep_remove_line_and_block_cross_merge(self):
        editor = AutoEdit(DummyArgs())
        subs = [
            self._make_sub(1, 0.0, 1.0, "短句一"),
            self._make_sub(2, 1.2, 2.2, f"{REMOVE_TOKEN} 这句要删除"),
            self._make_sub(3, 2.4, 3.4, "短句二"),
            self._make_sub(4, 3.6, 4.6, "这句很长不需要合并因为已经超过二十字阈值"),
        ]
        segments = [
            {"start": 0.0, "end": 1.0},
            {"start": 1.2, "end": 2.2},
            {"start": 2.4, "end": 3.4},
            {"start": 3.6, "end": 4.6},
        ]

        merged_subs, merged_segments = editor._merge_short_lines_in_subs(subs, segments, threshold=20)

        self.assertEqual(len(merged_subs), 3)
        self.assertEqual(merged_subs[0].content, "短句一")
        self.assertTrue(merged_subs[1].content.startswith(REMOVE_TOKEN))
        self.assertEqual(merged_subs[2].content, "短句二，这句很长不需要合并因为已经超过二十字阈值")

        # remove 行不进入 EDL segments
        self.assertEqual(len(merged_segments), 2)
        self.assertEqual(merged_segments[0]["start"], 0.0)
        self.assertEqual(merged_segments[0]["end"], 1.0)
        self.assertEqual(merged_segments[1]["start"], 2.4)
        self.assertEqual(merged_segments[1]["end"], 4.6)

    def test_all_remove_lines_are_kept_in_subs(self):
        editor = AutoEdit(DummyArgs())
        subs = [
            self._make_sub(1, 0.0, 1.0, f"{REMOVE_TOKEN} A"),
            self._make_sub(2, 1.2, 2.2, f"{REMOVE_TOKEN} B"),
        ]
        segments = [
            {"start": 0.0, "end": 1.0},
            {"start": 1.2, "end": 2.2},
        ]

        merged_subs, merged_segments = editor._merge_short_lines_in_subs(subs, segments, threshold=20)

        self.assertEqual(len(merged_subs), 2)
        self.assertTrue(all(sub.content.startswith(REMOVE_TOKEN) for sub in merged_subs))
        self.assertEqual(merged_segments, [])

    def test_merge_reuses_existing_comma_without_double_punctuation(self):
        editor = AutoEdit(DummyArgs())
        subs = [
            self._make_sub(1, 0.0, 1.0, "字幕也完成了润色，"),
            self._make_sub(2, 1.2, 2.2, "章节进度条自动生成，"),
        ]
        segments = [
            {"start": 0.0, "end": 1.0},
            {"start": 1.2, "end": 2.2},
        ]

        merged_subs, _ = editor._merge_short_lines_in_subs(subs, segments, threshold=20)

        self.assertEqual(len(merged_subs), 1)
        self.assertEqual(merged_subs[0].content, "字幕也完成了润色，章节进度条自动生成")

    def test_merge_uses_comma_for_non_question(self):
        editor = AutoEdit(DummyArgs())
        subs = [
            self._make_sub(1, 0.0, 1.0, "使用门槛有点高。"),
            self._make_sub(2, 1.2, 2.2, "所以这几天我用AI把它做成一个网页版，"),
        ]
        segments = [
            {"start": 0.0, "end": 1.0},
            {"start": 1.2, "end": 2.2},
        ]

        merged_subs, _ = editor._merge_short_lines_in_subs(subs, segments, threshold=20)

        self.assertEqual(len(merged_subs), 1)
        self.assertEqual(merged_subs[0].content, "使用门槛有点高，所以这几天我用AI把它做成一个网页版")

    def test_merge_keeps_question_mark_boundary(self):
        editor = AutoEdit(DummyArgs())
        subs = [
            self._make_sub(1, 0.0, 1.0, "你知道为什么吗？"),
            self._make_sub(2, 1.2, 2.2, "因为这里要保留问句"),
        ]
        segments = [
            {"start": 0.0, "end": 1.0},
            {"start": 1.2, "end": 2.2},
        ]

        merged_subs, _ = editor._merge_short_lines_in_subs(subs, segments, threshold=20)

        self.assertEqual(len(merged_subs), 1)
        self.assertEqual(merged_subs[0].content, "你知道为什么吗？因为这里要保留问句")


if __name__ == "__main__":
    unittest.main()
