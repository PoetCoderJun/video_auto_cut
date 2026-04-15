from __future__ import annotations

import unittest
from unittest.mock import patch

from video_auto_cut.pi_agent_runner import SHARED_SYSTEM_PROMPT, build_pi_command, skill_paths


class PiAgentRunnerTests(unittest.TestCase):
    def test_skill_paths_only_include_three_editing_skills(self) -> None:
        paths = skill_paths()
        self.assertEqual([path.name for path in paths], ["delete", "polish", "chapter"])

    def test_build_pi_command_loads_repo_local_editing_skills_and_system_prompt(self) -> None:
        command = build_pi_command(pi_bin="pi", pi_args=["--model", "gpt-5"])
        skill_args = [command[index + 1] for index, item in enumerate(command[:-1]) if item == "--skill"]
        prompt_args = [command[index + 1] for index, item in enumerate(command[:-1]) if item == "--append-system-prompt"]
        self.assertEqual(command[0], "pi")
        self.assertIn("--no-skills", command)
        self.assertEqual(len(skill_args), 3)
        self.assertTrue(any(path.endswith("/skills/delete") for path in skill_args))
        self.assertTrue(any(path.endswith("/skills/polish") for path in skill_args))
        self.assertTrue(any(path.endswith("/skills/chapter") for path in skill_args))
        self.assertEqual(prompt_args, [SHARED_SYSTEM_PROMPT])
        self.assertEqual(command[-2:], ["--model", "gpt-5"])


if __name__ == "__main__":
    unittest.main()
