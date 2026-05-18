"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  Zap,
  UploadCloud,
  CheckCircle2,
  ArrowRight,
  Play,
  FileText,
  Handshake,
  MessageCircle,
} from "lucide-react";
import Logo from "@/components/logo";
import {
  UploadIllustration,
  AICutIllustration,
  ExportIllustration,
} from "@/components/step-illustrations";

import {
  type ClientUploadIssueStage,
  getMe,
  invalidateTokenCache,
  reportClientUploadIssue,
  setApiAuthTokenProvider,
} from "../lib/api";
import {
  isUnsupportedLocalVideoBrowser,
  isUnsupportedMobileUploadDevice,
} from "../lib/device";
import {
  getLikelyAppExportFileMessage,
  isLikelyAppExportFileName,
} from "../lib/source-video-guard";
import { getFriendlyUploadErrorMessage } from "../lib/upload-error";
import {
  getUploadIssueErrorMessage,
  getUploadIssueErrorName,
} from "../lib/upload-error";
import {
  getFileExtension,
  getFileSizeMbBucket,
  trackEvent,
} from "../lib/analytics";
import {
  getVideoDurationLimitMessage,
  MAX_VIDEO_DURATION_SEC,
  readVideoDurationSec,
  runUploadPipeline,
  UploadPipelineError,
} from "../lib/upload-pipeline";
import { authClient } from "../lib/auth-client";
import { ACTIVE_JOB_ID_KEY } from "../lib/session";
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
import HeroAnimation from "@/components/hero-animation";
import FounderCard from "@/components/founder-card";

const WECHAT_ID = "PoetCoderJun";

const FAQ_ITEMS = [
  {
    question: "支持哪些视频格式？",
    answer:
      "当前支持主流视频格式：MP4、MOV、MKV、WebM、M4V、TS、M2TS、MTS。单次上传最长支持 10 分钟。",
  },
  {
    question: "对浏览器有什么要求？",
    answer:
      "请使用桌面版 Chrome。由于导出渲染依赖浏览器本地 FFmpeg，目前暂不支持 Edge、Safari、Firefox 及移动端浏览器。",
  },
  {
    question: "视频数据安全吗？会上传到哪里？",
    answer:
      "视频上传至阿里云 OSS 用于云端 AI 语音转写与分析，分析完成后不会长期保留。最终视频导出渲染完全在您的本地浏览器中完成，成片不会上传至任何服务器。",
  },
  {
    question: "现在怎么使用？",
    answer:
      "当前是限时免费阶段。登录账号后即可上传、处理并导出，暂时不展示额度，也不会扣除额度。",
  },
];

const FLOW_STEPS = [
  {
    title: "上传原始口播",
    description: "直接上传真实录制的视频，说错、停顿、重复都不用先手动处理。",
    illustration: UploadIllustration,
  },
  {
    title: "确认精剪草稿",
    description: "AI 先帮你删废话、理字幕、分章节，你只需要做最后确认。",
    illustration: AICutIllustration,
  },
  {
    title: "导出包装成片",
    description: "字幕、章节、进度条和关键词高亮自动生成，直接导出可发布视频。",
    illustration: ExportIllustration,
  },
];

