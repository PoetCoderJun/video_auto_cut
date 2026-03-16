from __future__ import annotations

import asyncio
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import UploadFile

from video_auto_cut.asr.oss_uploader import UploadedAudioObject
from web_api.constants import JOB_STATUS_UPLOAD_READY, PROGRESS_UPLOAD_READY
from web_api.services.jobs import save_uploaded_audio


class _FakeUploader:
    def __init__(self) -> None:
        self.last_path: Path | None = None
        self.last_job_id: str | None = None

    def upload_audio(self, local_path: Path, *, job_id: str | None = None) -> UploadedAudioObject:
        path = Path(local_path)
        if not path.exists():
            raise AssertionError(f"temp upload file missing: {path}")
        self.last_path = path
        self.last_job_id = job_id
        return UploadedAudioObject(
            object_key=f"video-auto-cut/asr/{job_id}/audio.wav",
            signed_url="https://example.com/fake.wav",
            size_bytes=path.stat().st_size,
        )


class JobsAudioUploadTest(unittest.TestCase):
    def test_save_uploaded_audio_uploads_to_oss_and_only_records_asr_key(self) -> None:
        upload = UploadFile(filename="audio.wav", file=io.BytesIO(b"audio-bytes"))
        fake_uploader = _FakeUploader()

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch(
                    "web_api.services.jobs.get_settings",
                    return_value=SimpleNamespace(max_upload_mb=10),
                ),
                patch(
                    "web_api.services.jobs.ensure_job_dirs",
                    return_value={"input": Path(tmpdir)},
                ),
                patch(
                    "web_api.services.jobs.get_oss_uploader",
                    return_value=fake_uploader,
                ),
                patch("web_api.services.jobs.upsert_job_files") as mock_upsert_job_files,
                patch("web_api.services.jobs.update_job") as mock_update_job,
            ):
                result = asyncio.run(save_uploaded_audio("job_123", upload))

        self.assertEqual(result["object_key"], "video-auto-cut/asr/job_123/audio.wav")
        self.assertEqual(result["size_bytes"], len(b"audio-bytes"))
        self.assertEqual(fake_uploader.last_job_id, "job_123")
        self.assertIsNotNone(fake_uploader.last_path)
        self.assertFalse(fake_uploader.last_path.exists())

        mock_upsert_job_files.assert_called_once()
        self.assertEqual(
            mock_upsert_job_files.call_args.kwargs,
            {
                "audio_path": None,
                "asr_oss_key": "video-auto-cut/asr/job_123/audio.wav",
            },
        )
        mock_update_job.assert_called_once_with(
            "job_123",
            status=JOB_STATUS_UPLOAD_READY,
            progress=PROGRESS_UPLOAD_READY,
            stage_code="UPLOAD_COMPLETE",
            stage_message="上传完成，正在启动语音转写...",
        )


if __name__ == "__main__":
    unittest.main()
