from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / "skills"


class RepoSkillLayoutTests(unittest.TestCase):
    def test_asr_transcribe_skill_is_doc_first_and_script_free(self) -> None:
        skill_dir = SKILLS_ROOT / "asr-transcribe"
        self.assertTrue((skill_dir / "SKILL.md").exists())
        self.assertFalse((skill_dir / "scripts").exists())

    def test_asr_transcribe_skill_points_to_module_cli(self) -> None:
        text = (SKILLS_ROOT / "asr-transcribe" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("python -m video_auto_cut.asr.transcribe_stage", text)
        self.assertNotIn("skills/asr-transcribe/scripts/run_asr_transcribe.py", text)


if __name__ == "__main__":
    unittest.main()
