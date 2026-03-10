from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from web_api.constants import JOB_STATUS_STEP2_CONFIRMED, JOB_STATUS_STEP2_READY
from web_api.services.step2 import run_step2


class Step2AutoConfirmTest(unittest.TestCase):
    def test_run_step2_auto_confirms_generated_chapters(self) -> None:
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
      "line_ids": [1]
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
        self.assertIn(JOB_STATUS_STEP2_CONFIRMED, statuses)
        self.assertNotIn(JOB_STATUS_STEP2_READY, statuses)
        self.assertEqual(statuses[-1], JOB_STATUS_STEP2_CONFIRMED)


if __name__ == "__main__":
    unittest.main()
