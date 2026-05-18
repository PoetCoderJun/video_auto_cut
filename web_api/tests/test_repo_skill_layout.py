from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = REPO_ROOT / "skills"


class RepoSkillLayoutTests(unittest.TestCase):
    def test_project_skills_only_keep_direct_prompt_sources(self) -> None:
        dirs = sorted(path.name for path in SKILLS_ROOT.iterdir() if path.is_dir())
        self.assertEqual(dirs, ["direct-prompts"])

        prompt_files = sorted(path.name for path in (SKILLS_ROOT / "direct-prompts").glob("*.md"))
        self.assertEqual(
            prompt_files,
            [
                "chapter.md",
                "delete-with-reference.md",
                "delete.md",
                "highlight.md",
                "polish-with-reference.md",
                "polish.md",
            ],
        )


if __name__ == "__main__":
    unittest.main()
