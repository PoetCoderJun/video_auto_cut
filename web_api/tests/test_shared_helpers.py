from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from video_auto_cut.shared.dotenv import auto_load_dotenv
from web_api.utils.common import new_request_id


class SharedHelpersTest(unittest.TestCase):
    def test_auto_load_dotenv_loads_first_existing_candidate_without_overwriting(self) -> None:
        original_keep = os.environ.get("KEEP_ME")
        original_loaded = os.environ.get("LOADED_VALUE")
        try:
            os.environ["KEEP_ME"] = "preserved"
            os.environ.pop("LOADED_VALUE", None)

            with tempfile.TemporaryDirectory() as tmpdir:
                root = Path(tmpdir)
                first = root / ".env.first"
                second = root / ".env.second"
                second.write_text(
                    'KEEP_ME="replaced"\nLOADED_VALUE=\'loaded\'\n',
                    encoding="utf-8",
                )

                loaded = auto_load_dotenv([first, second])

            self.assertTrue(loaded)
            self.assertEqual(os.environ.get("KEEP_ME"), "preserved")
            self.assertEqual(os.environ.get("LOADED_VALUE"), "loaded")
        finally:
            if original_keep is None:
                os.environ.pop("KEEP_ME", None)
            else:
                os.environ["KEEP_ME"] = original_keep
            if original_loaded is None:
                os.environ.pop("LOADED_VALUE", None)
            else:
                os.environ["LOADED_VALUE"] = original_loaded

    def test_new_request_id_uses_req_prefix_and_short_hex_suffix(self) -> None:
        request_id = new_request_id()
        self.assertRegex(request_id, r"^req_[0-9a-f]{10}$")
