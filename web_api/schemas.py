from __future__ import annotations

from pydantic import BaseModel, Field

MAX_STEP1_CONFIRM_LINES = 5000
MAX_STEP1_CONFIRM_CHAPTERS = 1000
MAX_STEP_TEXT_LENGTH = 1000
MAX_CHAPTER_TITLE_LENGTH = 120
MAX_BLOCK_RANGE_LENGTH = 64
MAX_CODE_LENGTH = 64
MAX_OBJECT_KEY_LENGTH = 1024
MAX_REVISION_LENGTH = 128


class Step1ConfirmLine(BaseModel):
    line_id: int = Field(..., ge=1)
    optimized_text: str = Field(default="", max_length=MAX_STEP_TEXT_LENGTH)
    user_final_remove: bool


class Step1ConfirmChapter(BaseModel):
    chapter_id: int = Field(..., ge=1)
    title: str = Field(default="", max_length=MAX_CHAPTER_TITLE_LENGTH)
    block_range: str = Field(default="", min_length=1, max_length=MAX_BLOCK_RANGE_LENGTH)


class Step1ConfirmRequest(BaseModel):
    lines: list[Step1ConfirmLine] = Field(
        ...,
        min_length=1,
        max_length=MAX_STEP1_CONFIRM_LINES,
    )
    chapters: list[Step1ConfirmChapter] = Field(
        ...,
        min_length=1,
        max_length=MAX_STEP1_CONFIRM_CHAPTERS,
    )
    expected_revision: str = Field(..., min_length=1, max_length=MAX_REVISION_LENGTH)


class CouponRedeemRequest(BaseModel):
    code: str = Field(default="", min_length=1, max_length=MAX_CODE_LENGTH)


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
