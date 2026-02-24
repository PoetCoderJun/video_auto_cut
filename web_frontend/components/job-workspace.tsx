"use client";

import {useCallback, useEffect, useMemo, useState} from "react";
import {
  Chapter,
  Job,
  Step1Line,
  confirmStep1,
  confirmStep2,
  downloadRenderedVideo,
  getJob,
  getRenderSourceBlob,
  getStep1,
  getStep2,
  getWebRenderConfig,
  runStep1,
  runStep2,
  uploadVideo,
} from "../lib/api";
import {STATUS} from "../lib/workflow";
import {StitchVideoWeb, type SubtitleTheme} from "../lib/remotion/stitch-video-web";

function autoResize(target: HTMLTextAreaElement) {
  target.style.height = "auto";
  target.style.height = `${target.scrollHeight}px`;
}

const STEPS = [
  {id: 1, label: "上传视频"},
  {id: 2, label: "剪辑字幕"},
  {id: 3, label: "确认章节"},
  {id: 4, label: "导出视频"},
];

const CHAPTER_COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"];
const SUPPORTED_UPLOAD_EXTENSIONS = [".mp4", ".mov", ".mkv", ".webm", ".m4v", ".ts", ".m2ts", ".mts"];
const SUPPORTED_UPLOAD_ACCEPT = SUPPORTED_UPLOAD_EXTENSIONS.join(",");
const SUBTITLE_THEME_OPTIONS: Array<{value: SubtitleTheme; label: string}> = [
  {value: "box-white-on-black", label: "黑底白字"},
  {value: "box-black-on-white", label: "白底黑字"},
  {value: "text-white", label: "白色"},
  {value: "text-black", label: "黑色"},
];

function getActiveStep(status: Job["status"]): number {
  switch (status) {
    case STATUS.CREATED:
    case STATUS.UPLOAD_READY:
      return 1;
    case STATUS.STEP1_RUNNING:
    case STATUS.STEP1_READY:
      return 2;
    case STATUS.STEP1_CONFIRMED:
    case STATUS.STEP2_RUNNING:
    case STATUS.STEP2_READY:
      return 3;
    case STATUS.STEP2_CONFIRMED:
    case STATUS.RENDER_RUNNING:
    case STATUS.SUCCEEDED:
      return 4;
    default:
      return 1;
  }
}

function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(100, value));
}

function ProgressBar({label, value}: {label: string; value: number}) {
  const safeValue = clampPercent(value);
  return (
    <div className="progress-item">
      <div className="progress-head">
        <span>{label}</span>
        <span>{Math.round(safeValue)}%</span>
      </div>
      <div className="progress-track">
        <div className="progress-fill" style={{width: `${safeValue}%`}} />
      </div>
    </div>
  );
}

function CircularProgress({value}: {value: number}) {
  const safeValue = clampPercent(value);
  const size = 180;
  const stroke = 12;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - safeValue / 100);

  return (
    <div style={{position: "relative", width: size, height: size}}>
      <svg width={size} height={size}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#0f172a"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${circumference} ${circumference}`}
          strokeDashoffset={dashOffset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{transition: "stroke-dashoffset 0.2s ease"}}
        />
      </svg>
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 34,
          fontWeight: 700,
          color: "#0f172a",
        }}
      >
        {Math.round(safeValue)}%
      </div>
    </div>
  );
}

function formatDuration(seconds: number): string {
  if (!seconds || Number.isNaN(seconds)) return "00:00";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
}

