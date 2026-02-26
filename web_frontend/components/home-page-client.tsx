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
  UploadCloud,
  Scissors,
  ShieldCheck,
  ArrowRight,
} from "lucide-react";

import {
  ApiClientError,
  activateInviteCode,
  createJob,
  getMe,
  invalidateTokenCache,
  setApiAuthTokenProvider,
  uploadAudio,
} from "../lib/api";
import { extractAudioForAsr } from "../lib/audio-extract";
import { saveCachedJobSourceVideo } from "../lib/video-cache";
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

const LANDING_STATS = [
  { label: "剪辑准备时间", value: "95%", hint: "平均可节省" },
  { label: "上手门槛", value: "0", hint: "无需专业经验" },
  { label: "流程步骤", value: "3", hint: "上传到导出" },
];

const FLOW_STEPS = [
  {
    title: "上传视频",
    description: "直接上传口播视频，系统自动提取语音与字幕。",
    icon: <UploadCloud className="h-5 w-5 text-indigo-600" />,
  },
  {
    title: "AI 智能精简",
    description: "自动识别废话、停顿和重复表达，生成更紧凑内容。",
    icon: <Scissors className="h-5 w-5 text-violet-600" />,
  },
  {
    title: "快速导出成片",
    description: "自动渲染字幕、进度条和章节，导出可发布视频。",
    icon: <Play className="h-5 w-5 text-rose-600" />,
  },
];

type UserStatus = "UNKNOWN" | "ACTIVE" | "PENDING_COUPON";

