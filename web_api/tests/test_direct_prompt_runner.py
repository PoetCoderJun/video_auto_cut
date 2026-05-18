from __future__ import annotations

import unittest

from video_auto_cut.direct_prompt_runner import PROJECT_ROOT
from video_auto_cut.orchestration.test_cli import main as direct_prompt_cli_main


class DirectPromptRunnerCleanupTests(unittest.TestCase):
    def test_project_no_longer_carries_pi_runtime_config(self) -> None:
        self.assertFalse((PROJECT_ROOT / ".pi").exists())

    def test_project_no_longer_carries_pi_runner_module(self) -> None:
        self.assertFalse((PROJECT_ROOT / "video_auto_cut" / "pi_agent_runner.py").exists())

    def test_direct_prompt_runner_has_no_pi_provider_routing_or_cli_passthrough(self) -> None:
        runner_text = (PROJECT_ROOT / "video_auto_cut" / "direct_prompt_runner.py").read_text(encoding="utf-8")
        self.assertNotIn("PI_PROVIDER", runner_text)
        self.assertNotIn("KIMI_CODING_PROVIDER", runner_text)
        self.assertNotIn("build_pi_command", runner_text)

    def test_cli_requires_explicit_direct_prompt_task(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "--task is required"):
            direct_prompt_cli_main([])


if __name__ == "__main__":
    unittest.main()