function PublicFeedbackSection() {
  return (
    <section id="contact" className="border-t border-border/60 py-14">
      <div className="mx-auto grid max-w-5xl gap-8 lg:grid-cols-[1fr_320px] lg:items-center">
        <div>
          <Badge className="rounded-full bg-emerald-600 text-white hover:bg-emerald-600">
            公测开放中
          </Badge>
          <h2 className="mt-4 text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
            产品反馈、口播需求和相关合作，可以直接联系
          </h2>
          <div className="mt-4 space-y-3 text-sm leading-7 text-muted-foreground sm:text-base">
            <p>
              PoetCut 已经从内测进入公测开放阶段。现在登录账号即可直接体验完整的上传、AI 精剪、字幕编辑和浏览器导出流程。
            </p>
            <p>
              这个产品最早来自真实口播剪辑里的痛点，也需要继续根据创作者的素材、节奏和发布场景一起迭代。如果你觉得哪里不顺手，或者有更具体的口播剪辑需求，欢迎直接发给我。
            </p>
          </div>
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <div className="flex items-start gap-3 rounded-lg border bg-card p-4">
              <MessageCircle className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <div>
                <p className="text-sm font-semibold text-foreground">产品反馈</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  上传、剪辑、字幕、导出、风格包装，任何卡住或不顺手的地方都可以说。
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3 rounded-lg border bg-card p-4">
              <Handshake className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <div>
                <p className="text-sm font-semibold text-foreground">相关合作</p>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">
                  创作者共创、工作机会、产品合作、口播内容自动化场景都可以交流。
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-lg border bg-card p-5 shadow-sm">
          <div className="mx-auto w-fit rounded-lg border border-border bg-background p-3 shadow-sm">
            <Image
              src="/wechat.jpg"
              alt="PoetCut 公测反馈与合作微信二维码"
              width={224}
              height={224}
              className="h-56 w-56 rounded-md object-contain"
            />
          </div>
          <div className="mt-4 rounded-lg border border-dashed border-border bg-muted/30 px-4 py-3 text-sm">
            <p className="text-muted-foreground">微信号</p>
            <p className="mt-1 font-semibold tracking-wide text-foreground">{WECHAT_ID}</p>
            <p className="mt-1 text-xs text-muted-foreground">添加时请备注：PoetCut 反馈 / 合作</p>
          </div>
        </div>
      </div>
    </section>
  );
}

function useInView(threshold = 0.2) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [inView, setInView] = useState(false);
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          observer.disconnect();
        }
      },
      { threshold }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [threshold]);
  return { ref, inView: !mounted || inView };
}

function StepCard({ step, index }: { step: typeof FLOW_STEPS[0]; index: number }) {
  const { ref, inView } = useInView(0.15);
  const Illustration = step.illustration;
  return (
    <div
      ref={ref}
      className={cn(
        "transition-all duration-700 ease-out",
        inView
          ? "opacity-100 translate-y-0"
          : "opacity-0 translate-y-6"
      )}
      style={{ transitionDelay: `${index * 150}ms` }}
    >
      <Card className="border-muted bg-card shadow-sm overflow-hidden h-full">
        <div className="pt-6 px-6">
          <Illustration className="h-28 text-foreground" />
        </div>
        <CardHeader className="pt-4">
          <CardTitle className="text-lg">
            <span className="text-muted-foreground mr-2">{index + 1}.</span>
            {step.title}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <CardDescription className="text-base leading-relaxed">
            {step.description}
          </CardDescription>
        </CardContent>
      </Card>
    </div>
  );
}

