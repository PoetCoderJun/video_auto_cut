"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import {
  Zap,
  Video,
  CheckCircle2,
  Play,
  Sparkles,
  LayoutTemplate,
  UploadCloud,
} from "lucide-react";

import {
  activateInviteCode,
  createJob,
  getMe,
  setApiAuthTokenProvider,
  uploadVideo,
} from "../lib/api";
import { authClient } from "../lib/auth-client";
import { ACTIVE_JOB_ID_KEY, PENDING_INVITE_CODE_KEY } from "../lib/session";
import JobWorkspace from "./job-workspace";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

const FAQ_ITEMS = [
  {
    question: "支持哪些视频格式？",
    answer: "当前支持主流视频格式：MP4、MOV、MKV、WebM、M4V、TS、M2TS、MTS。",
  },
  {
    question: "一次处理大概需要多久？",
    answer:
      "取决于视频时长和您的电脑性能，AI 分析仅需几分钟，导出过程由于在本地渲染，速度非常快。",
  },
  {
    question: "是否需要专业剪辑经验？",
    answer: "完全不需要。整个流程按步骤引导，您的重点只是确认文字字幕和章节结构。",
  },
];

export default function HomePageClient() {
  const router = useRouter();
  const [jobId, setJobId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [authBusy, setAuthBusy] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [error, setError] = useState("");
  const [creditBalance, setCreditBalance] = useState<number | null>(null);
  const [userStatus, setUserStatus] = useState("PENDING_COUPON");
  const [inviteNotice, setInviteNotice] = useState("");
  const [isSignedIn, setIsSignedIn] = useState(false);
  const [authAccount, setAuthAccount] = useState("");
  const [apiToken, setApiToken] = useState<string | null>(null);

  const inviteActivated = userStatus === "ACTIVE";

  const getJwtToken = useCallback(async (): Promise<string | null> => {
    try {
      const tokenResult = await (authClient as any).token();
      return String(tokenResult?.data?.token || "").trim() || null;
    } catch {
      return null;
    }
  }, []);

  const syncAuthState = useCallback(async () => {
    try {
      const sessionResult = await (authClient as any).getSession();
      const user = sessionResult?.data?.user;
      if (!user?.id) {
        setIsSignedIn(false);
        setAuthAccount("");
        setApiToken(null);
        setCreditBalance(null);
        setUserStatus("PENDING_COUPON");
        return;
      }
      setIsSignedIn(true);
      const account = String(user.email || user.name || user.id || "").trim();
      setAuthAccount(account);
      setApiToken(await getJwtToken());
    } catch {
      setIsSignedIn(false);
      setAuthAccount("");
      setApiToken(null);
      setCreditBalance(null);
      setUserStatus("PENDING_COUPON");
    }
  }, [getJwtToken]);

  useEffect(() => {
    let alive = true;
    const bootstrap = async () => {
      await syncAuthState();
      if (!alive) return;
      try {
        const cachedJobId = localStorage.getItem(ACTIVE_JOB_ID_KEY)?.trim() || "";
        if (cachedJobId) {
          setJobId(cachedJobId);
        }
      } catch {
        // Ignore storage errors.
      }
      setAuthReady(true);
    };
    void bootstrap();
    return () => {
      alive = false;
    };
  }, [syncAuthState]);

  useEffect(() => {
    setApiAuthTokenProvider(async () => apiToken);
    return () => {
      setApiAuthTokenProvider(null);
    };
  }, [apiToken]);

  useEffect(() => {
    if (!authReady) return;
    if (isSignedIn) return;
    setJobId(null);
    setCreditBalance(null);
    setUserStatus("PENDING_COUPON");
    setInviteNotice("");
    try {
      localStorage.removeItem(ACTIVE_JOB_ID_KEY);
    } catch {
      // Ignore storage failures.
    }
  }, [authReady, isSignedIn]);

  useEffect(() => {
    if (!authReady || !isSignedIn || !apiToken) return;
    let cancelled = false;
    const syncProfile = async () => {
      try {
        const me = await getMe();
        if (cancelled) return;
        setCreditBalance(me.credits.balance);
        setUserStatus(String(me.status || "PENDING_COUPON").toUpperCase());
      } catch (err) {
        if (cancelled) return;
        const message =
          err instanceof Error ? err.message : "登录状态已失效，请重新登录。";
        setError(message);
      }
    };
    void syncProfile();
    return () => {
      cancelled = true;
    };
  }, [authReady, isSignedIn, apiToken]);

  useEffect(() => {
    if (!authReady || !isSignedIn || !apiToken) return;
    if (userStatus !== "PENDING_COUPON") return;
    let cancelled = false;

    const activatePendingInvite = async () => {
      let code = "";
      try {
        code =
          localStorage.getItem(PENDING_INVITE_CODE_KEY)?.trim().toUpperCase() ||
          "";
      } catch {
        code = "";
      }
      if (!code) return;
      try {
        const activation = await activateInviteCode(code);
        if (cancelled) return;
        setCreditBalance(activation.balance);
        setUserStatus("ACTIVE");
        setInviteNotice("注册成功，邀请码已激活。");
        try {
          localStorage.removeItem(PENDING_INVITE_CODE_KEY);
        } catch {
          // Ignore storage failures.
        }
      } catch {
        if (cancelled) return;
        setInviteNotice("检测到注册邀请码，正在后台自动激活，请稍后刷新页面。");
      }
    };

    void activatePendingInvite();
    return () => {
      cancelled = true;
    };
  }, [authReady, isSignedIn, apiToken, userStatus]);

  const saveJobId = useCallback((value: string) => {
    setJobId(value);
    try {
      localStorage.setItem(ACTIVE_JOB_ID_KEY, value);
    } catch {
      // Ignore storage failures.
    }
  }, []);

  const handleBackHome = useCallback(() => {
    setJobId(null);
    try {
      localStorage.removeItem(ACTIVE_JOB_ID_KEY);
    } catch {
      // Ignore storage failures.
    }
  }, []);

  const handleLogout = async () => {
    setAuthBusy(true);
    try {
      await (authClient as any).signOut();
      setApiToken(null);
      setIsSignedIn(false);
      setAuthAccount("");
      setCreditBalance(null);
      setUserStatus("PENDING_COUPON");
      setJobId(null);
      setInviteNotice("");
      try {
        localStorage.removeItem(ACTIVE_JOB_ID_KEY);
      } catch {
        // Ignore storage failures.
      }
    } finally {
      setAuthBusy(false);
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!authReady) return;

    if (!isSignedIn) {
      router.push("/sign-in");
      return;
    }

    if (!inviteActivated) {
      setError("账号尚未完成邀请码激活，请稍后自动重试。");
      return;
    }
    if (!apiToken) {
      setError("登录状态初始化中，请稍后再试。");
      return;
    }

    setError("");
    setLoading(true);
    try {
      const job = await createJob();
      await uploadVideo(job.job_id, file);
      saveJobId(job.job_id);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "创建视频项目失败，请稍后重试。";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  if (jobId) {
    if (!authReady || !isSignedIn || !apiToken) {
      return (
        <main className="container mx-auto flex h-[50vh] flex-col items-center justify-center gap-4">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <p className="text-muted-foreground">正在校验登录状态...</p>
        </main>
      );
    }
    return (
      <div className="min-h-screen bg-background font-sans">
        <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="container mx-auto flex h-14 items-center justify-between px-4 sm:px-6">
            <Link
              href="/"
              className="flex items-center gap-2 font-bold text-lg text-foreground transition-opacity hover:opacity-80"
              onClick={(e) => {
                e.preventDefault();
                handleBackHome();
              }}
            >
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Video className="h-4 w-4" />
              </div>
              <span>AI Cut</span>
            </Link>
            <div className="flex items-center gap-3">
              {isSignedIn && (
                <>
                  {creditBalance !== null && (
                    <Badge variant="secondary" className="px-3 py-1">
                      额度: {creditBalance} 次
                    </Badge>
                  )}
                  <span className="hidden text-sm text-muted-foreground sm:inline-block">
                    {authAccount}
                  </span>
                </>
              )}
            </div>
          </div>
        </header>
        <JobWorkspace
          key={jobId}
          jobId={jobId}
          onBackHome={handleBackHome}
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background font-sans">
      <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto flex h-14 items-center justify-between px-4 sm:px-6">
          <Link
            href="/"
            className="flex items-center gap-2 font-bold text-lg text-foreground transition-opacity hover:opacity-80"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Video className="h-4 w-4" />
            </div>
            <span>AI Cut</span>
          </Link>
          <div className="flex items-center gap-3">
            {!authReady ? null : !isSignedIn ? (
              <>
                <Link href="/sign-in">
                  <Button variant="ghost">登录</Button>
                </Link>
                <Link href="/sign-up">
                  <Button className="rounded-full">注册体验</Button>
                </Link>
              </>
            ) : (
              <>
                {creditBalance !== null && (
                  <Badge variant="secondary" className="px-3 py-1">
                    额度: {creditBalance} 次
                  </Badge>
                )}
                <span className="hidden text-sm text-muted-foreground sm:inline-block">
                  {authAccount}
                </span>
                <Button variant="ghost" onClick={handleLogout} disabled={authBusy}>
                  退出
                </Button>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 sm:px-6">
        {/* Hero Section */}
        <section className="relative pt-20 pb-16 text-center lg:pt-32">
          <div className="absolute inset-x-0 -top-40 -z-10 transform-gpu overflow-hidden blur-3xl sm:-top-80">
            <div
              className="relative left-[calc(50%-11rem)] aspect-[1155/678] w-[36.125rem] -translate-x-1/2 rotate-[30deg] bg-gradient-to-tr from-[#ff80b5] to-[#9089fc] opacity-30 sm:left-[calc(50%-30rem)] sm:w-[72.1875rem]"
              style={{
                clipPath:
                  "polygon(74.1% 44.1%, 100% 61.6%, 97.5% 26.9%, 85.5% 0.1%, 80.7% 2%, 72.5% 32.5%, 60.2% 62.4%, 52.4% 68.1%, 47.5% 58.3%, 45.2% 34.5%, 27.5% 76.7%, 0.1% 64.9%, 17.9% 100%, 27.6% 76.8%, 76.1% 97.7%, 74.1% 44.1%)",
              }}
            />
          </div>

          <div className="mx-auto max-w-2xl">
            <div className="mb-8 flex justify-center">
              <div className="relative rounded-full px-3 py-1 text-sm leading-6 text-muted-foreground ring-1 ring-border/60 hover:ring-border/80 bg-background/50 backdrop-blur-sm">
                <span className="flex items-center gap-1.5 font-semibold text-foreground">
                  <Zap className="h-4 w-4 text-amber-500 fill-amber-500" />
                  让口播视频剪辑提速 95%
                </span>
              </div>
            </div>

            <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-6xl mb-6">
              极简{" "}
              <span className="bg-gradient-to-r from-foreground to-indigo-600 bg-clip-text text-transparent">
                AI 视频剪辑
              </span>
            </h1>

            <p className="mt-6 text-lg leading-8 text-muted-foreground">
              自动剔除废话、精简字幕并生成章节，<br />
              无需专业剪辑经验，专注于内容创作本身。
            </p>

            <div className="mt-10 flex flex-col items-center justify-center gap-6">
              {/* Direct Upload Area */}
              <div
                className={cn(
                  "relative group w-full max-w-lg cursor-pointer rounded-xl border-2 border-dashed border-muted-foreground/25 bg-card p-10 transition-all hover:border-primary/50 hover:bg-muted/30",
                  loading && "opacity-70 cursor-not-allowed"
                )}
              >
                <input
                  type="file"
                  accept=".mp4,.mov,.mkv,.webm,.m4v,.ts,.m2ts,.mts"
                  onChange={handleFileSelect}
                  disabled={loading || !authReady}
                  className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
                />
                <div className="flex flex-col items-center justify-center gap-4 text-center">
                  <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/5 text-primary">
                    {loading ? (
                      <div className="h-6 w-6 animate-spin rounded-full border-2 border-current border-t-transparent" />
                    ) : (
                      <UploadCloud className="h-8 w-8" />
                    )}
                  </div>
                  <div className="space-y-1">
                    <h3 className="font-semibold text-lg text-foreground">
                      {loading ? "正在上传并分析..." : "点击或拖拽上传视频"}
                    </h3>
                    <p className="text-sm text-muted-foreground">
                      支持 MP4, MOV, MKV 等主流格式
                    </p>
                  </div>
                  {!isSignedIn && authReady && (
                    <Badge variant="outline" className="text-amber-600 bg-amber-50 border-amber-200 mt-2">
                      需登录后使用
                    </Badge>
                  )}
                </div>
              </div>

              {inviteNotice && (
                <div className="flex items-center gap-2 rounded-full bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-700 border border-emerald-200">
                  <CheckCircle2 className="h-4 w-4" />
                  {inviteNotice}
                </div>
              )}

              {error && (
                <div className="w-full max-w-lg rounded-md bg-destructive/10 p-3 text-sm font-medium text-destructive text-center border border-destructive/20">
                  {error}
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Feature Grid */}
        <section id="features" className="py-16">
          <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
            {[
              {
                title: "智能字幕生成",
                desc: "自动识别视频语音，生成高精度字幕，支持多种主流视频格式。",
                icon: <LayoutTemplate className="h-6 w-6 text-blue-500" />,
              },
              {
                title: "智能剪辑剔除",
                desc: "自动分析静音与废话片段，一键剔除冗余内容，保留精华。",
                icon: <Sparkles className="h-6 w-6 text-purple-500" />,
              },
              {
                title: "智能章节划分",
                desc: "根据内容语义自动划分章节，生成清晰的视频结构大纲。",
                icon: <Play className="h-6 w-6 text-red-500" />,
              },
            ].map((f, i) => (
              <Card key={i} className="border-muted bg-card shadow-sm transition-all hover:shadow-md hover:-translate-y-1">
                <CardHeader>
                  <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                    {f.icon}
                  </div>
                  <CardTitle className="text-lg">{f.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-base leading-relaxed">
                    {f.desc}
                  </CardDescription>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="mx-auto max-w-3xl py-16">
          <div className="mb-10 text-center">
            <h2 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
              常见问题
            </h2>
          </div>
          <div className="space-y-4">
            {FAQ_ITEMS.map((item, index) => (
              <details
                key={index}
                className="group rounded-lg border border-border bg-card px-6 py-4 shadow-sm [&_summary::-webkit-details-marker]:hidden"
              >
                <summary className="flex cursor-pointer items-center justify-between font-medium text-foreground group-hover:text-primary">
                  {item.question}
                  <span className="ml-4 transition-transform duration-300 group-open:rotate-45">
                    <span className="block h-4 w-4 text-muted-foreground">+</span>
                  </span>
                </summary>
                <div className="mt-4 text-sm leading-relaxed text-muted-foreground">
                  {item.answer}
                </div>
              </details>
            ))}
          </div>
        </section>

        {/* Author */}
        <section className="border-t border-border py-16">
          <div className="mx-auto max-w-md">
            <Card className="text-center shadow-lg">
              <CardContent className="pt-8">
                <div className="relative mx-auto mb-4 h-20 w-20 overflow-hidden rounded-full border-2 border-border">
                  <a
                    href="https://xhslink.com/m/2CUIT8iyntn"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Image
                      src="/photo.jpg"
                      alt="Jun"
                      fill
                      className="object-cover"
                    />
                  </a>
                </div>
                <h3 className="mb-2 text-lg font-bold text-foreground">
                  诗人程序员Jun
                </h3>
                <div className="mb-6 inline-flex items-center gap-2 rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
                  <span>AI builder in HK</span>
                  <span className="h-1 w-1 rounded-full bg-muted-foreground/30" />
                  <span>Vibe coding 主理人</span>
                </div>
                <p className="text-sm text-muted-foreground">
                  合作 / 工作机会等，欢迎关注{" "}
                  <a
                    href="https://xhslink.com/m/2CUIT8iyntn"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="font-semibold text-foreground underline hover:text-primary"
                  >
                    小红书
                  </a>{" "}
                  随时私信我。
                </p>
              </CardContent>
            </Card>
          </div>
        </section>
      </main>

      <footer className="border-t border-border bg-muted/30 py-8 text-center text-xs text-muted-foreground">
        <p>&copy; {new Date().getFullYear()} AI Cut. All rights reserved.</p>
      </footer>
    </div>
  );
}
