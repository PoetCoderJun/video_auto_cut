"use client";

import {useCallback, useEffect, useMemo, useState} from "react";
import {
  Chapter,
  Job,
  Step1Line,
  confirmStep1,
  confirmStep2,
  getDownloadUrl,
  getJob,
  getStep1,
  getStep2,
  runRender,
  runStep1,
  runStep2,
  uploadVideo,
} from "../../../lib/api";
import {
  DONE_STATUSES,
  RUNNING_STATUSES,
  STATUS,
  STEP1_LOADABLE_STATUSES,
  STEP2_LOADABLE_STATUSES,
} from "../../../lib/workflow";

function statusClass(status: string): string {
  if (status === STATUS.FAILED) return "status-badge failed";
  if (RUNNING_STATUSES.has(status as Job["status"])) return "status-badge running";
  if (DONE_STATUSES.has(status as Job["status"])) return "status-badge done";
  return "status-badge";
}

export default function JobPage({params}: {params: {jobId: string}}) {
  const jobId = params.jobId;
  const [job, setJob] = useState<Job | null>(null);
  const [lines, setLines] = useState<Step1Line[]>([]);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionText, setActionText] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

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
        setError("无法连接 API，请确认 uvicorn 正在运行（127.0.0.1:8000）");
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
    if (!STEP1_LOADABLE_STATUSES.has(job.status)) return;
    if (lines.length > 0) return;

    getStep1(jobId)
      .then((data) => setLines(data))
      .catch(() => undefined);
  }, [job, lines.length, jobId]);

  useEffect(() => {
    if (!job) return;
    if (!STEP2_LOADABLE_STATUSES.has(job.status)) return;
    if (chapters.length > 0) return;

    getStep2(jobId)
      .then((data) => setChapters(data))
      .catch(() => undefined);
  }, [job, chapters.length, jobId]);

  const uploadDisabled = useMemo(
    () => !job || job.status !== STATUS.CREATED || !selectedFile || busy,
    [job, selectedFile, busy],
  );

  const handleUpload = async () => {
    if (!selectedFile) return;
    setError("");
    setBusy(true);
    setActionText(`上传中：${selectedFile.name}`);
    try {
      const next = await uploadVideo(jobId, selectedFile);
      setJob(next);
      setSelectedFile(null);
      await refreshJob();
      setActionText(`上传完成，当前状态：${next.status}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
      setActionText("上传失败");
    } finally {
      setBusy(false);
    }
  };

  const handleRunStep1 = async () => {
    setError("");
    setBusy(true);
    setActionText("正在启动 Step1 ...");
    try {
      await runStep1(jobId);
      await refreshJob();
      setLines([]);
      setActionText("Step1 已启动，等待处理完成");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Step1 启动失败");
      setActionText("Step1 启动失败");
    } finally {
      setBusy(false);
    }
  };

  const handleConfirmStep1 = async () => {
    setError("");
    setBusy(true);
    setActionText("正在确认 Step1 ...");
    try {
      await confirmStep1(jobId, lines);
      await refreshJob();
      setActionText("Step1 已确认");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Step1 确认失败");
      setActionText("Step1 确认失败");
    } finally {
      setBusy(false);
    }
  };

  const handleRunStep2 = async () => {
    setError("");
    setBusy(true);
    setActionText("正在启动 Step2 ...");
    try {
      await runStep2(jobId);
      await refreshJob();
      setChapters([]);
      setActionText("Step2 已启动，等待处理完成");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Step2 启动失败");
      setActionText("Step2 启动失败");
    } finally {
      setBusy(false);
    }
  };

  const handleConfirmStep2 = async () => {
    setError("");
    setBusy(true);
    setActionText("正在确认 Step2 ...");
    try {
      await confirmStep2(jobId, chapters);
      await refreshJob();
      setActionText("Step2 已确认");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Step2 确认失败");
      setActionText("Step2 确认失败");
    } finally {
      setBusy(false);
    }
  };

  const handleRunRender = async () => {
    setError("");
    setBusy(true);
    setActionText("正在启动渲染 ...");
    try {
      await runRender(jobId);
      await refreshJob();
      setActionText("渲染已启动，等待完成");
    } catch (err) {
      setError(err instanceof Error ? err.message : "渲染启动失败");
      setActionText("渲染启动失败");
    } finally {
      setBusy(false);
    }
  };

  const updateLine = (lineId: number, patch: Partial<Step1Line>) => {
    setLines((prev) => prev.map((line) => (line.line_id === lineId ? {...line, ...patch} : line)));
  };

  const updateChapter = (chapterId: number, patch: Partial<Chapter>) => {
    setChapters((prev) =>
      prev.map((chapter) => (chapter.chapter_id === chapterId ? {...chapter, ...patch} : chapter)),
    );
  };

  return (
    <main>
      <div className="card" style={{marginTop: 16}}>
        <div className="row" style={{justifyContent: "space-between", alignItems: "center"}}>
          <h1 style={{fontSize: 24}}>任务 {jobId}</h1>
          <button className="ghost" onClick={() => refreshJob()} disabled={busy}>
            刷新状态
          </button>
        </div>
        <div className="row" style={{marginTop: 10, alignItems: "center"}}>
          <span className={statusClass(job?.status || STATUS.CREATED)}>{job?.status || "LOADING"}</span>
          <span className="muted">进度：{job?.progress ?? 0}%</span>
        </div>
        <div className="progress-wrap" style={{marginTop: 10}}>
          <div className="progress-bar" style={{width: `${job?.progress ?? 0}%`}} />
        </div>
        {job?.error ? <p className="error">{job.error.message}</p> : null}
        {error ? <p className="error">{error}</p> : null}
        {actionText ? <p className="muted">操作状态：{actionText}</p> : null}
      </div>

      <div className="card" style={{marginTop: 14}}>
        <h2 style={{fontSize: 20}}>Step 0 上传视频</h2>
        <div className="row" style={{marginTop: 10}}>
          <input
            type="file"
            accept="video/*"
            onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
          />
          <button className="primary" onClick={handleUpload} disabled={uploadDisabled}>
            {busy && actionText.startsWith("上传中") ? "上传中..." : "上传并校验"}
          </button>
        </div>
        <p className="muted">仅在状态 CREATED 可上传。限制由后端 MAX_UPLOAD_MB 控制。</p>
      </div>

      <div className="card" style={{marginTop: 14}}>
        <div className="row" style={{justifyContent: "space-between", alignItems: "center"}}>
          <h2 style={{fontSize: 20}}>Step 1 字幕优化与删减确认</h2>
          <div className="row">
            <button onClick={handleRunStep1} disabled={!job || job.status !== STATUS.UPLOAD_READY || busy}>
              运行 Step1
            </button>
            <button
              className="primary"
              onClick={handleConfirmStep1}
              disabled={!job || job.status !== STATUS.STEP1_READY || lines.length === 0 || busy}
            >
              确认 Step1
            </button>
          </div>
        </div>
        <div style={{marginTop: 10, overflowX: "auto"}}>
          <table>
            <thead>
              <tr>
                <th style={{width: 70}}>行号</th>
                <th style={{width: 130}}>时间</th>
                <th>原文</th>
                <th>优化文本</th>
                <th style={{width: 110}}>删除</th>
              </tr>
            </thead>
            <tbody>
              {lines.map((line) => (
                <tr key={line.line_id}>
                  <td>{line.line_id}</td>
                  <td>
                    {line.start.toFixed(1)} - {line.end.toFixed(1)}
                  </td>
                  <td>{line.original_text}</td>
                  <td>
                    <textarea
                      value={line.optimized_text}
                      onChange={(event) =>
                        updateLine(line.line_id, {optimized_text: event.target.value})
                      }
                    />
                  </td>
                  <td>
                    <label>
                      <input
                        type="checkbox"
                        checked={line.user_final_remove}
                        onChange={(event) =>
                          updateLine(line.line_id, {user_final_remove: event.target.checked})
                        }
                      />
                      {line.ai_suggest_remove ? " AI建议" : " 手动"}
                    </label>
                  </td>
                </tr>
              ))}
              {lines.length === 0 ? (
                <tr>
                  <td colSpan={5} className="muted">
                    暂无 Step1 数据
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card" style={{marginTop: 14}}>
        <div className="row" style={{justifyContent: "space-between", alignItems: "center"}}>
          <h2 style={{fontSize: 20}}>Step 2 章节确认</h2>
          <div className="row">
            <button onClick={handleRunStep2} disabled={!job || job.status !== STATUS.STEP1_CONFIRMED || busy}>
              运行 Step2
            </button>
            <button
              className="primary"
              onClick={handleConfirmStep2}
              disabled={!job || job.status !== STATUS.STEP2_READY || chapters.length === 0 || busy}
            >
              确认 Step2
            </button>
          </div>
        </div>
        <div style={{marginTop: 10}}>
          {chapters.map((chapter) => (
            <div key={chapter.chapter_id} className="card" style={{marginBottom: 10, boxShadow: "none"}}>
              <div className="row" style={{alignItems: "center"}}>
                <strong>章节 {chapter.chapter_id}</strong>
                <span className="muted">
                  {chapter.start.toFixed(1)} - {chapter.end.toFixed(1)}
                </span>
              </div>
              <div className="row" style={{marginTop: 8}}>
                <div style={{flex: "1 1 280px"}}>
                  <label>标题</label>
                  <input
                    type="text"
                    value={chapter.title}
                    onChange={(event) => updateChapter(chapter.chapter_id, {title: event.target.value})}
                  />
                </div>
                <div style={{flex: "1 1 380px"}}>
                  <label>摘要</label>
                  <input
                    type="text"
                    value={chapter.summary}
                    onChange={(event) => updateChapter(chapter.chapter_id, {summary: event.target.value})}
                  />
                </div>
              </div>
            </div>
          ))}
          {chapters.length === 0 ? <p className="muted">暂无 Step2 数据</p> : null}
        </div>
      </div>

      <div className="card" style={{marginTop: 14}}>
        <div className="row" style={{justifyContent: "space-between", alignItems: "center"}}>
          <h2 style={{fontSize: 20}}>Step 3 渲染与下载</h2>
          <div className="row">
            <button
              onClick={handleRunRender}
              disabled={!job || job.status !== STATUS.STEP2_CONFIRMED || busy}
            >
              启动渲染
            </button>
            <a href={getDownloadUrl(jobId)}>
              <button className="primary" disabled={!job || job.status !== STATUS.SUCCEEDED}>
                下载视频
              </button>
            </a>
          </div>
        </div>
      </div>
    </main>
  );
}