export default function HomePageClient() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [authBusy, setAuthBusy] = useState(false);
  const [error, setError] = useState("");
  const [accountNotice, setAccountNotice] = useState("");
  const [isSignedIn, setIsSignedIn] = useState(false);
  const [authAccount, setAuthAccount] = useState("");
  const [mobileUploadBlocked, setMobileUploadBlocked] = useState(false);
  const [uploadStageMessage, setUploadStageMessage] = useState("");
  const [scrolled, setScrolled] = useState(false);
  const [script, setScript] = useState("");
  const [scriptExpanded, setScriptExpanded] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 10);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

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

  useEffect(() => {
    setMobileUploadBlocked(
      isUnsupportedMobileUploadDevice() || isUnsupportedLocalVideoBrowser()
    );
  }, []);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 10);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const showMobileUploadError = useCallback(() => {
    trackEvent("upload_blocked", { reason: "unsupported_browser" });
    setError("当前浏览器暂不支持上传视频，请使用桌面版 Chrome。");
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
      setJobId(null);
      setAccountNotice("");
      try {
        localStorage.removeItem(ACTIVE_JOB_ID_KEY);
      } catch {
        // Ignore storage failures.
      }
    } finally {
      setAuthBusy(false);
    }
  };

  const showLoginRequiredError = useCallback((source = "upload_entry") => {
    trackEvent("upload_login_required", { source });
    setError("当前限时免费需要先登录账号。登录后即可上传和导出，暂时不消耗额度。");
  }, []);

  // Auth and profile checks happen here, only when user actually tries to upload.
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (!file) return;

    trackEvent("upload_file_selected", {
      file_extension: getFileExtension(file.name),
      file_type: file.type || "unknown",
      file_size_mb_bucket: getFileSizeMbBucket(file.size),
    });

    if (mobileUploadBlocked) {
      showMobileUploadError();
      return;
    }
    if (isLikelyAppExportFileName(file.name)) {
      trackEvent("upload_rejected", { reason: "app_export_file_name" });
      setError(getLikelyAppExportFileMessage(file.name));
      return;
    }

    setError("");
    setLoading(true);
    let uploadStage: ClientUploadIssueStage = "session_check";
    try {
      // 0. Check video duration — reject anything >= 10 minutes.
      const durationSec = await readVideoDurationSec(file);
      if (durationSec >= MAX_VIDEO_DURATION_SEC) {
        trackEvent("upload_rejected", {
          reason: "duration_too_long",
          duration_sec: Math.round(durationSec),
        });
        setError(getVideoDurationLimitMessage(durationSec));
        return;
      }

      // 1. Verify session lazily at consumption time. The limited-time free
      // period still requires a signed-in account.
      uploadStage = "session_check";
      const sessionResult = await (authClient as any).getSession();
      const user = sessionResult?.data?.user;
      if (!user?.id) {
        setIsSignedIn(false);
        setAuthAccount("");
        showLoginRequiredError("file_select");
        return;
      }
      setIsSignedIn(true);
      setAuthAccount(String(user.email || user.name || user.id || "").trim());

      // 2. Reconcile the business user row before starting job I/O.
      uploadStage = "profile_check";
      try {
        await getMe();
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "账号状态校验失败，请稍后重试。";
        setError(message);
        return;
      }
      setAccountNotice("限时免费已开启：本次处理和导出暂不消耗额度。");

      const result = await runUploadPipeline({
        file,
        script,
        onStageMessage: setUploadStageMessage,
      });
      trackEvent("upload_accepted", {
        has_reference_script: script.trim().length > 0,
      });
      saveJobId(result.job.job_id);
    } catch (err) {
      if (err instanceof UploadPipelineError) {
        uploadStage = err.stage;
      }
      const friendlyMessage = getFriendlyUploadErrorMessage(err);
      trackEvent("upload_error", {
        stage: uploadStage,
        error_name: getUploadIssueErrorName(err),
      });
        void reportClientUploadIssue({
          stage: uploadStage,
          page: "/",
          file_name: file.name,
          file_type: file.type,
          file_size_bytes: file.size,
          error_name: getUploadIssueErrorName(err),
          error_message: getUploadIssueErrorMessage(err),
          friendly_message: friendlyMessage,
          user_agent:
            typeof navigator !== "undefined" ? navigator.userAgent : "",
      }).catch(() => undefined);
      setError(friendlyMessage);
    } finally {
      setUploadStageMessage("");
      setLoading(false);
    }
  };

  const handleUploadAreaClick = useCallback(() => {
    if (mobileUploadBlocked) {
      showMobileUploadError();
      return;
    }
    if (!isSignedIn) {
      showLoginRequiredError();
    }
  }, [isSignedIn, mobileUploadBlocked, showLoginRequiredError, showMobileUploadError]);

  if (jobId) {
    return (
      <div className="min-h-screen bg-background font-sans">
        <header className={cn("sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 transition-shadow duration-300", scrolled && "shadow-sm")}>
          <div className="container mx-auto flex h-14 items-center justify-between px-4 sm:px-6">
            <Link
              href="/"
              className="flex items-center gap-2 transition-opacity hover:opacity-80"
              onClick={(e) => {
                e.preventDefault();
                handleBackHome();
              }}
            >
              <Logo iconSize={32} showText={true} />
            </Link>
            <div className="flex items-center gap-3">
              {isSignedIn && (
                <>
                  <Badge variant="secondary" className="px-3 py-1">
                    限时免费
                  </Badge>
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
          onSwitchJob={saveJobId}
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background font-sans">
      <header className={cn("sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 transition-shadow duration-300", scrolled && "shadow-sm")}>
        <div className="container mx-auto flex h-14 items-center justify-between px-4 sm:px-6">
          <Link
            href="/"
            className="flex items-center gap-2 transition-opacity hover:opacity-80"
          >
            <Logo iconSize={32} showText={true} />
          </Link>
          <nav className="hidden items-center gap-6 text-sm text-muted-foreground md:flex">
            <a href="#how-it-works" className="transition-colors hover:text-foreground">
              如何使用
            </a>
            <Link href="/use-cases/koubo-video-editing" className="transition-colors hover:text-foreground">
              适合谁用
            </Link>
            <Link href="/ai-koubo-jianji" className="transition-colors hover:text-foreground">
              产品思考
            </Link>
            <a href="#contact" className="transition-colors hover:text-foreground">
              反馈合作
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
                  <Button className="rounded-full">注册/登录</Button>
                </Link>
              </>
            ) : (
              <>
                <Badge variant="secondary" className="px-3 py-1">
                  限时免费
                </Badge>
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
        {/* Hero Section — full viewport minus header */}
        <section className="relative flex flex-col justify-center min-h-[calc(100dvh-3.5rem)] py-6 lg:py-8">
          {/* Background gradient blob */}
          <div className="absolute inset-x-0 -top-20 -z-10 transform-gpu overflow-hidden blur-3xl sm:-top-40">
            <div
              className="relative left-[calc(50%-11rem)] aspect-[1155/678] w-[36.125rem] -translate-x-1/2 rotate-[30deg] bg-gradient-to-tr from-[#ff80b5] to-[#9089fc] opacity-20 sm:left-[calc(50%-30rem)] sm:w-[72.1875rem]"
              style={{
                clipPath:
                  "polygon(74.1% 44.1%, 100% 61.6%, 97.5% 26.9%, 85.5% 0.1%, 80.7% 2%, 72.5% 32.5%, 60.2% 62.4%, 52.4% 68.1%, 47.5% 58.3%, 45.2% 34.5%, 27.5% 76.7%, 0.1% 64.9%, 17.9% 100%, 27.6% 76.8%, 76.1% 97.7%, 74.1% 44.1%)",
              }}
            />
          </div>

          <div className="flex flex-col lg:flex-row lg:items-center lg:gap-10 xl:gap-14">
            {/* ── Left column: headline + upload card ── */}
            <div className="flex-1 lg:max-w-[56%] min-w-0">
              <div className="mb-5 inline-flex flex-wrap items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700">
                <Badge className="rounded-full bg-emerald-600 text-white hover:bg-emerald-600">
                  限时免费
                </Badge>
                <span>公测期间登录账号即可免费使用</span>
              </div>
              {/* Headline */}
              <h1 className="tracking-tight text-foreground">
                <span className="block text-xl font-semibold leading-tight text-muted-foreground sm:text-2xl lg:text-[2rem]">
                  口播视频一遍遍录制？
                </span>
                <span className="mt-2 block text-xl font-semibold leading-tight text-muted-foreground sm:text-2xl lg:text-[2rem]">
                  几分钟视频剪辑要花几个小时？
                </span>
                <span className="mt-7 flex flex-col gap-2 text-[1.9rem] font-extrabold leading-[1.08] text-foreground sm:text-5xl lg:text-[3.35rem]">
                  <span className="flex flex-wrap items-baseline gap-x-8 gap-y-1">
                    <span className="whitespace-nowrap">一次录制</span>
                    <span className="whitespace-nowrap">一镜到底</span>
                  </span>
                  <span className="flex flex-wrap items-baseline gap-x-8 gap-y-1">
                    <span className="whitespace-nowrap">AI 一键剪辑</span>
                    <span className="whitespace-nowrap text-indigo-600">
                      包装出片
                    </span>
                  </span>
                </span>
              </h1>

              {/* Highlights */}
              <div className="mt-8 space-y-3 max-w-md lg:max-w-none">
                <div className="flex items-start gap-3">
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 mt-0.5">
                    <CheckCircle2 className="h-3.5 w-3.5 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-foreground">讲错了也不用重来</p>
                    <p className="text-xs text-muted-foreground mt-0.5">停顿、改口、重复说明，都可以在精剪草稿里处理</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 mt-0.5">
                    <Zap className="h-3.5 w-3.5 text-primary" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-foreground">剪辑和包装一次完成</p>
                    <p className="text-xs text-muted-foreground mt-0.5">字幕、章节、进度条、高亮自动生成，少做很多重复活</p>
                  </div>
                </div>
              </div>

              {/* Upload + Script Card */}
              <div
                className="mt-10"
                onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
                onDrop={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  if (mobileUploadBlocked || loading) return;
                  if (!isSignedIn) {
                    showLoginRequiredError();
                    return;
                  }
                  const file = e.dataTransfer.files?.[0];
                  if (!file) return;
                  const input = document.querySelector<HTMLInputElement>("input[type='file']");
                  if (!input) return;
                  const dt = new DataTransfer();
                  dt.items.add(file);
                  input.files = dt.files;
                  input.dispatchEvent(new Event("change", { bubbles: true }));
                }}
              >
                <Card className="border-border/80 shadow-sm overflow-hidden">
                  {/* Upload area */}
                  <div
                    onClick={handleUploadAreaClick}
                    className={cn(
                      "relative group px-6 py-6 transition-all duration-300 hover:bg-muted/30",
                      mobileUploadBlocked || loading || !isSignedIn
                        ? "cursor-not-allowed opacity-70"
                        : "cursor-pointer"
                    )}
                  >
                    <input
                      type="file"
                      accept=".mp4,.mov,.mkv,.webm,.m4v,.ts,.m2ts,.mts"
                      onChange={handleFileSelect}
                      disabled={loading || mobileUploadBlocked || !isSignedIn}
                      className="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
                    />
                    <div className="flex items-center gap-5">
                      <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary transition-all duration-300 group-hover:bg-primary/15 group-hover:scale-105">
                        {loading ? (
                          <div className="h-6 w-6 animate-spin rounded-full border-2 border-current border-t-transparent" />
                        ) : (
                          <UploadCloud className="h-7 w-7" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-base font-medium text-foreground">
                          {loading
                            ? uploadStageMessage || "正在上传并分析..."
                            : mobileUploadBlocked
                            ? "当前浏览器暂不支持上传"
                            : !isSignedIn
                            ? "登录后即可限时免费上传"
                            : "拖拽文件到此处，或点击上传视频"}
                        </p>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {mobileUploadBlocked
                            ? "请使用桌面版 Chrome"
                            : !isSignedIn
                            ? "限时免费期间不消耗额度，请先登录账号"
                            : "支持 MP4, MOV, MKV 等 · 最长 10 分钟"}
                        </p>
                      </div>
                      {!loading && !mobileUploadBlocked && isSignedIn && (
                        <span className="text-xs font-medium text-primary shrink-0 px-3 py-1.5 rounded-full bg-primary/5 ring-1 ring-primary/20 group-hover:bg-primary/10 transition-colors">
                          选择文件
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Divider */}
                  <div className="h-px bg-border/60" />

                  {/* Script input area */}
                  <div className="px-5 py-3 bg-muted/20">
                    <button
                      type="button"
                      onClick={() => {
                        setScriptExpanded((v) => {
                          const next = !v;
                          trackEvent("reference_script_toggled", { expanded: next });
                          return next;
                        });
                      }}
                      className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <FileText className="h-3.5 w-3.5" />
                      <span>已有口播脚本？（可选）粘贴进来让 AI 更精准剪辑</span>
                      <span className={cn("ml-auto transition-transform duration-200", scriptExpanded && "rotate-180")}>▼</span>
                    </button>
                    {scriptExpanded && (
                      <div className="mt-2">
                        <textarea
                          value={script}
                          onChange={(e) => setScript(e.target.value)}
                          placeholder="在此粘贴你的口播脚本，AI 会以此为参考进行剪辑和润色..."
                          className="w-full min-h-[80px] max-h-[160px] resize-y rounded-lg border border-border/80 bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-primary/30 focus:border-primary/40"
                        />
                      </div>
                    )}
                  </div>
                </Card>

                {/* Status messages */}
                <div className="mt-3 space-y-2">
                  {accountNotice && (
                    <div className="flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 border border-emerald-200">
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      {accountNotice}
                    </div>
                  )}
                  {mobileUploadBlocked && (
                    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800">
                      当前浏览器暂不支持上传视频，请使用桌面版 Chrome。
                    </div>
                  )}
                  {error && (
                    <div className="rounded-md bg-destructive/10 px-3 py-2 text-xs font-medium text-destructive border border-destructive/20">
                      <p>{error}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Mobile: CTA buttons moved below card */}
              <div className="mt-6 flex flex-wrap items-center gap-3 lg:hidden justify-center">
                <Button
                  onClick={() => {
                    if (mobileUploadBlocked) {
                      showMobileUploadError();
                      return;
                    }
                    if (!isSignedIn) {
                      window.location.href = "/sign-in";
                      return;
                    }
                    const input = document.querySelector<HTMLInputElement>("input[type='file']");
                    input?.click();
                  }}
                  className="rounded-full h-10 px-5 text-sm"
                  disabled={loading}
                >
                  <UploadCloud className="mr-2 h-4 w-4" />
                  {isSignedIn ? "立即上传" : "登录后上传"}
                </Button>
                <Button
                  variant="outline"
                  className="rounded-full h-10 px-5 text-sm"
                  onClick={() => {
                    const el = document.getElementById("how-it-works");
                    el?.scrollIntoView({ behavior: "smooth" });
                  }}
                >
                  <Play className="mr-2 h-4 w-4" />
                  观看演示
                </Button>
              </div>
            </div>

            {/* ── Right column: animation ── */}
            <div className="hidden lg:flex flex-1 justify-center items-center max-w-[48%] min-h-[420px]">
              <HeroAnimation />
            </div>
          </div>
        </section>

        <section id="how-it-works" className="bg-slate-50 dark:bg-slate-900/30 py-16 lg:py-20 -mx-4 sm:-mx-6 px-4 sm:px-6">
          <div className="mx-auto max-w-2xl mb-10 text-center">
            <h2 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
              三步完成口播成片
            </h2>
            <p className="mt-3 text-sm text-muted-foreground sm:text-base">
              从上传、确认到导出，尽量把最耗时的剪辑和包装动作都收进一个流程。
            </p>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {FLOW_STEPS.map((step, index) => (
              <StepCard key={step.title} step={step} index={index} />
            ))}
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="mx-auto max-w-3xl py-16 lg:py-20 border-t border-border/60">
          <div className="mb-12 text-center">
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

        <PublicFeedbackSection />

        <section className="border-t border-border/60 py-12">
          <div className="mx-auto max-w-md">
            <FounderCard />
          </div>
        </section>

        <section className="pb-16 pt-8">
          <Card className="border-border bg-gradient-to-br from-indigo-50 via-violet-50/70 to-background dark:from-indigo-950/30 dark:via-violet-950/20 dark:to-background shadow-sm">
            <CardContent className="flex flex-col items-center gap-4 px-6 py-8 text-center sm:px-10">
              <h3 className="text-xl font-bold text-foreground sm:text-2xl">
                开始你的下一条高质量口播视频
              </h3>
              <p className="max-w-2xl text-sm text-muted-foreground sm:text-base">
                上传原始口播，先得到一版精剪和包装都完成的草稿，再做最后确认。
              </p>
              <div className="flex flex-wrap items-center justify-center gap-3">
                <Button
                  onClick={() => {
                    if (mobileUploadBlocked) {
                      showMobileUploadError();
                      return;
                    }
                    if (!isSignedIn) {
                      window.location.href = "/sign-in";
                      return;
                    }
                    const input = document.querySelector<HTMLInputElement>("input[type='file']");
                    input?.click();
                  }}
                  className="rounded-full"
                  disabled={loading}
                >
                  {isSignedIn ? "立即上传视频" : "登录后免费使用"}
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
        <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
          <Link href="/features/remove-filler-words" className="hover:text-foreground">
            自动删废话
          </Link>
          <Link href="/ai-koubo-jianji" className="hover:text-foreground">
            产品思考
          </Link>
          <Link href="/features/subtitle-driven-editing" className="hover:text-foreground">
            字幕剪辑
          </Link>
          <Link href="/use-cases/koubo-video-editing" className="hover:text-foreground">
            口播场景
          </Link>
          <Link href="/faq" className="hover:text-foreground">
            常见问题
          </Link>
          <a href="#contact" className="hover:text-foreground">
            反馈合作
          </a>
        </div>
        <p className="mt-4">&copy; {new Date().getFullYear()} PoetCut. All rights reserved.</p>
      </footer>
    </div>
  );
}
