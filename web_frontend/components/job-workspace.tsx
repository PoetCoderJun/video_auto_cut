"use client";

import {useEffect, useState} from "react";

import {resetBrowserFfmpeg} from "../lib/ffmpeg-browser";
import {STATUS} from "../lib/workflow";

import {SUPPORTED_UPLOAD_ACCEPT} from "./job-workspace/constants";
import {EditorStep} from "./job-workspace/editor-step";
import {ExportStep} from "./job-workspace/export-step";
import {JobWorkspaceLoadingState} from "./job-workspace/job-workspace-loading-state";
import {JobWorkspaceStepper} from "./job-workspace/job-workspace-stepper";
import {TestProcessingState} from "./job-workspace/test-processing-state";
import {UploadStep} from "./job-workspace/upload-step";
import {useEditorStepController} from "./job-workspace/use-editor-step-controller";
import {useExportStepController} from "./job-workspace/use-export-step-controller";
import {useJobLifecycle} from "./job-workspace/use-job-lifecycle";
import {getActiveStep, getJobWorkspaceView} from "./job-workspace/workspace-state";

export default function JobWorkspace({
  jobId,
  onBackHome,
  onSwitchJob,
}: {
  jobId: string;
  onBackHome?: () => void;
  onSwitchJob?: (jobId: string) => void;
}) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const lifecycle = useJobLifecycle({
    jobId,
    onBackHome,
    onPreparedSource: setSelectedFile,
    onSwitchJob,
  });
  const editor = useEditorStepController({
    busy: lifecycle.state.busy,
    job: lifecycle.state.job,
    jobId,
    setBusy: lifecycle.actions.setBusy,
    setError: lifecycle.actions.setError,
    setJob: lifecycle.actions.setJob,
  });
  const exportController = useExportStepController({
    busy: lifecycle.state.busy,
    job: lifecycle.state.job,
    jobId,
    selectedFile,
    setError: lifecycle.actions.setError,
    setJob: lifecycle.actions.setJob,
    setSelectedFile,
  });

  useEffect(() => {
    return () => {
      resetBrowserFfmpeg();
    };
  }, []);

  if (!lifecycle.state.job) {
    return (
      <JobWorkspaceLoadingState
        isLoadingJob={lifecycle.state.isLoadingJob}
        jobLoadError={lifecycle.state.jobLoadError}
        onRetryLoadJob={lifecycle.actions.handleRetryLoadJob}
        onBackHome={onBackHome}
      />
    );
  }

  const job = lifecycle.state.job;
  const activeStep = getActiveStep(job.status);
  const view = getJobWorkspaceView(job.status, editor.state.testReadyHandoffActive);

  return (
    <main className="container mx-auto max-w-6xl px-4 py-8">
      <JobWorkspaceStepper
        activeStep={activeStep}
        succeeded={job.status === STATUS.SUCCEEDED}
        onBackHome={onBackHome}
      />

      {(job.error || lifecycle.state.error) && (
        <div className="mb-6 rounded-md border border-destructive/20 bg-destructive/10 p-4 text-sm font-medium text-destructive">
          {job.error?.message || lifecycle.state.error}
        </div>
      )}

      {exportController.state.renderCompletionMarkerMessage && (
        <div className="mb-6 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm font-medium text-amber-800">
          {exportController.state.renderCompletionMarkerMessage}
        </div>
      )}

      {exportController.state.renderNote && (
        <div className="mb-6 rounded-md border border-amber-200 bg-amber-50 p-4 text-sm font-medium text-amber-800">
          {exportController.state.renderNote}
        </div>
      )}

      {view === "upload" && (
        <UploadStep
          state={{
            busy: lifecycle.state.busy,
            mobileUploadBlocked: lifecycle.state.mobileUploadBlocked,
            selectedFile,
            supportedUploadAccept: SUPPORTED_UPLOAD_ACCEPT,
            uploadStageMessage: lifecycle.state.uploadStageMessage,
          }}
          actions={{
            onBlockedClick: lifecycle.actions.showMobileUploadError,
            onFileChange: lifecycle.actions.handleUploadFileChange,
          }}
        />
      )}

      {view === "processing" && (
        <TestProcessingState
          job={job}
          lines={editor.state.lines}
          busy={lifecycle.state.busy}
          autoTestTriggered={lifecycle.state.autoTestTriggered}
          draftError={editor.state.testDraftError}
          onRetry={lifecycle.actions.handleRetryTestAutoRun}
          onRetryDraft={editor.actions.handleRetryTestDraftLoad}
        />
      )}

      {view === "editor" && (
        <EditorStep
          state={editor.state}
          actions={editor.actions}
          helpers={editor.helpers}
        />
      )}

      {view === "export" && (
        <ExportStep
          state={{
            ...exportController.state,
            busy: lifecycle.state.busy,
            supportedUploadAccept: SUPPORTED_UPLOAD_ACCEPT,
          }}
          actions={exportController.actions}
        />
      )}
    </main>
  );
}
