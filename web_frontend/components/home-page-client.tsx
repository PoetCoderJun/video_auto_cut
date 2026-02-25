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
  ApiClientError,
  activateInviteCode,
  createJob,
  getMe,
  setApiAuthTokenProvider,
  uploadVideo,
} from "../lib/api";
import { authClient } from "../lib/auth-client";
import {
  ACTIVE_JOB_ID_KEY,
  LEGACY_PENDING_INVITE_CODE_KEY,
  pendingInviteCodeKeyForUser,
} from "../lib/session";
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

type UserStatus = "UNKNOWN" | "ACTIVE" | "PENDING_COUPON";
type ProfileLoadState = "idle" | "loading" | "ready" | "error";
const PROFILE_SYNC_MAX_ATTEMPTS = 3;
const PROFILE_SYNC_RETRY_BASE_MS = 800;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function isAuthMessage(message: string): boolean {
  return message.includes("请先登录") || message.includes("登录状态无效");
}

function isAuthError(err: unknown): boolean {
  if (err instanceof ApiClientError && err.code === "UNAUTHORIZED") {
    return true;
  }
  const message = err instanceof Error ? err.message : String(err);
  return isAuthMessage(message);
}

export default function HomePageClient() {
  const router = useRouter();
  const [jobId, setJobId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [authBusy, setAuthBusy] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [error, setError] = useState("");
  const [creditBalance, setCreditBalance] = useState<number | null>(null);
  const [userStatus, setUserStatus] = useState<UserStatus>("UNKNOWN");
  const [profileState, setProfileState] = useState<ProfileLoadState>("idle");
  const [inviteNotice, setInviteNotice] = useState("");
  const [isSignedIn, setIsSignedIn] = useState(false);
  const [authAccount, setAuthAccount] = useState("");
  const [apiToken, setApiToken] = useState<string | null>(null);
  const [authUserId, setAuthUserId] = useState<string | null>(null);
  const [profileSyncNonce, setProfileSyncNonce] = useState(0);

  const inviteActivated = userStatus === "ACTIVE";
  const profileLoading =
    isSignedIn && (profileState === "idle" || profileState === "loading");

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
        setAuthUserId(null);
        setAuthAccount("");
        setApiToken(null);
        setCreditBalance(null);
        setUserStatus("UNKNOWN");
        setProfileState("idle");
        return;
      }
      setIsSignedIn(true);
      setAuthUserId(String(user.id));
      const account = String(user.email || user.name || user.id || "").trim();
      setAuthAccount(account);
      setCreditBalance(null);
      setUserStatus("UNKNOWN");
      setProfileState("idle");
      setApiToken(await getJwtToken());
    } catch {
      setIsSignedIn(false);
      setAuthUserId(null);
      setAuthAccount("");
      setApiToken(null);
      setCreditBalance(null);
      setUserStatus("UNKNOWN");
      setProfileState("idle");
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
    setUserStatus("UNKNOWN");
    setProfileState("idle");
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
    setProfileState("loading");

    const syncProfile = async () => {
      for (let attempt = 1; attempt <= PROFILE_SYNC_MAX_ATTEMPTS; attempt += 1) {
        if (cancelled) return;
        try {
          const me = await getMe();
          if (cancelled) return;
          setCreditBalance(me.credits.balance);
          const normalizedStatus = String(me.status || "PENDING_COUPON").toUpperCase();
          setUserStatus(normalizedStatus === "ACTIVE" ? "ACTIVE" : "PENDING_COUPON");
          setProfileState("ready");
          return;
        } catch (err) {
          if (cancelled) return;
          const message =
            err instanceof Error ? err.message : "登录状态已失效，请重新登录。";
          const shouldRetry =
            !isAuthError(err) && attempt < PROFILE_SYNC_MAX_ATTEMPTS;
          if (shouldRetry) {
            await sleep(PROFILE_SYNC_RETRY_BASE_MS * attempt);
            continue;
          }
          setUserStatus("UNKNOWN");
          setProfileState("error");
          setError(message);
          return;
        }
      }
    };
    void syncProfile();
    return () => {
      cancelled = true;
    };
  }, [authReady, isSignedIn, apiToken, profileSyncNonce]);

  useEffect(() => {
    if (!authReady || !isSignedIn || !apiToken || !authUserId) return;
    if (profileState !== "ready") return;
    if (userStatus !== "PENDING_COUPON") return;
    let cancelled = false;

    const activatePendingInvite = async () => {
      const scopedKey = pendingInviteCodeKeyForUser(authUserId);
      let code = "";
      try {
        code = localStorage.getItem(scopedKey)?.trim().toUpperCase() || "";
        localStorage.removeItem(LEGACY_PENDING_INVITE_CODE_KEY);
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
          localStorage.removeItem(scopedKey);
        } catch {
          // Ignore storage failures.
        }
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "邀请码自动激活失败";
        const isPermanentInviteError =
          message.includes("邀请码") &&
          (message.includes("已被使用") ||
            message.includes("无效") ||
            message.includes("已过期"));
        if (isPermanentInviteError) {
          setInviteNotice(`邀请码激活失败：${message}`);
          try {
            localStorage.removeItem(scopedKey);
          } catch {
            // Ignore storage failures.
          }
          return;
        }
        setInviteNotice("检测到注册邀请码，正在后台自动激活，请稍后重试。");
      }
    };

    void activatePendingInvite();
    return () => {
      cancelled = true;
    };
  }, [authReady, isSignedIn, apiToken, userStatus, profileState, authUserId]);

  useEffect(() => {
    if (!isSignedIn || profileState !== "ready" || !inviteActivated) return;
    setError((previous) => {
      if (
        previous.includes("账号状态加载中") ||
        previous.includes("账号状态校验失败") ||
        previous.includes("尚未完成邀请码激活")
      ) {
        return "";
      }
      return previous;
    });
  }, [isSignedIn, profileState, inviteActivated]);

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
      setAuthUserId(null);
      setAuthAccount("");
      setCreditBalance(null);
      setUserStatus("UNKNOWN");
      setProfileState("idle");
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

  const handleRetryProfileSync = () => {
    setError((previous) => {
      if (
        previous.includes("登录状态") ||
        previous.includes("账号状态校验失败") ||
        previous.includes("无法连接 API")
      ) {
        return "";
      }
      return previous;
    });
    setProfileState("idle");
    setProfileSyncNonce((previous) => previous + 1);
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;

    if (!authReady) {
      setError("登录状态初始化中，请稍后再试。");
      return;
    }

    if (!isSignedIn) {
      router.push("/sign-in");
      return;
    }

    if (!apiToken) {
      setError("登录状态初始化中，请稍后再试。");
      return;
    }

    if (profileState === "idle" || profileState === "loading") {
      setError("账号状态加载中，请稍后自动重试。");
      return;
    }

    if (profileState === "error") {
      setError("账号状态校验失败，请刷新页面后重试。");
      return;
    }

    if (!inviteActivated) {
      setError("账号尚未完成邀请码激活，请先完成激活。");
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
              AI口播{" "}
              <span className="bg-gradient-to-r from-foreground to-indigo-600 bg-clip-text text-transparent">
                一键剪辑
              </span>
            </h1>

            <p className="mt-6 text-lg leading-8 text-muted-foreground">
              AI自动剔除废话、精简字幕并自动渲染成品视频，<br />
              自动完成且人工可修改。
            </p>

            <div className="mt-10 flex flex-col items-center justify-center gap-6">
              {/* Direct Upload Area */}
              <div
                className={cn(
                  "relative group w-full max-w-lg cursor-pointer rounded-xl border-2 border-dashed border-muted-foreground/25 bg-card p-10 transition-all hover:border-primary/50 hover:bg-muted/30",
                  (loading || profileLoading) && "opacity-70 cursor-not-allowed"
                )}
              >
                <input
                  type="file"
                  accept=".mp4,.mov,.mkv,.webm,.m4v,.ts,.m2ts,.mts"
                  onChange={handleFileSelect}
                  disabled={loading || !authReady || profileLoading}
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
                  {profileLoading && (
                    <Badge variant="outline" className="text-sky-600 bg-sky-50 border-sky-200 mt-2">
                      正在同步账号状态...
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
                  <p>{error}</p>
                  {isSignedIn && profileState === "error" && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="mt-3 border-destructive/40 text-destructive hover:bg-destructive/10"
                      onClick={handleRetryProfileSync}
                    >
                      重试账号状态
                    </Button>
                  )}
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
                title: "自动渲染字幕、进度条、章节",
                desc: "并且加入亮点，未来有更多渲染和AI的可选项即将推出。",
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
