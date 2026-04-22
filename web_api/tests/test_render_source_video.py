from __future__ import annotations

import unittest
from pathlib import Path

from web_api.services.render_source_video import build_cut_source_video_command


class RenderSourceVideoTests(unittest.TestCase):
    def test_build_cut_source_video_command_preserves_resolution_and_maps_first_audio(self) -> None:
        command = build_cut_source_video_command(
            input_path=Path("/tmp/input.mov"),
            output_path=Path("/tmp/output.mp4"),
            segments=[
                {"start": 1.25, "end": 3.5},
                {"start": 6.0, "end": 9.75},
            ],
            include_audio=True,
        )

        joined = " ".join(command)
        self.assertIn("libx264", command)
        self.assertIn("aac", command)
        self.assertIn("veryfast", command)
        self.assertIn("-crf", command)
        self.assertNotIn("scale=", joined)
        self.assertIn("[0:a:0]atrim=start=1.250:end=3.500", joined)
        self.assertIn("[0:v:0]trim=start=6.000:end=9.750", joined)
        self.assertIn("concat=n=2:v=1:a=1[outv][outa]", joined)

    def test_build_cut_source_video_command_can_omit_audio(self) -> None:
        command = build_cut_source_video_command(
            input_path=Path("/tmp/input.mov"),
            output_path=Path("/tmp/output.mp4"),
            segments=[
                {"start": 0.0, "end": 2.0},
            ],
            include_audio=False,
        )

        joined = " ".join(command)
        self.assertIn("concat=n=1:v=1:a=0[outv]", joined)
        self.assertIn("-an", command)
        self.assertNotIn("atrim=", joined)


if __name__ == "__main__":
    unittest.main()
