"""端到端测试：Step 1 (with chunk) -> Step 1.5 -> Step 2

测试完整的字幕优化流程：
1. Step 1: LLM 删除重复行
2. Step 1.5: 合并短句字幕（<20字）
3. Step 2: LLM 润色字幕
"""

import unittest
from unittest.mock import patch

from video_auto_cut.editing.auto_edit import (
    AutoEdit,
    REMOVE_TOKEN,
    AUTO_EDIT_CHUNK_LINES,
)


class DummyArgs:
    """模拟 AutoEdit 需要的参数"""
    def __init__(self):
        self.inputs = []
        self.encoding = "utf-8"
        self.force = False
        self.auto_edit_llm = True
        self.auto_edit_merge_gap = 0.5
        self.auto_edit_pad_head = 0.0
        self.auto_edit_pad_tail = 0.0
        self.llm_base_url = "http://localhost:8000"
        self.llm_model = "test-model"
        self.llm_api_key = None
        self.llm_timeout = 60
        self.llm_temperature = 0.0
        self.llm_max_tokens = None


def make_segments(texts):
    """Helper: 从文本列表创建 segments"""
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


class TestAutoEditE2ENonChunked(unittest.TestCase):
    """非 chunked 模式的端到端测试（行数 <= AUTO_EDIT_CHUNK_LINES）"""

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_e2e_basic_flow(self, mock_chat):
        """测试基本流程：删除 -> 合并 -> 润色"""
        # 准备数据：5行，包含重复和短句
        segments = make_segments([
            "前面这句说错了",           # 将被删除（重复）
            "后面这句是正确表达",       # 保留（8字，短）
            "短句",                     # 短（<20），将合并
            "继续短",                   # 短（<20），将合并
            "这句很长不需要合并因为已经超过二十字阈值",  # 长，停止合并
        ])
        
        # Mock LLM 调用
        mock_chat.side_effect = [
            # Step 1: remove pass - 删除第1行（重复）
            "\n".join([
                f"[L0001] {REMOVE_TOKEN}",
                "[L0002] 后面这句是正确表达",
                "[L0003] 短句",
                "[L0004] 继续短",
                "[L0005] 这句很长不需要合并因为已经超过二十字阈值",
            ]),
            # Step 2: optimize pass - 润色（输入5行，输出5行）
            "\n".join([
                "[L0001] 前面这句说错了",  # LLM 尝试恢复，但会被忽略
                "[L0002] 后面这句是正确表达",
                "[L0003] 短句",
                "[L0004] 继续短",
                "[L0005] 这句很长不需要合并因为已经超过二十字阈值",
            ]),
        ]
        
        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segments(segments, total_length=10.0)
        
        subs = result["optimized_subs"]
        
        # 验证：
        # - L1 被标记为删除并保留
        # - remove 行不参与合并；L2-L5 在 remove 之后持续合并直到阈值
        # L2(8)+L3(2)+L4(3)+L5(20)=33>=20
        self.assertEqual(len(subs), 2)
        self.assertTrue(subs[0].content.startswith(REMOVE_TOKEN))
        self.assertEqual(
            subs[1].content, 
            "后面这句是正确表达，短句，继续短，这句很长不需要合并因为已经超过二十字阈值"
        )

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_e2e_with_merge(self, mock_chat):
        """测试短句合并功能"""
        segments = make_segments([
            "大家好",           # 3字 - 短
            "今天我们要聊",     # 6字 - 短
            "一个话题",         # 4字 - 短
            "关于如何提高",     # 6字 - 短（累计22字>=20，停止）
            "效率的方法",       # 5字 - 短
            "谢谢观看",         # 4字 - 短
        ])
        
        mock_chat.side_effect = [
            # Step 1: 不删除任何行
            "\n".join([f"[L{i+1:04d}] {seg['text']}" for i, seg in enumerate(segments)]),
            # Step 2: 润色（保持原样）
            "\n".join([f"[L{i+1:04d}] {seg['text']}" for i, seg in enumerate(segments)]),
        ]
        
        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segments(segments, total_length=10.0)
        
        subs = result["optimized_subs"]
        
        # L1-L4: 3+6+4+6=19字 + 3个逗号=22字 >=20，合并成1行
        # L5-L6: 5+4=9字 + 1个逗号=10字 <20，但无更多行，合并成1行
        self.assertEqual(len(subs), 2)
        
        # 验证第1行是 L1-L4 合并
        expected_merged = "大家好，今天我们要聊，一个话题，关于如何提高"
        self.assertEqual(subs[0].content, expected_merged)
        # 时间戳应该覆盖 L1-L4
        self.assertAlmostEqual(subs[0].start.total_seconds(), 0.0)
        self.assertAlmostEqual(subs[0].end.total_seconds(), 4.6)  # L4 的 end
        
        # 验证第2行是 L5-L6 合并
        self.assertEqual(subs[1].content, "效率的方法，谢谢观看")

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_e2e_remove_then_merge(self, mock_chat):
        """测试删除后再合并的场景"""
        segments = make_segments([
            "这句要删除",       # 将被删除
            "短句一",           # 短
            "短句二",           # 短
            "这句很长不需要合并因为已经超过二十字阈值",  # 长
        ])
        
        mock_chat.side_effect = [
            # Step 1: 删除第1行
            "\n".join([
                f"[L0001] {REMOVE_TOKEN}",
                "[L0002] 短句一",
                "[L0003] 短句二",
                "[L0004] 这句很长不需要合并因为已经超过二十字阈值",
            ]),
            # Step 2: 润色（输入4行，输出4行）
            "\n".join([
                "[L0001] 这句要删除",  # LLM 尝试恢复
                "[L0002] 短句一",
                "[L0003] 短句二",
                "[L0004] 这句很长不需要合并因为已经超过二十字阈值",
            ]),
        ]
        
        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segments(segments, total_length=10.0)
        
        subs = result["optimized_subs"]
        
        # remove 行保留；L2+L3+L4 合并（4+4+20=28>=20）
        self.assertEqual(len(subs), 2)
        self.assertTrue(subs[0].content.startswith(REMOVE_TOKEN))
        self.assertEqual(
            subs[1].content, 
            "短句一，短句二，这句很长不需要合并因为已经超过二十字阈值"
        )

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_e2e_remove_line_kept_and_blocks_cross_merge(self, mock_chat):
        """Step 1.5 must keep remove line and never merge across it."""
        segments = make_segments(
            [
                "短句一",
                "这句要删除",
                "短句二",
                "这句很长不需要合并因为已经超过二十字阈值",
            ]
        )

        mock_chat.side_effect = [
            "\n".join(
                [
                    "[L0001] 短句一",
                    f"[L0002] {REMOVE_TOKEN}",
                    "[L0003] 短句二",
                    "[L0004] 这句很长不需要合并因为已经超过二十字阈值",
                ]
            ),
            "\n".join(
                [
                    "[L0001] 短句一",
                    "[L0002] 这句要删除",
                    "[L0003] 短句二",
                    "[L0004] 这句很长不需要合并因为已经超过二十字阈值",
                ]
            ),
        ]

        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segments(segments, total_length=10.0)
        subs = result["optimized_subs"]

        self.assertEqual(len(subs), 3)
        self.assertEqual(subs[0].content, "短句一")
        self.assertTrue(subs[1].content.startswith(REMOVE_TOKEN))
        self.assertEqual(
            subs[2].content,
            "短句二，这句很长不需要合并因为已经超过二十字阈值",
        )

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_e2e_low_speech_line_marked_remove_and_kept(self, mock_chat):
        """< Low Speech > should be deterministically removed but still kept as a line."""
        segments = make_segments(
            [
                "< Low Speech >",
                "短句一",
                "这句很长不需要合并因为已经超过二十字阈值",
            ]
        )

        # 即使 LLM 未输出 remove，规则也应把 low speech 标成 remove。
        mock_chat.side_effect = [
            "\n".join(
                [
                    "[L0001] < Low Speech >",
                    "[L0002] 短句一",
                    "[L0003] 这句很长不需要合并因为已经超过二十字阈值",
                ]
            ),
            "\n".join(
                [
                    "[L0001] < Low Speech >",
                    "[L0002] 短句一",
                    "[L0003] 这句很长不需要合并因为已经超过二十字阈值",
                ]
            ),
        ]

        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segments(segments, total_length=10.0)
        subs = result["optimized_subs"]

        self.assertEqual(len(subs), 2)
        self.assertTrue(subs[0].content.startswith(REMOVE_TOKEN))
        self.assertEqual(subs[1].content, "短句一，这句很长不需要合并因为已经超过二十字阈值")


