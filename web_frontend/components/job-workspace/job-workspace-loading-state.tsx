"use client";

import {Button} from "@/components/ui/button";
import {Loader2} from "lucide-react";

export function JobWorkspaceLoadingState({
  isLoadingJob,
  jobLoadError,
  onRetryLoadJob,
  onBackHome,
}: {
  isLoadingJob: boolean;
  jobLoadError: string;
  onRetryLoadJob: () => void;
  onBackHome?: () => void;
}) {
  return (
    <main className="container mx-auto flex h-[50vh] flex-col items-center justify-center gap-4">
      {isLoadingJob ? (
        <>
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-muted-foreground">正在加载项目数据...</p>
        </>
      ) : jobLoadError ? (
        <div className="w-full max-w-md space-y-4 rounded-md border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">
          <p>{jobLoadError}</p>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={onRetryLoadJob}>
              重新加载项目
            </Button>
            {onBackHome && (
              <Button size="sm" variant="outline" onClick={onBackHome}>
                返回首页
              </Button>
            )}
          </div>
        </div>
      ) : (
        <>
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-muted-foreground">正在加载项目数据...</p>
        </>
      )}
    </main>
  );
}
