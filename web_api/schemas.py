from __future__ import annotations

from pydantic import BaseModel, Field


class Step1ConfirmLine(BaseModel):
    line_id: int = Field(..., ge=1)
    optimized_text: str = Field(default="")
    user_final_remove: bool


class Step1ConfirmRequest(BaseModel):
    lines: list[Step1ConfirmLine]


class Step2ConfirmChapter(BaseModel):
    chapter_id: int = Field(..., ge=1)
    title: str = Field(default="")
    start: float = Field(..., ge=0)
    end: float = Field(..., ge=0)
    block_range: str = Field(default="", min_length=1)


class Step2ConfirmRequest(BaseModel):
    chapters: list[Step2ConfirmChapter]


class CouponRedeemRequest(BaseModel):
    code: str = Field(default="", min_length=1)


class AudioOssReadyRequest(BaseModel):
    object_key: str = Field(..., min_length=1)


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
