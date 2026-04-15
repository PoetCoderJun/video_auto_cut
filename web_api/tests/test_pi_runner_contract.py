from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from video_auto_cut.pi_agent_runner import Step1PiRequest, run_step1_pi


class Step1PiRunnerContractTests(unittest.TestCase):
    @patch("video_auto_cut.editing.llm_client.chat_completion")
    def test_delete_contract_requires_all_line_ids(self, mock_chat) -> None:
        mock_chat.return_value = json.dumps(
            {"lines": [{"line_id": 1, "action": "KEEP", "reason": "保留"}]},
            ensure_ascii=False,
        )
        with self.assertRaisesRegex(RuntimeError, "delete output must cover all line ids exactly once"):
            run_step1_pi(
                Step1PiRequest(
                    task="delete",
                    llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                    segments=[
                        {"id": 1, "start": 0.0, "end": 1.0, "text": "第一句"},
                        {"id": 2, "start": 1.0, "end": 2.0, "text": "第二句"},
                    ],
                )
            )

    def test_unknown_task_fails_fast(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Unsupported Step1 PI task"):
            run_step1_pi(
                Step1PiRequest(  # type: ignore[arg-type]
                    task="unknown",
                    llm_config={"base_url": "http://x", "model": "m", "api_key": "k"},
                )
            )


if __name__ == "__main__":
    unittest.main()
