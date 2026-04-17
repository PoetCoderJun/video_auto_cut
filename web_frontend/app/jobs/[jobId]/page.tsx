"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ACTIVE_JOB_ID_KEY } from "@/lib/session";
import { Loader2 } from "lucide-react";

export default function LegacyJobRoutePage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const router = useRouter();
  const { jobId } = use(params);

  useEffect(() => {
    try {
      localStorage.setItem(ACTIVE_JOB_ID_KEY, jobId);
    } catch {
      // Ignore storage failures and still redirect to root.
    }
    router.replace("/");
  }, [jobId, router]);

  return (
    <main className="flex h-screen flex-col items-center justify-center gap-4">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
      <p className="text-muted-foreground">正在跳转到首页...</p>
    </main>
  );
}
