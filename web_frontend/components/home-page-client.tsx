"use client";

import {useCallback, useEffect, useState} from "react";
import Link from "next/link";
import {activateInviteCode, createJob, getMe, setApiAuthTokenProvider} from "../lib/api";
import {authClient} from "../lib/auth-client";
import {ACTIVE_JOB_ID_KEY, PENDING_INVITE_CODE_KEY} from "../lib/session";
import JobWorkspace from "./job-workspace";
import { Zap, ChevronRight, Video, CheckCircle2 } from "lucide-react";
import Image from "next/image";

const FAQ_ITEMS = [
  {
    question: "支持哪些视频格式？",
    answer: "当前支持主流视频格式：MP4、MOV、MKV、WebM、M4V、TS、M2TS、MTS。",
  },
  {
    question: "一次处理大概需要多久？",
    answer: "取决于视频时长和您的电脑性能，AI 分析仅需几分钟，导出过程由于在本地渲染，速度非常快。",
  },
  {
    question: "是否需要专业剪辑经验？",
    answer: "完全不需要。整个流程按步骤引导，您的重点只是确认文字字幕和章节结构。",
  },
];

export default function HomePageClient() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [authBusy, setAuthBusy] = useState(false);
  const [authReady, setAuthReady] = useState(false);
  const [error, setError] = useState("");
  const [creditBalance, setCreditBalance] = useState<number>(0);
  const [userStatus, setUserStatus] = useState("PENDING_INVITE");
  const [inviteNotice, setInviteNotice] = useState("");
  const [isSignedIn, setIsSignedIn] = useState(false);
  const [authAccount, setAuthAccount] = useState("");
  const [apiToken, setApiToken] = useState<string | null>(null);
  const [inviteCodeInput, setInviteCodeInput] = useState("");

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
        setCreditBalance(0);
        setUserStatus("PENDING_INVITE");
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
      setCreditBalance(0);
      setUserStatus("PENDING_INVITE");
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
    setCreditBalance(0);
    setUserStatus("PENDING_INVITE");
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
        setUserStatus(String(me.status || "PENDING_INVITE").toUpperCase());
      } catch (err) {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : "登录状态已失效，请重新登录。";
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
    if (userStatus !== "PENDING_INVITE") return;
    let cancelled = false;

    const activatePendingInvite = async () => {
      let code = "";
      try {
        code = localStorage.getItem(PENDING_INVITE_CODE_KEY)?.trim().toUpperCase() || "";
      } catch {
        code = "";
      }
      if (!code) return;

      setInviteCodeInput(code);
      try {
        const activation = await activateInviteCode(code);
        if (cancelled) return;
        setCreditBalance(activation.balance);
        setUserStatus("ACTIVE");
        setInviteNotice("注册成功，邀请码已激活。");
        setInviteCodeInput("");
        try {
          localStorage.removeItem(PENDING_INVITE_CODE_KEY);
        } catch {
          // Ignore storage failures.
        }
      } catch {
        if (cancelled) return;
        setInviteNotice("检测到注册邀请码，请点击“激活”完成激活。");
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

  const handleActivateInvite = async () => {
    const inviteCode = inviteCodeInput.trim().toUpperCase();
    if (!inviteCode) {
      setError("请输入邀请码。");
      return;
    }
    setError("");
    setInviteNotice("");
    setAuthBusy(true);
    try {
      const activation = await activateInviteCode(inviteCode);
      setCreditBalance(activation.balance);
      setUserStatus("ACTIVE");
      if (activation.already_activated) {
        setInviteNotice("邀请码已处理过，本次未重复发放免费额度。");
      } else if (activation.granted_credits > 0) {
        setInviteNotice(`邀请码兑换成功，已发放 ${activation.granted_credits} 次免费额度。`);
      } else {
        setInviteNotice("邀请码已激活。");
      }
      setInviteCodeInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "邀请码兑换失败，请重试。");
    } finally {
      setAuthBusy(false);
    }
  };

  const handleLogout = async () => {
    setAuthBusy(true);
    try {
      await (authClient as any).signOut();
      setApiToken(null);
      setIsSignedIn(false);
      setAuthAccount("");
      setCreditBalance(0);
      setUserStatus("PENDING_INVITE");
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

  const handleCreate = async () => {
    if (!isSignedIn) {
      setError("请先登录后再开始创作。");
      return;
    }
    if (!inviteActivated) {
      setError("请先输入邀请码激活账号后再开始创作。");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const job = await createJob();
      saveJobId(job.job_id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "创建视频项目失败，请稍后重试。";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  if (jobId) {
    return (
      <div className="app-container">
        <header className="top-nav">
          <Link href="/" className="nav-brand" onClick={(e) => { e.preventDefault(); handleBackHome(); }}>
            <Video className="w-5 h-5" />
            AI Cut
          </Link>
          <div className="nav-actions">
            {isSignedIn && (
              <>
                <span className="status-badge" style={{ background: '#f3f4f6', color: '#111827' }}>
                  额度: {creditBalance} 次
                </span>
                <span className="muted" style={{ fontSize: '0.875rem' }}>{authAccount}</span>
              </>
            )}
          </div>
        </header>
        <JobWorkspace key={jobId} jobId={jobId} onBackHome={handleBackHome} />
      </div>
    );
  }

  return (
    <div className="app-container fade-in">
      <header className="top-nav">
        <Link href="/" className="nav-brand">
          <Video className="w-5 h-5" />
          AI Cut
        </Link>
        <div className="nav-actions">
          {!authReady ? null : !isSignedIn ? (
            <>
              <Link href="/sign-in" className="btn btn-ghost">登录</Link>
              <Link href="/sign-up" className="btn btn-primary">注册</Link>
            </>
          ) : (
            <>
              <span className="status-badge" style={{ background: '#f3f4f6', color: '#111827' }}>
                额度: {creditBalance} 次
              </span>
              <span className="muted" style={{ fontSize: '0.875rem', display: 'none' }}>{authAccount}</span>
              <button className="btn-ghost" onClick={handleLogout} disabled={authBusy}>
                退出
              </button>
            </>
          )}
        </div>
      </header>

      <main className="max-w-screen-md mx-auto">
        {/* Hero Section */}
        <section className="text-center mb-20 mt-16 relative">
          <div style={{ position: 'absolute', top: -120, left: '50%', transform: 'translateX(-50%)', width: 800, height: 400, background: 'radial-gradient(ellipse at center, rgba(139, 92, 246, 0.15) 0%, rgba(56, 189, 248, 0.15) 40%, transparent 70%)', filter: 'blur(50px)', zIndex: -1, pointerEvents: 'none' }} />
          <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 16px', background: 'rgba(255, 255, 255, 0.6)', border: '1px solid rgba(228, 228, 231, 0.8)', backdropFilter: 'blur(12px)', borderRadius: 999, fontSize: 13, fontWeight: 600, marginBottom: 28, color: '#3f3f46', boxShadow: '0 2px 10px rgba(0,0,0,0.02)' }}>
            <Zap className="w-4 h-4" style={{ color: '#8b5cf6' }} /> 让口播视频更快进入可发布状态
          </div>
          <h1 style={{ letterSpacing: '-0.04em', fontSize: '3.75rem', fontWeight: 800, marginBottom: 24, lineHeight: 1.15 }}>
            <span style={{ background: 'linear-gradient(135deg, #09090b 0%, #4338ca 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', display: 'inline-block', paddingRight: '0.1em' }}>极简 AI 视频剪辑</span>
          </h1>
          <p className="max-w-screen-md mx-auto" style={{ fontSize: '1.25rem', marginBottom: 40, lineHeight: 1.6, color: '#52525b', fontWeight: 400 }}>
            自动剔除废话、精简字幕并生成章节，<br/>为创作者节省 80% 的初期剪辑时间。
          </p>
          <div className="flex justify-center items-center gap-4 flex-wrap">
            <button
              className="btn-primary btn-large"
              style={{ fontSize: '1.125rem', padding: '0 36px', height: 56, borderRadius: 28 }}
              onClick={handleCreate}
              disabled={loading || !authReady}
            >
              {loading ? (
                <><span className="spinner" style={{ width: 18, height: 18, marginRight: 8, borderWidth: 2, borderTopColor: '#fff', borderColor: 'rgba(255,255,255,0.3)' }} /> 准备环境...</>
              ) : !authReady ? (
                "准备中..."
              ) : (
                <>开始免费创作 <ChevronRight className="w-5 h-5 ml-1" /></>
              )}
            </button>
          </div>

          {/* Activation Notice inside Hero if needed */}
          {isSignedIn && !inviteActivated ? (
            <div className="flex justify-center mt-6">
              <div style={{ background: '#fffbeb', border: '1px solid #fde68a', padding: '12px 16px', borderRadius: 12, display: 'inline-flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: 14, color: '#92400e', fontWeight: 500 }}>账号未激活，请输入邀请码获取额度</span>
                <input
                  type="text"
                  value={inviteCodeInput}
                  placeholder="输入邀请码..."
                  onChange={(e) => setInviteCodeInput(e.target.value.toUpperCase())}
                  disabled={authBusy}
                  style={{ width: 140, height: 32, fontSize: 14 }}
                />
                <button className="btn" style={{ height: 32, fontSize: 13 }} onClick={handleActivateInvite} disabled={authBusy}>
                  激活
                </button>
              </div>
            </div>
          ) : null}

          {inviteNotice ? (
            <p className="mt-4" style={{ color: '#059669', fontSize: 14, fontWeight: 500 }}>
              <CheckCircle2 className="w-4 h-4 inline mr-1" style={{ verticalAlign: 'text-bottom' }} /> {inviteNotice}
            </p>
          ) : null}

          {error ? <div className="error max-w-screen-md mx-auto mt-6 justify-center">{error}</div> : null}
        </section>

        {/* How it works */}
        <section id="how-it-works" className="mb-24 mt-20">
          <div className="text-center mb-16">
            <h2 style={{ fontSize: '2.5rem', fontWeight: 800, marginBottom: 16, letterSpacing: '-0.02em', background: 'linear-gradient(135deg, #09090b 0%, #4338ca 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', display: 'inline-block' }}>一键剪口播视频</h2>
            <p style={{ fontSize: '1.25rem', color: '#52525b', maxWidth: 600, margin: '0 auto' }}>全自动分析，每一步支持人为微调，完美把控细节</p>
          </div>
          <div style={{ position: 'relative', overflow: 'hidden' }}>
            <div className="flex" style={{ flexDirection: 'row', gap: 32, position: 'relative', zIndex: 1, alignItems: 'stretch' }}>
              {[
                { step: 1, title: '提取字幕与生成建议', desc: 'AI 自动分析语音生成精确字幕，并高亮标记废话、停顿。' },
                { step: 2, title: '微调字幕与精简确认', desc: '浏览 AI 建议的删除项，像编辑文档一样快速调整、确认保留内容。' },
                { step: 3, title: '章节划分与极速导出', desc: '基于精简后的内容，AI 自动划分章节，微调后一键导出成片。' },
              ].map((s, idx) => (
                <div key={s.step} style={{ flex: 1, position: 'relative', display: 'flex', flexDirection: 'column' }}>
                  {idx < 2 && (
                    <div style={{ position: 'absolute', top: 24, left: '50%', right: '-50%', height: 1, background: '#e4e4e7', zIndex: 0 }} />
                  )}
                  <div style={{ width: 48, height: 48, borderRadius: '50%', background: '#18181b', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.25rem', fontWeight: 600, flexShrink: 0, position: 'relative', zIndex: 10, marginBottom: 24, margin: '0 auto 24px' }}>
                    {s.step}
                  </div>
                  <div style={{ textAlign: 'center', flex: 1 }}>
                    <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: 12, color: '#09090b', letterSpacing: '-0.01em', lineHeight: 1.4 }}>{s.title}</h3>
                    <p style={{ margin: 0, fontSize: '1rem', color: '#52525b', lineHeight: 1.6 }}>{s.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="mb-12">
          <div className="text-center mb-8">
            <h2>常见问题</h2>
          </div>
          <div className="faq-list">
            {FAQ_ITEMS.map((item) => (
              <details key={item.question} className="faq-item">
                <summary>{item.question}</summary>
                <p>{item.answer}</p>
              </details>
            ))}
          </div>
        </section>
        
        {/* About Me */}
        <section className="mt-20 pt-16 pb-16" style={{ borderTop: '1px solid #e4e4e7', background: '#fafafa' }}>
          <div className="max-w-screen-md mx-auto px-6 flex justify-center">
            <div style={{ width: '100%', maxWidth: 400, background: '#fff', padding: '32px 32px 36px', borderRadius: 24, boxShadow: '0 4px 20px rgba(0,0,0,0.03)', border: '1px solid #e4e4e7', position: 'relative' }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
                <a href="https://xhslink.com/m/2CUIT8iyntn" target="_blank" rel="noopener noreferrer" style={{ width: 80, height: 80, borderRadius: '50%', overflow: 'hidden', border: '1px solid #e4e4e7', display: 'block', marginBottom: 16 }}>
                  <Image src="/photo.jpg" alt="Jun" width={80} height={80} style={{ objectFit: 'cover' }} />
                </a>
                <h3 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 12px', color: '#09090b' }}>诗人程序员Jun</h3>
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, background: '#f4f4f5', padding: '4px 12px', borderRadius: 999, marginBottom: 24 }}>
                  <span style={{ fontSize: '0.8125rem', color: '#52525b' }}>AI builder in HK</span>
                  <span style={{ width: 3, height: 3, borderRadius: '50%', background: '#d4d4d8' }} />
                  <span style={{ fontSize: '0.8125rem', color: '#52525b' }}>Vibe coding 主理人</span>
                </div>
                <p style={{ margin: 0, fontSize: '0.9375rem', color: '#52525b', lineHeight: 1.6 }}>
                  合作 / 工作机会等，欢迎关注 <a href="https://xhslink.com/m/2CUIT8iyntn" target="_blank" rel="noopener noreferrer" style={{ color: '#09090b', textDecoration: 'underline', fontWeight: 500 }}>小红书</a> 随时私信我。
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