class TestAutoEditE2EChunked(unittest.TestCase):
    """Chunked 模式的端到端测试（行数 > AUTO_EDIT_CHUNK_LINES）"""

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_e2e_chunked_then_merge(self, mock_chat):
        """测试 chunked 处理后再合并"""
        # 创建超过 AUTO_EDIT_CHUNK_LINES 行的数据
        chunk_size = AUTO_EDIT_CHUNK_LINES  # 30
        total_lines = chunk_size + 10  # 40行，会分成2个 chunk
        
        segments = make_segments([
            "短句" if i % 2 == 0 else "这句很长不需要合并因为已经超过二十字阈值"
            for i in range(total_lines)
        ])
        
        # 准备 mock 返回值
        # 每个 chunk 会调用 2 次 LLM（remove + optimize）
        def make_chunk_response(start_idx, count):
            """为一个 chunk 创建 LLM 响应"""
            # remove pass - 删除所有偶数行
            remove_lines = []
            for i in range(count):
                line_num = start_idx + i
                if (start_idx + i) % 2 == 0:  # 偶数行删除
                    remove_lines.append(f"[L{i+1:04d}] {REMOVE_TOKEN}")
                else:
                    remove_lines.append(f"[L{i+1:04d}] 这句很长不需要合并因为已经超过二十字阈值")
            
            # optimize pass - 保持原样（只返回保留的行）
            optimize_lines = [
                f"[L{i+1:04d}] 这句很长不需要合并因为已经超过二十字阈值"
                for i in range(count) if (start_idx + i) % 2 != 0
            ]
            
            return "\n".join(remove_lines), "\n".join(optimize_lines)
        
        # Chunk 1: 第1-34行（30行core + 4行overlap）
        remove1, optimize1 = make_chunk_response(1, 34)
        # Chunk 2: 第27-40行（10行core + 4行左overlap）
        remove2, optimize2 = make_chunk_response(27, 14)
        
        mock_chat.side_effect = [
            remove1, optimize1,   # Chunk 1
            remove2, optimize2,   # Chunk 2
        ]
        
        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segments(segments, total_length=50.0)
        
        subs = result["optimized_subs"]
        
        # 验证：
        # - 原始40行中，偶数行会被标记删除并保留
        # - remove 行作为边界，奇数长句不再与其他行合并
        # - 最终保留40行（20 remove + 20 长句）
        self.assertEqual(len(subs), 40)

        remove_count = sum(1 for sub in subs if sub.content.startswith(REMOVE_TOKEN))
        self.assertEqual(remove_count, 20)


