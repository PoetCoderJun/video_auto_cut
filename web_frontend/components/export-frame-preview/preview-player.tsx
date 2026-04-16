"use client";

import React from "react";

export function PreviewPlayer({
  centeredVideoStyle,
  emptyStateMode,
  sourceUrl,
  videoRef,
}: {
  centeredVideoStyle: React.CSSProperties;
  emptyStateMode: "message" | "blank";
  sourceUrl: string | null;
  videoRef: React.RefObject<HTMLVideoElement | null>;
}) {
  if (sourceUrl) {
    return (
      <video
        ref={videoRef as React.Ref<HTMLVideoElement>}
        src={sourceUrl}
        muted
        playsInline
        preload="metadata"
        style={centeredVideoStyle}
      />
    );
  }

  if (emptyStateMode === "blank") {
    return <div className="h-full w-full bg-white" />;
  }

  return (
    <div className="flex h-full w-full items-center justify-center bg-[linear-gradient(180deg,#111827_0%,#0f172a_100%)] text-sm text-slate-300">
      当前会话缺少本地原视频，预览不可用
    </div>
  );
}
