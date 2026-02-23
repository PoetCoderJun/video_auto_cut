"use client";

import {useState} from "react";
import {useRouter} from "next/navigation";
import {createJob} from "../lib/api";

export default function HomePage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleCreate = async () => {
    setError("");
    setLoading(true);
    try {
      const job = await createJob();
      router.push(`/jobs/${job.job_id}`);
    } catch (err) {
      const message = err instanceof Error ? err.message : "创建任务失败";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <main>
      <div className="card" style={{marginTop: 24}}>
        <h1 style={{fontSize: 30, marginBottom: 10}}>自动口播剪辑 Web 工作台</h1>
        <p className="muted" style={{marginTop: 0, marginBottom: 18}}>
          按照 Upload → Step1 → Step2 → Render 逐步完成。
        </p>
        <div className="row">
          <button className="primary" onClick={handleCreate} disabled={loading}>
            {loading ? "创建中..." : "创建新任务"}
          </button>
        </div>
        {error ? <p className="error">{error}</p> : null}
      </div>
    </main>
  );
}
