"use client";

import {ChangeEvent} from "react";

import {Card, CardContent, CardDescription, CardHeader, CardTitle} from "@/components/ui/card";
import {cn} from "@/lib/utils";
import {Loader2, UploadCloud} from "lucide-react";

export function UploadStep({
  actions,
  state,
}: {
  actions: {
    onBlockedClick: () => void;
    onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  };
  state: {
    busy: boolean;
    mobileUploadBlocked: boolean;
    selectedFile: File | null;
    supportedUploadAccept: string;
    uploadStageMessage: string;
  };
}) {
  const {
    busy,
    mobileUploadBlocked,
    selectedFile,
    supportedUploadAccept,
    uploadStageMessage,
  } = state;

  return (
    <Card className="mx-auto max-w-xl text-center">
      <CardHeader>
        <CardTitle>上传原始视频</CardTitle>
        <CardDescription>
          请选择您要剪辑的视频文件。支持 MP4, MOV, MKV 等格式。
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div
          onClick={() => {
            if (mobileUploadBlocked) actions.onBlockedClick();
          }}
          className={cn(
            "relative group w-full rounded-xl border-2 border-dashed border-muted-foreground/25 bg-muted/50 p-10 transition-all hover:border-primary/50 hover:bg-muted",
            selectedFile && "border-primary bg-primary/5",
            busy || mobileUploadBlocked
              ? "opacity-70 cursor-not-allowed"
              : "cursor-pointer",
          )}
        >
          <input
            type="file"
            accept={supportedUploadAccept}
            onChange={actions.onFileChange}
            disabled={busy || mobileUploadBlocked}
            className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
          />
          <div className="flex flex-col items-center justify-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-background shadow-sm">
              {busy ? (
                <Loader2 className="h-8 w-8 animate-spin text-primary" />
              ) : (
                <UploadCloud className="h-8 w-8 text-primary" />
              )}
            </div>
            <div className="space-y-1">
              <h3 className="font-semibold text-lg text-foreground">
                {busy
                  ? uploadStageMessage || "正在上传..."
                  : mobileUploadBlocked
                    ? "当前浏览器暂不支持上传"
                    : selectedFile
                      ? selectedFile.name
                      : "点击或拖拽上传视频"}
              </h3>
              <p className="text-sm text-muted-foreground">
                {mobileUploadBlocked
                  ? "请使用桌面版 Chrome"
                  : busy
                    ? "请保持页面开启，我们会自动继续处理。"
                    : "AI 将自动提取字幕并进行智能分析"}
              </p>
            </div>
          </div>
        </div>
        {mobileUploadBlocked && (
          <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm font-medium text-amber-800">
            当前浏览器暂不支持上传视频，请使用桌面版 Chrome。
          </div>
        )}
      </CardContent>
    </Card>
  );
}