export default function HomePageClient() {
  const router = useRouter();
  const [jobId, setJobId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [authBusy, setAuthBusy] = useState(false);
  const [error, setError] = useState("");
  const [creditBalance, setCreditBalance] = useState<number | null>(null);
  const [userStatus, setUserStatus] = useState<UserStatus>("UNKNOWN");
  const [inviteNotice, setInviteNotice] = useState("");
  const [isSignedIn, setIsSignedIn] = useState(false);
  const [authAccount, setAuthAccount] = useState("");

  // Set up a lazy token provider. JWT is fetched on first API request and cached
  // in api.ts for ~4 minutes; no network call on page mount.
  useEffect(() => {
    setApiAuthTokenProvider(async () => {
      const result = await (authClient as any).token();
      return String(result?.data?.token || "").trim() || null;
    });
    return () => setApiAuthTokenProvider(null);
  }, []);

  // On mount: restore cached job ID and do a lightweight background session check
  // (getSession only — no token fetch, no /me call) so the header reflects the
  // signed-in state without blocking page render.
  useEffect(() => {
    let alive = true;
    try {
      const cached = localStorage.getItem(ACTIVE_JOB_ID_KEY)?.trim() || "";
      if (cached && alive) setJobId(cached);
    } catch {
      // Ignore storage errors.
    }
    (authClient as any).getSession().then((result: any) => {
      if (!alive) return;
      const user = result?.data?.user;
      if (user?.id) {
        setIsSignedIn(true);
        setAuthAccount(String(user.email || user.name || user.id || "").trim());
      }
    }).catch(() => undefined);
    return () => { alive = false; };
  }, []);

  const saveJobId = useCallback((id: string) => {
    setJobId(id);
    try {
      localStorage.setItem(ACTIVE_JOB_ID_KEY, id);
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
      invalidateTokenCache();
      setIsSignedIn(false);
      setAuthAccount("");
      setCreditBalance(null);
      setUserStatus("UNKNOWN");
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

  // Auth and profile checks happen here, only when user actually tries to upload.
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;

    setError("");
    setLoading(true);
    try {
      // 0. Check video duration — reject anything over 30 minutes.
      const durationSec = await new Promise<number>((resolve) => {
        const url = URL.createObjectURL(file);
        const video = document.createElement("video");
        video.preload = "metadata";
        video.onloadedmetadata = () => {
          URL.revokeObjectURL(url);
          resolve(video.duration);
        };
        video.onerror = () => {
          URL.revokeObjectURL(url);
          resolve(0);
        };
        video.src = url;
      });
      if (durationSec > 30 * 60) {
        const mins = Math.floor(durationSec / 60);
        const secs = Math.round(durationSec % 60);
        setError(
          `视频时长 ${mins} 分 ${secs} 秒，超过 30 分钟限制，请上传更短的视频。`
        );
        return;
      }

      // 1. Verify session lazily at consumption time.
      const sessionResult = await (authClient as any).getSession();
      const user = sessionResult?.data?.user;
      if (!user?.id) {
        router.push("/sign-in");
        return;
      }
      const userId = String(user.id);
      setIsSignedIn(true);
      setAuthAccount(String(user.email || user.name || user.id || "").trim());

      // 2. Fetch profile to check account status and credits.
      let me;
      try {
        me = await getMe();
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "账号状态校验失败，请稍后重试。";
        setError(message);
        return;
      }
      setCreditBalance(me.credits.balance);
      const status = String(me.status || "PENDING_COUPON").toUpperCase();
      let isActive = status === "ACTIVE";
      setUserStatus(isActive ? "ACTIVE" : "PENDING_COUPON");

      // 3. If not active, try to activate a pending invite code from localStorage.
      if (!isActive) {
        const scopedKey = pendingInviteCodeKeyForUser(userId);
        let code = "";
        try {
          code = localStorage.getItem(scopedKey)?.trim().toUpperCase() || "";
          localStorage.removeItem(LEGACY_PENDING_INVITE_CODE_KEY);
        } catch {
          code = "";
        }
        if (code) {
          try {
            const activation = await activateInviteCode(code);
            setCreditBalance(activation.balance);
            setUserStatus("ACTIVE");
            setInviteNotice("注册成功，邀请码已激活。");
            isActive = true;
            try {
              localStorage.removeItem(scopedKey);
            } catch {
              // Ignore storage failures.
            }
          } catch (err) {
            const msg = err instanceof Error ? err.message : "";
            const isPermanent =
              msg.includes("邀请码") &&
              (msg.includes("已被使用") ||
                msg.includes("无效") ||
                msg.includes("已过期"));
            if (isPermanent) {
              setInviteNotice(`邀请码激活失败：${msg}`);
              try {
                localStorage.removeItem(scopedKey);
              } catch {
                // Ignore storage failures.
              }
            } else {
              setInviteNotice("检测到注册邀请码，正在后台自动激活，请稍后重试。");
            }
          }
        }
      }

      if (!isActive) {
        setError("账号尚未完成邀请码激活，请先完成激活。");
        return;
      }

      // 4. Create job and upload.
      const job = await createJob();
      const audioFile = await extractAudioForAsr(file);
      await uploadAudio(job.job_id, audioFile);
      // 必须等本地缓存写入完成再切到任务页，否则任务页 mount 时 loadCachedJobSourceVideo 可能还没写到 IndexedDB，导出时会报「缺少本地原始视频」
      await saveCachedJobSourceVideo(job.job_id, file).catch(() => undefined);
      saveJobId(job.job_id);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "创建项目失败，请稍后重试。";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  if (jobId) {
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
          <nav className="hidden items-center gap-6 text-sm text-muted-foreground md:flex">
            <a href="#how-it-works" className="transition-colors hover:text-foreground">
              如何使用
            </a>
            <a href="#faq" className="transition-colors hover:text-foreground">
              常见问题
            </a>
          </nav>
          <div className="flex items-center gap-3">
            {!isSignedIn ? (
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
        <section className="relative pt-14 pb-14 text-center lg:pt-24">
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
                  AI 自动剪辑，让口播制作提速 95%
                </span>
              </div>
            </div>

            <h1 className="mb-6 text-4xl font-extrabold tracking-tight text-foreground sm:text-6xl">
              AI 口播视频{" "}
              <span className="bg-gradient-to-r from-foreground to-indigo-600 bg-clip-text text-transparent">
                一键精剪与导出
              </span>
            </h1>

            <p className="mt-6 text-lg leading-8 text-muted-foreground">
              自动剔除废话、整理章节并渲染字幕效果，几分钟完成口播后期。<br />
              全流程可编辑，既快又可控。
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
                  disabled={loading}
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
                      支持 MP4, MOV, MKV 等主流格式 · 最长 30 分钟
                    </p>
                  </div>
                  {!isSignedIn && (
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
                  <p>{error}</p>
                </div>
              )}
            </div>

            <div className="mx-auto mt-12 grid max-w-3xl grid-cols-1 gap-3 sm:grid-cols-3">
              {LANDING_STATS.map((item) => (
                <Card key={item.label} className="border-border/80 bg-card/80 text-left shadow-sm">
                  <CardContent className="p-4">
                    <p className="text-xs text-muted-foreground">{item.label}</p>
                    <p className="mt-1 text-2xl font-bold tracking-tight">{item.value}</p>
                    <p className="text-xs text-muted-foreground">{item.hint}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        </section>

        <section id="how-it-works" className="py-8">
          <div className="mx-auto mb-8 max-w-2xl text-center">
            <h2 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
              3 步完成视频成片
            </h2>
            <p className="mt-3 text-sm text-muted-foreground sm:text-base">
              从上传到导出，全流程结构清晰，适合内容创作者快速复用。
            </p>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {FLOW_STEPS.map((step, index) => (
              <Card key={step.title} className="border-muted bg-card shadow-sm">
                <CardHeader>
                  <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                    {step.icon}
                  </div>
                  <CardTitle className="text-lg">
                    {index + 1}. {step.title}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-base leading-relaxed">
                    {step.description}
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

        <section className="pb-16">
          <Card className="border-border bg-gradient-to-r from-indigo-50/70 via-violet-50/50 to-white shadow-sm">
            <CardContent className="flex flex-col items-center gap-4 px-6 py-8 text-center sm:px-10">
              <h3 className="text-xl font-bold text-foreground sm:text-2xl">
                开始你的下一条高质量口播视频
              </h3>
              <p className="max-w-2xl text-sm text-muted-foreground sm:text-base">
                上传视频后，AI 会自动完成字幕识别、内容精简与章节整理，你只需要做最后确认。
              </p>
              <div className="flex flex-wrap items-center justify-center gap-3">
                <Button
                  onClick={() => {
                    const input = document.querySelector<HTMLInputElement>("input[type='file']");
                    input?.click();
                  }}
                  className="rounded-full"
                  disabled={loading}
                >
                  立即上传视频
                  <ArrowRight className="ml-1 h-4 w-4" />
                </Button>
                {!isSignedIn && (
                  <Link href="/sign-up">
                    <Button variant="outline" className="rounded-full">
                      先注册账号
                    </Button>
                  </Link>
                )}
              </div>
            </CardContent>
          </Card>
        </section>
      </main>

      <footer className="border-t border-border bg-muted/30 py-8 text-center text-xs text-muted-foreground">
        <p>&copy; {new Date().getFullYear()} AI Cut. All rights reserved.</p>
      </footer>
    </div>
  );
}
