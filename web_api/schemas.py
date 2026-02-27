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
    summary: str = Field(default="")
    start: float = Field(..., ge=0)
    end: float = Field(..., ge=0)
    line_ids: list[int] = Field(default_factory=list)


class Step2ConfirmRequest(BaseModel):
    chapters: list[Step2ConfirmChapter]


class CouponRedeemRequest(BaseModel):
    code: str = Field(default="", min_length=1)


class AudioOssReadyRequest(BaseModel):
    object_key: str = Field(..., min_length=1)