class TestAutoEditE2EEdgeCases(unittest.TestCase):
    """边界情况的端到端测试"""

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_e2e_all_short_lines(self, mock_chat):
        """测试全是短句的情况"""
        segments = make_segments([
            "短句一",
            "短句二", 
            "短句三",
            "短句四",
        ])
        
        mock_chat.side_effect = [
            # Step 1
            "\n".join([f"[L{i+1:04d}] {seg['text']}" for i, seg in enumerate(segments)]),
            # Step 2
            "\n".join([f"[L{i+1:04d}] {seg['text']}" for i, seg in enumerate(segments)]),
        ]
        
        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segments(segments, total_length=10.0)
        
        subs = result["optimized_subs"]
        
        # 所有短句持续合并，直到最后一行
        # 3+3+3+3=12字 < 20，所以全部合并成1行
        self.assertEqual(len(subs), 1)
        self.assertEqual(subs[0].content, "短句一，短句二，短句三，短句四")

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_e2e_all_long_lines(self, mock_chat):
        """测试全是长句的情况（不需要合并）"""
        segments = make_segments([
            "这句很长不需要合并因为已经超过二十字阈值第一行",
            "这句很长不需要合并因为已经超过二十字阈值第二行",
            "这句很长不需要合并因为已经超过二十字阈值第三行",
        ])
        
        mock_chat.side_effect = [
            "\n".join([f"[L{i+1:04d}] {seg['text']}" for i, seg in enumerate(segments)]),
            "\n".join([f"[L{i+1:04d}] {seg['text']}" for i, seg in enumerate(segments)]),
        ]
        
        editor = AutoEdit(DummyArgs())
        result = editor._auto_edit_segments(segments, total_length=10.0)
        
        subs = result["optimized_subs"]
        
        # 所有行都 >=20字，不需要合并
        self.assertEqual(len(subs), 3)

    @patch("video_auto_cut.editing.auto_edit.llm_utils.chat_completion")
    def test_e2e_all_removed(self, mock_chat):
        """测试所有行都被删除的情况"""
        segments = make_segments([
            "这句要删除",
            "这句也要删除",
        ])
        
        # 即使全部删除，Step 2 仍会被调用（返回空会报错）
        # 实际上在 _auto_edit_segment_chunk 中，如果都删除了
        # kept_segments 为空，会在 _auto_edit_segments 中抛出异常
        mock_chat.side_effect = [
            "\n".join([
                f"[L0001] {REMOVE_TOKEN}",
                f"[L0002] {REMOVE_TOKEN}",
            ]),
            "\n".join([
                "[L0001] 这句要删除",
                "[L0002] 这句也要删除",
            ]),
        ]
        
        editor = AutoEdit(DummyArgs())
        
        # 应该抛出异常
        with self.assertRaises(RuntimeError) as ctx:
            editor._auto_edit_segments(segments, total_length=5.0)
        
        self.assertIn("All segments removed", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
