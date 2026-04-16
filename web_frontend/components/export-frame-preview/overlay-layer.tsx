"use client";

import React from "react";

import {
  PROGRESS_LABEL_PADDING_X_EM,
  getChapterCardStyle,
} from "@/lib/remotion/overlay-presentation";

import {PreviewModel, CHAPTER_TITLE_LINE_HEIGHT, OVERLAY_FONT_FAMILY} from "./use-overlay-layout";

export function OverlayLayer({
  activeCaptionLayout,
  compositionHeight,
  children,
  compositionWidth,
  displayedPreviewTime,
  displayedSourceTime,
  formatClockTime,
  previewModel,
  previewScale,
  subtitleRenderFontSize,
  subtitleRenderText,
  subtitleStyleOverrides,
}: {
  activeCaptionLayout: {text?: string} | null;
  children?: React.ReactNode;
  compositionHeight: number;
  compositionWidth: number;
  displayedPreviewTime: number;
  displayedSourceTime: number;
  formatClockTime: (timeSec: number) => string;
  previewModel: PreviewModel;
  previewScale: number;
  subtitleRenderFontSize: number;
  subtitleRenderText: string;
  subtitleStyleOverrides: React.CSSProperties;
}) {
  return (
    <>
      <div className="pointer-events-none absolute left-6 top-5 z-10 flex items-center gap-2 text-[11px] font-medium text-white/88">
        <span className="rounded-full border border-white/14 bg-black/30 px-2.5 py-1 backdrop-blur-md">
          导出 {formatClockTime(displayedPreviewTime)}
        </span>
        <span className="rounded-full border border-white/14 bg-black/22 px-2.5 py-1 text-white/72 backdrop-blur-md">
          原片 {formatClockTime(displayedSourceTime)}
        </span>
      </div>

      <div
        className="absolute left-1/2 top-1/2 overflow-hidden rounded-[20px] border border-white/12 shadow-[0_28px_70px_-38px_rgba(2,6,23,0.75)]"
        style={{
          width: compositionWidth,
          height: compositionHeight,
          transform: `translate(-50%, -50%) scale(${previewScale || 1})`,
          transformOrigin: "center center",
          background: "linear-gradient(180deg, #020617 0%, #0f172a 100%)",
        }}
      >
        {children}

        {previewModel.showChapter && previewModel.activeTopic ? (
          <div
            style={{
              position: "absolute",
              top: previewModel.typography.chapterTop,
              left: previewModel.typography.chapterInsetX,
              right: previewModel.typography.chapterInsetX,
              pointerEvents: "none",
            }}
          >
            <div
              style={{
                ...getChapterCardStyle({
                  cardMaxWidth: previewModel.chapterCardMaxWidth,
                }),
              }}
            >
              <div
                style={{
                  fontSize: previewModel.typography.chapterMetaFontSize,
                  fontWeight: 700,
                  fontFamily: OVERLAY_FONT_FAMILY,
                  color: "#8ee0ff",
                }}
              >
                CHAPTER {previewModel.activeTopicLabel}
              </div>
              <div
                style={{
                  fontSize:
                    previewModel.activeTopicLayout?.fontSize ?? previewModel.typography.chapterTitleFontSize,
                  lineHeight: CHAPTER_TITLE_LINE_HEIGHT,
                  fontWeight: 800,
                  fontFamily: OVERLAY_FONT_FAMILY,
                  color: "#ffffff",
                  whiteSpace: "pre-line",
                  wordBreak: "normal",
                  overflowWrap: "anywhere",
                  maxWidth: previewModel.chapterTitleMaxWidth,
                }}
              >
                {previewModel.activeTopicLayout?.text ?? previewModel.activeTopic.title}
              </div>
            </div>
          </div>
        ) : null}

        {previewModel.showSubtitles ? (
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: `${previewModel.subtitleYPercent}%`,
              transform: "translateY(-50%)",
              display: "flex",
              justifyContent: "center",
              pointerEvents: "none",
              paddingLeft: previewModel.typography.subtitleSidePadding,
              paddingRight: previewModel.typography.subtitleSidePadding,
            }}
          >
            <div
              style={{
                boxSizing: "border-box",
                color: "#ffffff",
                fontSize: subtitleRenderFontSize,
                fontWeight: 700,
                fontFamily: OVERLAY_FONT_FAMILY,
                lineHeight: previewModel.subtitleLineHeight,
                textAlign: "center",
                whiteSpace: "pre-line",
                wordBreak: "normal",
                overflowWrap: "anywhere",
                overflow: "hidden",
                ...subtitleStyleOverrides,
              }}
            >
              {activeCaptionLayout?.text ?? subtitleRenderText}
            </div>
          </div>
        ) : null}

        {previewModel.showProgress ? (
          <div
            style={{
              position: "absolute",
              left: previewModel.typography.progressInsetX,
              right: previewModel.typography.progressInsetX,
              top: `${previewModel.progressYPercent}%`,
              transform: "translateY(-50%)",
              height: previewModel.typography.progressHeight,
              pointerEvents: "none",
            }}
          >
            <div
              style={{
                position: "relative",
                width: "100%",
                height: "100%",
                borderRadius: previewModel.typography.progressRadius,
                overflow: "hidden",
                backgroundColor: "rgba(16, 22, 30, 0.42)",
                border: "1px solid rgba(255, 255, 255, 0.22)",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: `${previewModel.progressRatio * 100}%`,
                  background: "linear-gradient(90deg, rgba(29, 217, 255, 0.58), rgba(66, 240, 180, 0.45))",
                }}
              />
              {previewModel.topicSegments.map((segment) => (
                <div
                  key={`preview-segment-${segment.index}-${segment.startRatio}-${segment.endRatio}`}
                  style={{
                    position: "absolute",
                    top: 0,
                    bottom: 0,
                    left: `${segment.startRatio * 100}%`,
                    width: `${(segment.endRatio - segment.startRatio) * 100}%`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    overflow: "hidden",
                    borderRight: "1px solid rgba(255, 255, 255, 0.2)",
                    backgroundColor:
                      segment.index ===
                      (previewModel.activeTopicLabel
                        ? Number(previewModel.activeTopicLabel.split("/")[0]) - 1
                        : -1)
                        ? "rgba(255, 255, 255, 0.08)"
                        : "rgba(255, 255, 255, 0.02)",
                  }}
                >
                  <div
                    style={{
                      maxWidth: "100%",
                      padding: `0 ${PROGRESS_LABEL_PADDING_X_EM}em`,
                      fontSize: segment.labelFit.fontSize,
                      fontWeight: 700,
                      fontFamily: OVERLAY_FONT_FAMILY,
                      lineHeight: previewModel.progressLabelLineHeight,
                      whiteSpace: previewModel.allowWrappedProgressLabels ? "pre-line" : "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      textAlign: "center",
                      color:
                        segment.index ===
                        (previewModel.activeTopicLabel
                          ? Number(previewModel.activeTopicLabel.split("/")[0]) - 1
                          : -1)
                          ? "#ffffff"
                          : "rgba(238, 244, 255, 0.84)",
                    }}
                  >
                    {segment.labelFit.visible ? segment.labelFit.text : ""}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </>
  );
}
