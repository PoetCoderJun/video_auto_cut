"use client";

import {Button} from "@/components/ui/button";
import {cn} from "@/lib/utils";
import {ArrowLeft, CheckCircle2, ChevronRight, Loader2} from "lucide-react";

import {STEPS} from "./constants";

type StepId = (typeof STEPS)[number]["id"];

export function JobWorkspaceStepper({
  activeStep,
  canReopenEditor,
  onBackHome,
  onReopenEditor,
  reopenEditorBusy,
  reopenEditorDisabled,
  succeeded,
}: {
  activeStep: number;
  canReopenEditor?: boolean;
  onBackHome?: () => void;
  onReopenEditor?: () => void;
  reopenEditorBusy?: boolean;
  reopenEditorDisabled?: boolean;
  succeeded: boolean;
}) {
  const getStepAction = (stepId: StepId): (() => void) | undefined => {
    if (stepId === 1 && onBackHome && stepId < activeStep) {
      return onBackHome;
    }
    if (stepId === 2 && canReopenEditor && onReopenEditor) {
      return onReopenEditor;
    }
    return undefined;
  };

  const canShowReopenAction = Boolean(
    canReopenEditor && onReopenEditor && activeStep >= 3 && !succeeded,
  );

  return (
    <div className="mb-12 border-b pb-8">
      <div className="flex flex-wrap items-center justify-center gap-4 md:justify-between">
        <div className="flex flex-wrap items-center justify-center gap-2 md:gap-4">
          {STEPS.map((step, index) => {
            const isCompleted = step.id < activeStep || (step.id === 3 && succeeded);
            const isActive = step.id === activeStep && !succeeded;
            const stepAction = getStepAction(step.id);
            const isClickable = Boolean(stepAction);
            const isDisabled =
              step.id === 2 && isClickable && (reopenEditorBusy || reopenEditorDisabled);
            const StepTag = isClickable ? "button" : "div";
            return (
              <div key={step.id} className="flex items-center gap-2 md:gap-4">
                <StepTag
                  type={isClickable ? "button" : undefined}
                  onClick={isClickable ? stepAction : undefined}
                  disabled={isClickable ? isDisabled : undefined}
                  aria-label={
                    step.id === 1 && isClickable
                      ? "返回上传视频"
                      : step.id === 2 && isClickable
                        ? "返回编辑字幕"
                        : undefined
                  }
                  className={cn(
                    "flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : isCompleted
                        ? "bg-muted text-foreground"
                        : "text-muted-foreground opacity-50",
                    isClickable &&
                      "cursor-pointer hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-60",
                  )}
                >
                  <div
                    className={cn(
                      "flex h-5 w-5 items-center justify-center rounded-full border text-[10px]",
                      isActive ? "border-primary-foreground" : "border-current",
                    )}
                  >
                    {isCompleted ? <CheckCircle2 className="h-3 w-3" /> : step.id}
                  </div>
                  <span className="hidden sm:inline">{step.label}</span>
                </StepTag>
                {index < STEPS.length - 1 && (
                  <ChevronRight className="h-4 w-4 text-muted-foreground/30" />
                )}
              </div>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2">
          {canShowReopenAction && (
            <Button
              type="button"
              variant="default"
              size="sm"
              className="rounded-full px-4"
              onClick={onReopenEditor}
              disabled={reopenEditorBusy || reopenEditorDisabled}
            >
              {reopenEditorBusy ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" /> 返回中
                </>
              ) : (
                <>
                  <ArrowLeft className="mr-2 h-4 w-4" /> 返回上一步编辑字幕
                </>
              )}
            </Button>
          )}
          {onBackHome && (
            <Button type="button" variant="ghost" size="sm" onClick={onBackHome}>
              重新上传
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
