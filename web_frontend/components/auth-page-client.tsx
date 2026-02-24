"use client";

import Link from "next/link";
import {useRouter} from "next/navigation";
import {useState, FormEvent, useEffect} from "react";
import {Toaster, toast} from "sonner";
import {authClient} from "../lib/auth-client";
import {PENDING_INVITE_CODE_KEY} from "../lib/session";
import {Video, ArrowRight, Loader2} from "lucide-react";

type AuthViewName = "SIGN_IN" | "SIGN_UP";

type AuthPageClientProps = {
  view: AuthViewName;
};

export default function AuthPageClient({view}: AuthPageClientProps) {
  const router = useRouter();
  
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (view === "SIGN_UP") {
      try {
        const savedCode = localStorage.getItem(PENDING_INVITE_CODE_KEY);
        if (savedCode) setInviteCode(savedCode);
      } catch {
        // ignore
      }
    }
  }, [view]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error("请填写所有必填字段");
      return;
    }
    if (view === "SIGN_UP" && !inviteCode.trim()) {
      toast.error("请输入邀请码");
      return;
    }

    setLoading(true);
    
    try {
      if (view === "SIGN_UP") {
        const code = inviteCode.trim().toUpperCase();
        try {
          localStorage.setItem(PENDING_INVITE_CODE_KEY, code);
        } catch {
          // ignore
        }
        
        const res = await authClient.signUp.email({
          email,
          password,
          name: email.split("@")[0] || "User",
          inviteCode: code,
        } as any);
        if (res.error) throw res.error;
        toast.success("注册成功！");
        router.push("/");
      } else {
        const res = await authClient.signIn.email({
          email,
          password,
        });
        if (res.error) throw res.error;
        toast.success("登录成功！");
        router.push("/");
      }
    } catch (err: any) {
      toast.error(err.message || "操作失败，请重试");
    } finally {
      setLoading(false);
    }
  };

  const isSignIn = view === "SIGN_IN";

  return (
    <main className="app-container fade-in" style={{maxWidth: 420, margin: "0 auto"}}>
      <header className="top-nav">
        <Link href="/" className="nav-brand" style={{display: 'flex', alignItems: 'center', gap: 8, fontWeight: 700}}>
          <Video className="w-5 h-5" />
          AI Cut
        </Link>
      </header>
      
      <section style={{minHeight: "calc(100vh - 120px)", display: "flex", flexDirection: "column", justifyContent: "center", padding: "0 24px"}}>
        <div style={{
          background: "var(--panel)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)",
          padding: "40px 32px",
          boxShadow: "var(--shadow-md)",
          width: "100%"
        }}>
          <div style={{textAlign: "center", marginBottom: 32}}>
            <div style={{
              width: 48, height: 48, borderRadius: "12px", background: "#f4f4f5", 
              display: "flex", alignItems: "center", justifyContent: "center", 
              margin: "0 auto 16px"
            }}>
              <Video className="w-6 h-6" style={{color: "var(--text-main)"}} />
            </div>
            <h1 style={{fontSize: "1.5rem", marginBottom: 8}}>
              {isSignIn ? "欢迎回来" : "创建账号"}
            </h1>
            <p className="muted" style={{fontSize: "0.875rem", margin: 0}}>
              {isSignIn ? "登录以继续使用 AI 智能剪辑" : "注册账号开始体验智能剪辑工作流"}
            </p>
          </div>

          <form onSubmit={handleSubmit} style={{display: "flex", flexDirection: "column", gap: 16}}>
            <div style={{display: "flex", flexDirection: "column", gap: 6}}>
              <label style={{fontSize: "0.875rem", fontWeight: 500, color: "var(--text-main)"}}>邮箱地址</label>
              <input 
                type="email" 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@example.com"
                required
                disabled={loading}
              />
            </div>
            
            <div style={{display: "flex", flexDirection: "column", gap: 6}}>
              <label style={{fontSize: "0.875rem", fontWeight: 500, color: "var(--text-main)"}}>密码</label>
              <input 
                type="password" 
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="请输入密码"
                required
                disabled={loading}
              />
            </div>

            {!isSignIn && (
              <div style={{display: "flex", flexDirection: "column", gap: 6}}>
                <label style={{fontSize: "0.875rem", fontWeight: 500, color: "var(--text-main)"}}>邀请码</label>
                <input 
                  type="text" 
                  value={inviteCode}
                  onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                  placeholder="请输入注册邀请码"
                  required
                  disabled={loading}
                />
              </div>
            )}

            <button 
              type="submit" 
              className="btn-primary" 
              style={{marginTop: 8, height: 44, width: "100%"}}
              disabled={loading}
            >
              {loading ? (
                <><Loader2 className="w-4 h-4 mr-2" style={{animation: "spin 1s linear infinite"}} /> 处理中...</>
              ) : (
                <>{isSignIn ? "登录" : "注册账号"} <ArrowRight className="w-4 h-4 ml-2" /></>
              )}
            </button>
          </form>

          <div style={{marginTop: 24, textAlign: "center", fontSize: "0.875rem"}}>
            <span className="muted">
              {isSignIn ? "还没有账号？" : "已有账号？"}
            </span>{" "}
            <Link 
              href={isSignIn ? "/sign-up" : "/sign-in"} 
              style={{fontWeight: 600, color: "var(--text-main)", textDecoration: "underline", textUnderlineOffset: 4}}
            >
              {isSignIn ? "立即注册" : "前往登录"}
            </Link>
          </div>
        </div>
      </section>
      
      <Toaster position="top-center" richColors />
    </main>
  );
}
