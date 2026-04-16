# PRD — upload-1mov-browser-e2e

## Goal
验证并打通浏览器端上传 `test_data/raw/1.MOV` 到最终导出视频的真实用户链路。

## User Story
- 作为内容创作者，我希望把 `1.MOV` 上传到网页端并直接完成字幕整理和导出，这样我能确认产品主路径可用。

## Acceptance Criteria
- 能在本地 Web MVP 中完成真实浏览器上传 `test_data/raw/1.MOV`。
- 若链路失败，定位并修复阻塞问题。
- 修复后能完成导出，并给出导出文件位置/文件名。
- 输出本次验证证据与涉及路径。

## Non-Goals
- 不做无关重构。
- 不尝试清理当前仓库所有已有未提交改动。
