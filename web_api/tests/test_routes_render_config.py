from __future__ import annotations

import unittest
from unittest.mock import patch

from web_api.api.routes import render_config
from web_api.errors import ApiError
from web_api.services.auth import CurrentUser


class RenderConfigRouteTest(unittest.TestCase):
    @patch("web_api.api.routes.build_web_render_config")
    @patch("web_api.api.routes.has_available_credits", return_value=True)
    @patch("web_api.api.routes.require_status")
    @patch("web_api.api.routes.load_job_or_404")
    def test_render_config_maps_dimension_validation_to_api_error(
        self,
        mock_load_job,
        mock_require_status,
        mock_has_credits,
        mock_build_config,
    ) -> None:
        mock_load_job.return_value = {"job_id": "job-1", "status": "STEP1_CONFIRMED"}
        mock_build_config.side_effect = ValueError("视频分辨率无效，请重新选择源文件后重试")

        with self.assertRaises(ApiError) as raised:
            render_config(
                "job-1",
                width=0,
                height=0,
                current_user=CurrentUser(user_id="user-1", email="user@example.com", account="user"),
            )

        self.assertEqual(raised.exception.code, "INVALID_STEP_STATE")
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.message, "视频分辨率无效，请重新选择源文件后重试")
        mock_load_job.assert_called_once_with("job-1", "user-1")
        mock_require_status.assert_called_once()
        mock_has_credits.assert_called_once_with("user-1", required=1)


if __name__ == "__main__":
    unittest.main()
