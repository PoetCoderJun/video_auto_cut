from __future__ import annotations

from pydantic import BaseModel, Field

MAX_TEST_CONFIRM_LINES = 5000
MAX_TEST_CONFIRM_CHAPTERS = 1000
MAX_STEP_TEXT_LENGTH = 1000
MAX_CHAPTER_TITLE_LENGTH = 120
MAX_CHAPTER_KEY_LENGTH = 128
MAX_BLOCK_RANGE_LENGTH = 64
MAX_CODE_LENGTH = 64
MAX_OBJECT_KEY_LENGTH = 1024
MAX_REVISION_LENGTH = 128
MAX_SCRIPT_LENGTH = 50000


class CreateJobRequest(BaseModel):
    script: str = Field(default="", max_length=MAX_SCRIPT_LENGTH)


class TestConfirmLine(BaseModel):
    line_id: int = Field(..., ge=1)
    optimized_text: str = Field(default="", max_length=MAX_STEP_TEXT_LENGTH)
    user_final_remove: bool


class TestConfirmChapter(BaseModel):
    chapter_key: str = Field(..., min_length=1, max_length=MAX_CHAPTER_KEY_LENGTH)
    title: str = Field(default="", max_length=MAX_CHAPTER_TITLE_LENGTH)
    start_line_id: int = Field(..., ge=1)


class TestConfirmRequest(BaseModel):
    lines: list[TestConfirmLine] = Field(
        ...,
        min_length=1,
        max_length=MAX_TEST_CONFIRM_LINES,
    )
    chapters: list[TestConfirmChapter] = Field(
        ...,
        min_length=1,
        max_length=MAX_TEST_CONFIRM_CHAPTERS,
    )
    expected_revision: str = Field(..., min_length=1, max_length=MAX_REVISION_LENGTH)


class CouponRedeemRequest(BaseModel):
    code: str = Field(default="", min_length=1, max_length=MAX_CODE_LENGTH)


class GuestSessionClaimRequest(BaseModel):
    device_fingerprint: str = Field(default="", min_length=1, max_length=1024)


class AudioOssReadyRequest(BaseModel):
    object_key: str = Field(..., min_length=1, max_length=MAX_OBJECT_KEY_LENGTH)


class ClientUploadIssueReportRequest(BaseModel):
    stage: str = Field(..., min_length=1, max_length=64)
    page: str = Field(default="", max_length=128)
    file_name: str = Field(default="", max_length=255)
    file_type: str = Field(default="", max_length=128)
    file_size_bytes: int = Field(default=0, ge=0)
    error_name: str = Field(default="", max_length=128)
    error_message: str = Field(default="", max_length=2000)
    friendly_message: str = Field(default="", max_length=1000)
    user_agent: str = Field(default="", max_length=1000)
