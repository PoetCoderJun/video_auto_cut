from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class StartWebMvpScriptTest(unittest.TestCase):
    def test_local_only_mode_skips_turso_env_gate(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        script_path = repo_root / "scripts" / "start_web_mvp.sh"
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)

        env = os.environ.copy()
        env.pop("TURSO_DATABASE_URL", None)
        env.pop("TURSO_AUTH_TOKEN", None)
        env["WEB_DB_LOCAL_ONLY"] = "1"
        env["WEB_AUTH_ENABLED"] = "0"
        env["WORK_DIR"] = tmpdir.name
        env["PYTHON_BIN"] = "definitely-not-a-python-binary"

        result = subprocess.run(
            ["bash", str(script_path), "debug"],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        combined_output = f"{result.stdout}\n{result.stderr}"
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WEB_DB_LOCAL_ONLY enabled", combined_output)
        self.assertIn("python not found", combined_output)
        self.assertNotIn("TURSO_DATABASE_URL is required", combined_output)
        self.assertNotIn("TURSO_AUTH_TOKEN is required", combined_output)


if __name__ == "__main__":
    unittest.main()
