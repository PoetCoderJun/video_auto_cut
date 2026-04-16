"use client";

import {useEffect, useState} from "react";

import {
  inspectRenderSourceCompatibility,
  type RenderSourceCompatibility,
} from "@/lib/video-render-compatibility";

export type RenderSourceCompatibilityState =
  | RenderSourceCompatibility
  | {
      status: "idle" | "checking";
      message: string;
      videoCodec: string | null;
      audioCodec: string | null;
    };

const IDLE_STATE: RenderSourceCompatibilityState = {
  status: "idle",
  message: "",
  videoCodec: null,
  audioCodec: null,
};

export function useRenderSourceCompatibility(selectedFile: File | null) {
  const [renderSourceCompatibility, setRenderSourceCompatibility] =
    useState<RenderSourceCompatibilityState>(IDLE_STATE);

  useEffect(() => {
    let cancelled = false;
    if (!selectedFile) {
      setRenderSourceCompatibility(IDLE_STATE);
      return;
    }

    setRenderSourceCompatibility({
      status: "checking",
      message: "正在检查当前源视频是否可直接用于浏览器导出...",
      videoCodec: null,
      audioCodec: null,
    });

    inspectRenderSourceCompatibility(selectedFile)
      .then((result) => {
        if (!cancelled) {
          setRenderSourceCompatibility(result);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setRenderSourceCompatibility({
            status: "unknown",
            message:
              error instanceof Error
                ? `兼容性检查失败：${error.message}。将继续允许直接导出。`
                : "兼容性检查失败。将继续允许直接导出。",
            videoCodec: null,
            audioCodec: null,
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedFile]);

  return {renderSourceCompatibility, setRenderSourceCompatibility};
}
