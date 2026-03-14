"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Copy, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { claimPublicInviteCode } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type ClaimState = {
  code: string;
  alreadyClaimed: boolean;
} | null;

export default function InviteClaimPageClient() {
  const [claim, setClaim] = useState<ClaimState>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadInvite() {
      const maxAttempts = 4;

      for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
        try {
          const result = await claimPublicInviteCode();
          if (cancelled) return;
          setClaim({
            code: result.code,
            alreadyClaimed: result.already_claimed,
          });
          setError("");
          return;
        } catch (err) {
          if (cancelled) return;
          const message = err instanceof Error ? err.message : "邀请码领取失败，请稍后重试";
          if (attempt >= maxAttempts) {
            setError(message);
            return;
          }
          await new Promise((resolve) => setTimeout(resolve, attempt * 1200));
        } finally {
          if (!cancelled && attempt === maxAttempts) {
            setLoading(false);
          }
        }
      }
    }

    void loadInvite().finally(() => {
      if (!cancelled) {
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleCopy = async () => {
    if (!claim?.code) return;
    try {
      await navigator.clipboard.writeText(claim.code);
      toast.success("邀请码已复制");
    } catch {
      toast.error("复制失败，请手动复制邀请码");
    }
  };

  const signUpHref = claim ? `/sign-up?invite=${encodeURIComponent(claim.code)}` : "/sign-up";

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,rgba(251,191,36,0.14),transparent_30%),linear-gradient(180deg,#fffdf7_0%,#fff 45%,#fff7ed_100%)]">
      <main className="container mx-auto flex min-h-screen max-w-xl items-center px-4 py-10 sm:px-6 sm:py-16">
        <Card className="w-full border-border/70 bg-background/95 shadow-sm">
          <CardHeader className="space-y-3 text-center">
            <CardTitle className="text-2xl sm:text-3xl">邀请码</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {loading ? (
              <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-border bg-muted/20 px-6 py-10 text-sm text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>正在为你准备邀请码...</span>
              </div>
            ) : error ? (
              <div className="rounded-2xl border border-dashed border-border bg-muted/20 px-6 py-10 text-center text-sm leading-6 text-muted-foreground">
                {error}
              </div>
            ) : claim ? (
              <div className="space-y-6">
                <div className="rounded-2xl border border-border bg-muted/30 px-6 py-8 text-center">
                  <p className="text-sm text-muted-foreground">
                    {claim.alreadyClaimed ? "你之前领取的邀请码" : "你的邀请码"}
                  </p>
                  <p className="mt-3 font-mono text-2xl font-semibold tracking-[0.24em] text-foreground sm:text-3xl">
                    {claim.code}
                  </p>
                </div>

                <Button variant="outline" onClick={handleCopy} className="h-11 w-full rounded-full">
                  <Copy className="mr-2 h-4 w-4" />
                  请复制邀请码
                </Button>

                <Link href={signUpHref}>
                  <Button className="h-11 w-full rounded-full">
                    注册（进去之后自动填写邀请码）
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Button>
                </Link>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
