from __future__ import annotations

import unittest

from video_auto_cut.pi_agent_runner import PROJECT_ROOT, build_pi_command, load_project_pi_system_prompt


class PiAgentRunnerTests(unittest.TestCase):
    def test_project_pi_settings_auto_load_repo_skills_folder(self) -> None:
        settings_text = (PROJECT_ROOT / ".pi" / "settings.json").read_text(encoding="utf-8")
        self.assertIn('"../skills"', settings_text)
        self.assertIn('"defaultThinkingLevel": "off"', settings_text)

    def test_build_pi_command_does_not_couple_backend_to_skill_or_prompt_loading(self) -> None:
        command = build_pi_command(pi_bin="pi", pi_args=["--model", "gpt-5", "-p", "hello"])
        self.assertEqual(command[0], "pi")
        self.assertNotIn("--no-skills", command)
        self.assertNotIn("--skill", command)
        self.assertNotIn("--append-system-prompt", command)
        self.assertEqual(command[-4:], ["--model", "gpt-5", "-p", "hello"])

    def test_project_pi_system_prompt_lives_in_pi_append_system_file(self) -> None:
        prompt = load_project_pi_system_prompt()
        file_text = (PROJECT_ROOT / ".pi" / "APPEND_SYSTEM.md").read_text(encoding="utf-8").strip()
        self.assertEqual(prompt, file_text)
        self.assertIn("test-agent-editing", prompt)
        self.assertNotIn("工作流：", prompt)

    def test_project_pi_extension_registers_env_backed_provider(self) -> None:
        extension_text = (PROJECT_ROOT / ".pi" / "extensions" / "project-llm-provider.ts").read_text(encoding="utf-8")
        self.assertIn('pi.registerProvider("vac-llm"', extension_text)
        self.assertIn("LLM_BASE_URL", extension_text)
        self.assertIn("LLM_API_KEY", extension_text)
        self.assertIn('id === "qwen3.6-plus"', extension_text)
        self.assertIn('thinkingFormat: isQwenReasoningModel(id) ? "qwen" : "openai"', extension_text)
        self.assertIn("streamSimple: streamVacLlm", extension_text)
        self.assertIn("streamSimpleOpenAICompletions", extension_text)
        self.assertIn("next.enable_thinking = false", extension_text)
        self.assertIn('id === "kimi-k2.5"', extension_text)
        self.assertIn("delete next.thinking", extension_text)


if __name__ == "__main__":
    unittest.main()
