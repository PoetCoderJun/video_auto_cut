"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, FormEvent, useEffect } from "react";
import { toast } from "sonner";
import { authClient } from "../lib/auth-client";
import { activateInviteCode, verifyCouponCode } from "../lib/api";
import { PENDING_INVITE_CODE_KEY } from "../lib/session";
import { Video, ArrowRight, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type AuthViewName = "SIGN_IN" | "SIGN_UP";

type AuthPageClientProps = {
  view: AuthViewName;
};

export default function AuthPageClient({ view }: AuthPageClientProps) {
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
        await verifyCouponCode(code);
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
        
        let activated = false;
        try {
          const tokenResult = await (authClient as any).token();
          const token = String(tokenResult?.data?.token || "").trim();
          if (token) {
            const activation = await activateInviteCode(code, token);
            activated = true;
            try {
              localStorage.removeItem(PENDING_INVITE_CODE_KEY);
            } catch {
              // ignore
            }
            if (activation.granted_credits > 0) {
              toast.success(
                `注册成功，已自动发放 ${activation.granted_credits} 次免费额度`
              );
            } else {
              toast.success("注册成功");
            }
          }
        } catch {
          // Fallback: homepage will retry activation from pending localStorage code.
        }
        if (!activated) {
          toast.success("注册成功，正在自动激活邀请码...");
        }
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
    <div className="container relative min-h-screen flex-col items-center justify-center grid lg:max-w-none lg:grid-cols-2 lg:px-0 bg-muted/20">
      <Link
        href="/"
        className="absolute left-4 top-4 md:left-8 md:top-8 z-20 flex items-center gap-2 font-bold text-lg"
      >
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Video className="h-4 w-4" />
        </div>
        <span>AI Cut</span>
      </Link>
      
      <div className="relative hidden h-full flex-col bg-muted p-10 text-white dark:border-r lg:flex">
        <div className="absolute inset-0 bg-zinc-900" />
        <div className="relative z-20 flex items-center text-lg font-medium">
          <Sparkles className="mr-2 h-6 w-6" />
          AI 智能剪辑
        </div>
        <div className="relative z-20 mt-auto">
          <blockquote className="space-y-2">
            <p className="text-lg">
              &ldquo;这款工具彻底改变了我的工作流。以前需要几个小时的剪辑工作，现在几分钟就能完成，而且效果惊人。&rdquo;
            </p>
            <footer className="text-sm">诗人程序员Jun</footer>
          </blockquote>
        </div>
      </div>
      
      <div className="lg:p-8">
        <div className="mx-auto flex w-full flex-col justify-center space-y-6 sm:w-[350px]">
          <div className="flex flex-col space-y-2 text-center">
            <h1 className="text-2xl font-semibold tracking-tight">
              {isSignIn ? "欢迎回来" : "创建账号"}
            </h1>
            <p className="text-sm text-muted-foreground">
              {isSignIn
                ? "输入邮箱登录以继续使用"
                : "注册账号开始体验智能剪辑工作流"}
            </p>
          </div>
          
          <div className="grid gap-6">
            <form onSubmit={handleSubmit}>
              <div className="grid gap-4">
                <div className="grid gap-2">
                  <Label htmlFor="email">邮箱地址</Label>
                  <Input
                    id="email"
                    placeholder="name@example.com"
                    type="email"
                    autoCapitalize="none"
                    autoComplete="email"
                    autoCorrect="off"
                    disabled={loading}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="password">密码</Label>
                  <Input
                    id="password"
                    placeholder="请输入密码"
                    type="password"
                    autoComplete={isSignIn ? "current-password" : "new-password"}
                    disabled={loading}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
                
                {!isSignIn && (
                  <div className="grid gap-2">
                    <Label htmlFor="inviteCode">邀请码</Label>
                    <Input
                      id="inviteCode"
                      placeholder="请输入注册邀请码"
                      type="text"
                      autoCapitalize="characters"
                      disabled={loading}
                      value={inviteCode}
                      onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                      required
                    />
                  </div>
                )}
                
                <Button disabled={loading} className="mt-2">
                  {loading ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      处理中...
                    </>
                  ) : (
                    <>
                      {isSignIn ? "登录" : "注册账号"}
                      <ArrowRight className="ml-2 h-4 w-4" />
                    </>
                  )}
                </Button>
              </div>
            </form>
            
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-background px-2 text-muted-foreground">
                  {isSignIn ? "还没有账号？" : "已有账号？"}
                </span>
              </div>
            </div>
            
            <Link href={isSignIn ? "/sign-up" : "/sign-in"}>
              <Button variant="outline" className="w-full">
                {isSignIn ? "立即注册" : "前往登录"}
              </Button>
            </Link>
          </div>
          
          <p className="px-8 text-center text-sm text-muted-foreground">
            点击继续即表示您同意我们的{" "}
            <Link
              href="/terms"
              className="underline underline-offset-4 hover:text-primary"
            >
              服务条款
            </Link>{" "}
            和{" "}
            <Link
              href="/privacy"
              className="underline underline-offset-4 hover:text-primary"
            >
              隐私政策
            </Link>
            。
          </p>
        </div>
      </div>
    </div>
  );
}
