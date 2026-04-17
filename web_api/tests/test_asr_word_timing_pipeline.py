from __future__ import annotations

import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

import srt

from video_auto_cut.asr.word_timing_sidecar import (
    build_sidecar_from_dashscope_payload,
    load_sidecar,
    write_sidecar,
)
from web_api.services.render_word_timing import attach_remapped_tokens_to_captions


RAW_CASE_PATH = Path(__file__).resolve().parents[2] / "test_data" / "media" / "1.dashscope.raw.json"


class AsrWordTimingPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw_payload = json.loads(RAW_CASE_PATH.read_text(encoding="utf-8"))

    def test_build_sidecar_from_dashscope_payload_uses_real_fixture(self) -> None:
        sidecar = build_sidecar_from_dashscope_payload(
            self.raw_payload,
            asset_id="fixture-case",
            upstream_task_id="task-fixture",
        )

        self.assertIsNotNone(sidecar)
        assert sidecar is not None
        self.assertEqual(sidecar["source"], "dashscope")
        self.assertEqual(len(sidecar["sentences"]), 20)
        self.assertEqual(len(sidecar["words"]), 709)
        self.assertEqual(sidecar["sentences"][0]["text"], "哟，这里是俊。")
        first_sentence = sidecar["sentences"][0]
        sentence_words = sidecar["words"][
            first_sentence["word_start_index"] : first_sentence["word_end_index"] + 1
        ]
        self.assertEqual(
            "".join(f"{item['text']}{item['punct']}" for item in sentence_words),
            first_sentence["text"],
        )

    def test_attach_remapped_tokens_to_captions_uses_single_fuzzy_mapping_with_real_fixture(self) -> None:
        sidecar = build_sidecar_from_dashscope_payload(self.raw_payload, asset_id="fixture-case")
        assert sidecar is not None
        with tempfile.TemporaryDirectory() as tmpdir:
            sidecar_path = write_sidecar(Path(tmpdir) / "fixture.asr.words.json", sidecar)
            sentence = sidecar["sentences"][0]
            caption_duration = round((sentence["end_ms"] - sentence["start_ms"]) / 1000.0, 3)
            kept_subtitle = srt.Subtitle(
                index=1,
                start=timedelta(seconds=sentence["start_ms"] / 1000.0),
                end=timedelta(seconds=sentence["end_ms"] / 1000.0),
                content=sentence["text"],
            )
            captions = [
                {
                    "index": 1,
                    "start": 0.0,
                    "end": caption_duration,
                    "text": sentence["text"],
                }
            ]
            segments = [
                {
                    "start": sentence["start_ms"] / 1000.0,
                    "end": sentence["end_ms"] / 1000.0,
                }
            ]

            remapped = attach_remapped_tokens_to_captions(
                captions=captions,
                kept_subtitles=[kept_subtitle],
                segments=segments,
                sidecar_path=str(sidecar_path),
            )

        self.assertEqual(remapped[0]["alignmentMode"], "fuzzy")
        tokens = remapped[0]["tokens"]
        self.assertEqual([token["text"] for token in tokens[:5]], ["哟，", "这", "里", "是", "俊。"])
        self.assertEqual([token["sourceWordIndex"] for token in tokens[:5]], [0, 1, 2, 3, 4])
        self.assertEqual(tokens[0]["start"], 0.0)
        self.assertEqual(tokens[-1]["end"], caption_duration)
        self.assertTrue(all(tokens[index]["end"] <= tokens[index + 1]["start"] or tokens[index]["end"] == tokens[index + 1]["start"] for index in range(len(tokens) - 1)))

    def test_attach_remapped_tokens_to_captions_still_uses_fuzzy_mapping_when_text_changes(self) -> None:
        sidecar = build_sidecar_from_dashscope_payload(self.raw_payload, asset_id="fixture-case")
        assert sidecar is not None
        with tempfile.TemporaryDirectory() as tmpdir:
            sidecar_path = write_sidecar(Path(tmpdir) / "fixture.asr.words.json", sidecar)
            sentence = sidecar["sentences"][0]
            caption_duration = round((sentence["end_ms"] - sentence["start_ms"]) / 1000.0, 3)
            kept_subtitle = srt.Subtitle(
                index=1,
                start=timedelta(seconds=sentence["start_ms"] / 1000.0),
                end=timedelta(seconds=sentence["end_ms"] / 1000.0),
                content="这里先给结论。",
            )
            remapped = attach_remapped_tokens_to_captions(
                captions=[{"index": 1, "start": 0.0, "end": caption_duration, "text": "这里先给结论。"}],
                kept_subtitles=[kept_subtitle],
                segments=[{"start": sentence["start_ms"] / 1000.0, "end": sentence["end_ms"] / 1000.0}],
                sidecar_path=str(sidecar_path),
            )

        self.assertEqual(remapped[0]["alignmentMode"], "fuzzy")
        self.assertEqual("".join(token["text"] for token in remapped[0]["tokens"]), "这里先给结论。")
        self.assertEqual(remapped[0]["tokens"][0]["start"], 0.0)
        self.assertEqual(remapped[0]["tokens"][-1]["end"], caption_duration)
        self.assertTrue(all("sourceWordIndex" in token for token in remapped[0]["tokens"]))

    def test_load_sidecar_filters_invalid_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            sidecar_path = Path(tmpdir) / "broken.asr.words.json"
            sidecar_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "words": [
                            {"index": 0, "text": "好", "start_ms": 0, "end_ms": 100, "punct": ""},
                            {"index": 1, "text": "坏", "start_ms": 100, "end_ms": 90, "punct": ""},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            payload = load_sidecar(sidecar_path)

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(len(payload["words"]), 1)


if __name__ == "__main__":
    unittest.main()
