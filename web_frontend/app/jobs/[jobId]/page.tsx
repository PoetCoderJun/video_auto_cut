"use client";

import {useEffect} from "react";
import {useRouter} from "next/navigation";
import {ACTIVE_JOB_ID_KEY} from "../../../lib/session";

export default function LegacyJobRoutePage({params}: {params: {jobId: string}}) {
  const router = useRouter();

  useEffect(() => {
    try {
      localStorage.setItem(ACTIVE_JOB_ID_KEY, params.jobId);
    } catch {
      // Ignore storage failures and still redirect to root.
    }
    router.replace("/");
  }, [params.jobId, router]);

  return (
    <main>
      <div className="loading-view">
        <div className="spinner"></div>
        <p>正在跳转到首页...</p>
      </div>
    </main>
  );
}
