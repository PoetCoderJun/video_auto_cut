"use client";

import {Button} from "@/components/ui/button";
import {cn} from "@/lib/utils";
import {CheckCircle2} from "lucide-react";

import {STEPS} from "./constants";

export function JobWorkspaceStepper({
  activeStep,
  succeeded,
  onBackHome,
}: {
  activeStep: number;
  succeeded: boolean;
  onBackHome?: () => void;
}) {
  return (
    <div className="mb-12 border-b pb-8">
      <div className="flex flex-wrap items-center justify-center gap-4 md:justify-between">
        <div className="flex flex-wrap items-center gap-2 md:gap-4">
          {STEPS.map((step, index) => {
            const isCompleted = step.id < activeStep || (step.id === 3 && succeeded);
            const isActive = step.id === activeStep && !succeeded;
            return (
              <div key={step.id} className="flex items-center gap-2 md:gap-4">
                <div
                  className={cn(
                    "flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : isCompleted
                        ? "bg-muted text-foreground"
                        : "text-muted-foreground opacity-50",
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
                </div>
                {index < STEPS.length - 1 && (
                  <div className="text-muted-foreground/30">›</div>
                )}
              </div>
            );
          })}
        </div>
        {onBackHome && (
          <Button type="button" variant="ghost" size="sm" onClick={onBackHome}>
            重新上传
          </Button>
        )}
      </div>
    </div>
  );
}