export default function JobWorkspace({
  jobId,
  onBackHome,
}: {
  jobId: string;
  onBackHome?: () => void;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [lines, setLines] = useState<Step1Line[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [downloadBusy, setDownloadBusy] = useState(false);
  const [renderBusy, setRenderBusy] = useState(false);
  const [renderProgress, setRenderProgress] = useState(0);
  const [renderDownloadUrl, setRenderDownloadUrl] = useState<string | null>(null);
  const [renderFileName, setRenderFileName] = useState("output.mp4");
  const [subtitleTheme, setSubtitleTheme] = useState<SubtitleTheme>("box-white-on-black");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [draggedLineId, setDraggedLineId] = useState<number | null>(null);

  const lineToChapterIndex = useMemo(() => {
    const map: Record<number, number> = {};
    chapters.forEach((ch, idx) => {
      ch.line_ids.forEach((lid) => {
        map[lid] = idx;
      });
    });
    return map;
  }, [chapters]);

  const keptLines = useMemo(() => lines.filter((l) => !l.user_final_remove), [lines]);

  const refreshJob = useCallback(async () => {
    const next = await getJob(jobId);
    setJob(next);
    return next;
  }, [jobId]);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setInterval> | null = null;

    const tick = async () => {
      try {
        const latest = await getJob(jobId);
        if (!active) return;
        setJob(latest);
        setError((prev) => (prev.startsWith("无法连接 API") ? "" : prev));
      } catch {
        if (!active) return;
        setError("无法连接 API，请确认后端服务正在运行。");
      }
    };

    tick();
    timer = setInterval(tick, 2000);

    return () => {
      active = false;
      if (timer) clearInterval(timer);
    };
  }, [jobId]);

  useEffect(() => {
    if (!job) return;
    if (job.status === STATUS.STEP1_READY && lines.length === 0) {
      getStep1(jobId).then(setLines).catch(() => undefined);
    }
  }, [job, lines.length, jobId]);

  useEffect(() => {
    if (!job) return;
    if (job.status === STATUS.STEP2_READY) {
      if (chapters.length === 0) {
        getStep2(jobId).then(setChapters).catch(() => undefined);
      }
      if (lines.length === 0) {
        getStep1(jobId).then(setLines).catch(() => undefined);
      }
    }
  }, [job, chapters.length, lines.length, jobId]);

  useEffect(() => {
    return () => {
      if (renderDownloadUrl) {
        URL.revokeObjectURL(renderDownloadUrl);
      }
    };
  }, [renderDownloadUrl]);

  useEffect(() => {
    setRenderBusy(false);
    setDownloadBusy(false);
    setRenderProgress(0);
    setRenderDownloadUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return null;
    });
    setRenderFileName("output.mp4");
    setSubtitleTheme("box-white-on-black");
  }, [jobId]);

  const handleUpload = async (file: File) => {
    setError("");
    const lowerName = file.name.toLowerCase();
    const hasSupportedExt = SUPPORTED_UPLOAD_EXTENSIONS.some((ext) => lowerName.endsWith(ext));
    if (!hasSupportedExt) {
      setError("这个文件格式暂不支持。请上传 MP4、MOV、MKV、WebM、M4V、TS、M2TS 或 MTS 视频。");
      return;
    }
    setBusy(true);
    try {
      const nextJob = await uploadVideo(jobId, file);
      if (nextJob.status === STATUS.UPLOAD_READY) {
        await runStep1(jobId);
      }
      await refreshJob();
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败，请重试。");
    } finally {
      setBusy(false);
    }
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      void handleUpload(file);
    }
  };

  const handleConfirmStep1 = async () => {
    setError("");
    setBusy(true);
    try {
      await confirmStep1(jobId, lines);
      await runStep2(jobId);
      await refreshJob();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败，请重试。");
    } finally {
      setBusy(false);
    }
  };

  const handleConfirmStep2 = async () => {
    setError("");
    setBusy(true);
    try {
      await confirmStep2(jobId, chapters);
      await refreshJob();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败，请重试。");
    } finally {
      setBusy(false);
    }
  };

  const handleStartRender = useCallback(async () => {
    setError("");
    setRenderBusy(true);
    setRenderProgress(0);
    setRenderDownloadUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return null;
    });
    let sourceObjectUrl: string | null = null;
    try {
      const config = await getWebRenderConfig(jobId);
      const sourceBlob = await getRenderSourceBlob(jobId);
      sourceObjectUrl = URL.createObjectURL(sourceBlob);
      const inputProps = {
        ...config.input_props,
        src: sourceObjectUrl,
        subtitleTheme,
      };
      const composition = {
        ...config.composition,
        component: StitchVideoWeb,
        defaultProps: inputProps,
      };

      const {renderMediaOnWeb} = await import("@remotion/web-renderer");
      const result = await renderMediaOnWeb({
        composition,
        inputProps,
        videoCodec: "h264",
        onProgress: (progress) => {
          const totalFrames = Math.max(1, Number(config.composition.durationInFrames) || 1);
          const doneFrames =
            typeof progress.encodedFrames === "number" && Number.isFinite(progress.encodedFrames)
              ? progress.encodedFrames
              : progress.renderedFrames;
          setRenderProgress((previous) => Math.max(previous, clampPercent((doneFrames / totalFrames) * 100)));
        },
      });

      setRenderFileName(config.output_name || "output.mp4");
      const blob = await result.getBlob();
      const objectUrl = URL.createObjectURL(blob);
      setRenderDownloadUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return objectUrl;
      });
      // Try auto-download after export; keep the manual button as fallback.
      const autoDownloadLink = document.createElement("a");
      autoDownloadLink.href = objectUrl;
      autoDownloadLink.download = config.output_name || "output.mp4";
      autoDownloadLink.style.display = "none";
      document.body.appendChild(autoDownloadLink);
      autoDownloadLink.click();
      document.body.removeChild(autoDownloadLink);
      setRenderProgress(100);
    } catch (err) {
      setError(err instanceof Error ? err.message : "浏览器导出失败，请重试。");
    } finally {
      if (sourceObjectUrl) {
        URL.revokeObjectURL(sourceObjectUrl);
      }
      setRenderBusy(false);
    }
  }, [jobId, subtitleTheme]);

  const handleDownloadFinalVideo = useCallback(async () => {
    setError("");
    setDownloadBusy(true);
    try {
      const result = await downloadRenderedVideo(jobId);
      const objectUrl = URL.createObjectURL(result.blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = result.filename || "output.mp4";
      link.style.display = "none";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(() => URL.revokeObjectURL(objectUrl), 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "下载失败，请重试。");
    } finally {
      setDownloadBusy(false);
    }
  }, [jobId]);

  useEffect(() => {
    if (renderBusy) return;
    setRenderDownloadUrl((previous) => {
      if (!previous) return previous;
      URL.revokeObjectURL(previous);
      return null;
    });
    setRenderProgress(0);
  }, [subtitleTheme]);

  const updateLine = (lineId: number, patch: Partial<Step1Line>) => {
    setLines((prev) => prev.map((line) => (line.line_id === lineId ? {...line, ...patch} : line)));
  };

  const updateChapter = (chapterId: number, patch: Partial<Chapter>) => {
    setChapters((prev) =>
      prev.map((chapter) => (chapter.chapter_id === chapterId ? {...chapter, ...patch} : chapter)),
    );
  };

  const handleDragStart = (e: React.DragEvent, lineId: number) => {
    e.dataTransfer.setData("text/plain", lineId.toString());
    e.dataTransfer.effectAllowed = "move";
    setDraggedLineId(lineId);
  };

  const handleDragEnd = () => {
    setDraggedLineId(null);
  };

  const handleDropOnLine = (e: React.DragEvent, targetLineId: number) => {
    e.preventDefault();
    setDraggedLineId(null);

    const lineIdStr = e.dataTransfer.getData("text/plain");
    if (!lineIdStr) return;
    const draggedId = parseInt(lineIdStr, 10);
    if (draggedId === targetLineId) return;

    const targetChapterIdx = lineToChapterIndex[targetLineId];
    if (targetChapterIdx === undefined) return;
    const targetChapter = chapters[targetChapterIdx];

    setChapters((prev) =>
      prev.map((ch) => {
        const filtered = ch.line_ids.filter((id) => id !== draggedId);
        if (ch.chapter_id === targetChapter.chapter_id) {
          const newIds = [...filtered, draggedId].sort((a, b) => a - b);
          return {...ch, line_ids: newIds};
        }
        return {...ch, line_ids: filtered};
      }),
    );
  };

  const {originalDuration, estimatedDuration} = useMemo(() => {
    let original = 0;
    let estimated = 0;
    if (lines.length > 0) {
      original = lines[lines.length - 1].end;
      estimated = lines.reduce((acc, line) => {
        if (!line.user_final_remove) return acc + (line.end - line.start);
        return acc;
      }, 0);
    }
    return {originalDuration: original, estimatedDuration: estimated};
  }, [lines]);

  if (!job) {
    return (
      <main>
        <div className="loading-view">
          <div className="spinner"></div>
          <p>正在加载项目数据...</p>
        </div>
      </main>
    );
  }

  const activeStep = getActiveStep(job.status);
  const renderComposeProgress = clampPercent(job.progress);

  return (
    <main className="fade-in">
      <header className="page-header" style={{borderBottom: "none", paddingBottom: 0, marginBottom: 48}}>
        <div style={{display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap"}}>
          {STEPS.map((step, idx) => {
            const isCompleted = step.id < activeStep || (step.id === 4 && job.status === STATUS.SUCCEEDED);
            const isActive = step.id === activeStep && job.status !== STATUS.SUCCEEDED;
            return (
              <div key={step.id} style={{display: "flex", alignItems: "center", gap: 12}}>
                <div style={{display: "flex", alignItems: "center", gap: 8, opacity: isActive ? 1 : isCompleted ? 0.7 : 0.4}}>
                  <div
                    style={{
                      width: 22,
                      height: 22,
                      borderRadius: "50%",
                      background: isActive ? "#0f172a" : isCompleted ? "#e2e8f0" : "transparent",
                      border: `1px solid ${isActive ? "#0f172a" : "#cbd5e1"}`,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: isActive ? "#fff" : "#64748b",
                      fontSize: 12,
                      fontWeight: 600,
                    }}
                  >
                    {isCompleted ? "✓" : step.id}
                  </div>
                  <span style={{fontSize: 15, fontWeight: isActive ? 600 : 500, color: "#0f172a"}}>{step.label}</span>
                </div>
                {idx < STEPS.length - 1 && <div style={{color: "#cbd5e1"}}>›</div>}
              </div>
            );
          })}
        </div>
        {onBackHome ? (
          <button className="ghost" onClick={onBackHome} disabled={busy}>
            重新上传视频
          </button>
        ) : null}
      </header>

      {(job.error || error) && <div className="error">{job.error?.message || error}</div>}

      {job.status === STATUS.CREATED && (
        <div className="fade-in">
          <h2 style={{fontSize: 20}}>上传原始视频</h2>
          <p className="muted" style={{marginBottom: 32}}>
            请选择您要剪辑的视频文件。支持 MP4、MOV、MKV、WebM、M4V、TS、M2TS、MTS。上传完成后 AI 会自动开始处理。
          </p>
          <div className={`file-upload-wrapper ${selectedFile ? "has-file" : ""}`} style={{width: "100%"}}>
            <div className="file-upload-btn">
              {busy ? "正在上传，请勿关闭页面..." : selectedFile ? selectedFile.name : "点击此处选择视频文件，或将文件拖拽至此"}
            </div>
            <input type="file" accept={SUPPORTED_UPLOAD_ACCEPT} onChange={onFileChange} disabled={busy} />
          </div>
        </div>
      )}

      {(job.status === STATUS.UPLOAD_READY || job.status === STATUS.STEP1_RUNNING) && (
        <div className="loading-view fade-in">
          <div className="spinner"></div>
          <h2>正在提取字幕</h2>
          <p className="muted" style={{marginTop: 8}}>AI 正在解析视频语音，这可能需要几分钟...</p>
        </div>
      )}

      {(job.status === STATUS.STEP1_CONFIRMED || job.status === STATUS.STEP2_RUNNING) && (
        <div className="loading-view fade-in">
          <div className="spinner"></div>
          <h2>正在生成章节</h2>
          <p className="muted" style={{marginTop: 8}}>请等待，处理完成后将自动进入导出步骤。</p>
        </div>
      )}

      {job.status === STATUS.RENDER_RUNNING && (
        <div className="loading-view fade-in">
          <div className="spinner"></div>
          <h2>正在后台合成视频</h2>
          <p className="muted" style={{marginTop: 8}}>请等待，合成完成后即可下载。</p>
          <div className="loading-progress">
            <ProgressBar label="视频合成" value={renderComposeProgress} />
          </div>
        </div>
      )}

      {job.status === STATUS.STEP1_READY && (
        <div className="fade-in">
          <div style={{marginBottom: 32}}>
            <h2 style={{fontSize: 22, color: "#0f172a"}}>用字幕编辑视频</h2>
            <p className="muted" style={{marginTop: 8, lineHeight: 1.6}}>直接修改字幕，点击句尾“×”可剔除该句。</p>
          </div>

          <div className="modern-list">
            {lines.map((line) => {
              const isRemoved = line.user_final_remove;
              return (
                <div
                  key={line.line_id}
                  className={`modern-line ${isRemoved ? "removed" : ""}`}
                  onClick={() => {
                    if (isRemoved) updateLine(line.line_id, {user_final_remove: false});
                  }}
                >
                  <div className="modern-line-content">
                    {!isRemoved ? (
                      <textarea
                        className="modern-input"
                        value={line.optimized_text}
                        onChange={(e) => updateLine(line.line_id, {optimized_text: e.target.value})}
                        onClick={(e) => e.stopPropagation()}
                        rows={1}
                        onInput={(e) => autoResize(e.target as HTMLTextAreaElement)}
                        ref={(el) => {
                          if (el) autoResize(el);
                        }}
                      />
                    ) : (
                      <span className="removed-text">{line.optimized_text}</span>
                    )}
                  </div>
                  {!isRemoved && (
                    <span
                      className="remove-icon"
                      onClick={(e) => {
                        e.stopPropagation();
                        updateLine(line.line_id, {user_final_remove: true});
                      }}
                      title="剔除此行"
                    >
                      ×
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          <div className="action-bar" style={{flexDirection: "column", alignItems: "center", gap: 32}}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 48,
                padding: "24px 40px",
                background: "#f8fafc",
                border: "1px solid #e2e8f0",
                borderRadius: 16,
                width: "100%",
              }}
            >
              <div style={{display: "flex", flexDirection: "column", alignItems: "center", gap: 8}}>
                <span style={{fontSize: 15, color: "#64748b", fontWeight: 500}}>原始时长</span>
                <span style={{fontSize: 36, color: "#0f172a", fontWeight: 700}}>{formatDuration(originalDuration)}</span>
              </div>
              <div style={{color: "#cbd5e1", fontSize: 24}}>→</div>
              <div style={{display: "flex", flexDirection: "column", alignItems: "center", gap: 8}}>
                <span style={{fontSize: 15, color: "#64748b", fontWeight: 500}}>预计剪辑后</span>
                <span style={{fontSize: 36, color: "#059669", fontWeight: 700}}>{formatDuration(estimatedDuration)}</span>
              </div>
            </div>

            <button className="primary large-btn" onClick={handleConfirmStep1} disabled={lines.length === 0 || busy}>
              {busy ? "正在保存..." : "确认无误，下一步"}
            </button>
          </div>
        </div>
      )}

      {job.status === STATUS.STEP2_READY && (
        <div className="fade-in">
          <div style={{marginBottom: 32}}>
            <h2 style={{fontSize: 20}}>确认视频章节</h2>
            <p className="muted" style={{marginTop: 8, lineHeight: 1.6}}>拖拽字幕行可调整章节归属，点击标题可编辑。</p>
          </div>

          <div style={{display: "flex", flexDirection: "column", gap: 0}}>
            {chapters.map((chapter, chapterIdx) => {
              const color = CHAPTER_COLORS[chapterIdx % CHAPTER_COLORS.length];
              const chapterLines = keptLines.filter((l) => chapter.line_ids.includes(l.line_id));
              const isFirst = chapterIdx === 0;
              const isLast = chapterIdx === chapters.length - 1;

              return (
                <div key={chapter.chapter_id} style={{display: "flex", flexDirection: "column"}}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      padding: "16px 20px",
                      background: `${color}08`,
                      borderTop: isFirst ? `2px solid ${color}` : "1px dashed #e2e8f0",
                      borderLeft: `3px solid ${color}`,
                      borderRight: "1px solid #e2e8f0",
                      borderTopLeftRadius: isFirst ? 12 : 0,
                      borderTopRightRadius: isFirst ? 12 : 0,
                    }}
                  >
                    <div
                      style={{
                        background: color,
                        color: "#fff",
                        padding: "2px 10px",
                        borderRadius: 10,
                        fontSize: 12,
                        fontWeight: 700,
                        whiteSpace: "nowrap",
                      }}
                    >
                      {chapterIdx + 1}
                    </div>
                    <input
                      type="text"
                      value={chapter.title}
                      placeholder="章节标题"
                      onChange={(e) => updateChapter(chapter.chapter_id, {title: e.target.value})}
                      style={{
                        flex: 1,
                        border: "none",
                        background: "transparent",
                        fontSize: 15,
                        fontWeight: 600,
                        color: "#0f172a",
                        outline: "none",
                        padding: "4px 0",
                      }}
                    />
                    <span style={{fontSize: 12, color: "#94a3b8", whiteSpace: "nowrap"}}>{chapterLines.length} 句</span>
                  </div>

                  <div
                    style={{
                      borderLeft: `3px solid ${color}`,
                      borderRight: "1px solid #e2e8f0",
                      borderBottom: isLast ? "1px solid #e2e8f0" : "none",
                      borderBottomLeftRadius: isLast ? 12 : 0,
                      borderBottomRightRadius: isLast ? 12 : 0,
                      minHeight: 24,
                    }}
                    onDragOver={(e) => {
                      e.preventDefault();
                      e.dataTransfer.dropEffect = "move";
                    }}
                    onDrop={(e) => {
                      e.preventDefault();
                      setDraggedLineId(null);
                      const lid = parseInt(e.dataTransfer.getData("text/plain"), 10);
                      if (Number.isNaN(lid)) return;
                      if (chapter.line_ids.includes(lid)) return;
                      setChapters((prev) =>
                        prev.map((ch) => {
                          const filtered = ch.line_ids.filter((id) => id !== lid);
                          if (ch.chapter_id === chapter.chapter_id) {
                            return {...ch, line_ids: [...filtered, lid].sort((a, b) => a - b)};
                          }
                          return {...ch, line_ids: filtered};
                        }),
                      );
                    }}
                  >
                    {chapterLines.map((l, lineIdx) => {
                      const isDragged = draggedLineId === l.line_id;
                      return (
                        <div
                          key={l.line_id}
                          draggable
                          onDragStart={(e) => handleDragStart(e, l.line_id)}
                          onDragEnd={handleDragEnd}
                          onDragOver={(e) => {
                            e.preventDefault();
                            e.dataTransfer.dropEffect = "move";
                          }}
                          onDrop={(e) => handleDropOnLine(e, l.line_id)}
                          style={{
                            fontSize: 13,
                            color: isDragged ? "#94a3b8" : "#475569",
                            lineHeight: 1.7,
                            padding: "6px 20px 6px 36px",
                            cursor: "grab",
                            opacity: isDragged ? 0.4 : 1,
                            background: isDragged ? `${color}06` : lineIdx % 2 === 0 ? "transparent" : "#fafbfc",
                            transition: "opacity 0.15s, background 0.15s",
                            borderTop: lineIdx > 0 ? "1px solid #f1f5f9" : "none",
                          }}
                        >
                          {l.optimized_text}
                        </div>
                      );
                    })}
                    {chapterLines.length === 0 && (
                      <div style={{padding: "12px 20px 12px 36px", fontSize: 13, color: "#cbd5e1"}}>拖拽字幕行到此章节</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="action-bar">
            <button className="primary large-btn" onClick={handleConfirmStep2} disabled={chapters.length === 0 || busy}>
              {busy ? "正在保存..." : "确认章节，进入导出"}
            </button>
          </div>
        </div>
      )}

      {job.status === STATUS.STEP2_CONFIRMED && (
        <div className="fade-in" style={{textAlign: "center", padding: "80px 0"}}>
          <h2 style={{fontSize: 24, marginBottom: 8}}>导出视频</h2>
          <p className="muted" style={{marginBottom: 16}}>请选择字幕样式后，手动点击“开始导出”。</p>
          <div style={{display: "inline-flex", alignItems: "center", gap: 10, marginBottom: 16}}>
            <label htmlFor="subtitle-theme" style={{fontSize: 14, color: "#334155", fontWeight: 600}}>
              字幕颜色
            </label>
            <select
              id="subtitle-theme"
              value={subtitleTheme}
              onChange={(e) => setSubtitleTheme(e.target.value as SubtitleTheme)}
              disabled={renderBusy}
              style={{
                height: 36,
                padding: "0 12px",
                borderRadius: 8,
                border: "1px solid #cbd5e1",
                background: "#ffffff",
                color: "#0f172a",
                fontSize: 14,
                fontFamily: "inherit",
              }}
            >
              {SUBTITLE_THEME_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div
            style={{
              margin: "0 auto 24px",
              maxWidth: 520,
              textAlign: "left",
              padding: "12px 14px",
              borderRadius: 10,
              border: "1px solid #fcd34d",
              background: "#fffbeb",
              color: "#7c2d12",
              fontSize: 13,
              lineHeight: 1.7,
            }}
          >
            <div>优先使用 Chrome 浏览器导出。</div>
            <div>导出期间请保持当前页面前台运行。</div>
          </div>
          <div style={{display: "flex", flexDirection: "column", alignItems: "center", gap: 20}}>
            {renderBusy && <CircularProgress value={renderProgress} />}
            {renderBusy && <p className="muted">导出中，请保持本页面在前台。</p>}
            {!renderBusy && (
              <button
                className="primary large-btn"
                style={{padding: "0 40px"}}
                onClick={() => {
                  void handleStartRender();
                }}
                disabled={busy}
              >
                {renderDownloadUrl ? "重新导出" : "开始导出"}
              </button>
            )}
            {!renderBusy && renderDownloadUrl && (
              <a href={renderDownloadUrl} download={renderFileName}>
                <button className="primary large-btn" style={{padding: "0 40px"}}>
                  下载视频成品
                </button>
              </a>
            )}
          </div>
        </div>
      )}

      {job.status === STATUS.SUCCEEDED && (
        <div className="fade-in" style={{textAlign: "center", padding: "80px 0"}}>
          <div style={{fontSize: 48, marginBottom: 24}}>🎉</div>
          <h2 style={{fontSize: 24, marginBottom: 8}}>处理完成</h2>
          <p className="muted" style={{marginBottom: 32}}>您的视频已经成功剪辑并渲染完毕。</p>
          <button
            className="primary large-btn"
            style={{padding: "0 40px"}}
            onClick={() => {
              void handleDownloadFinalVideo();
            }}
            disabled={downloadBusy}
          >
            {downloadBusy ? "正在下载..." : "下载视频成品"}
          </button>
        </div>
      )}
    </main>
  );
}
