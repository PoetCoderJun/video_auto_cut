import Link from "next/link";
import Image from "next/image";
import { ArrowLeft } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const WECHAT_ID = "PoetCoderJun";
const BETA_NOTES = [
  "如果效果不好，无条件退款",
  "当前为内测版本，功能持续更新中",
  "如遇问题可在讨论群反馈",
  "可以在讨论群提任何需求，我帮你实现",
];

export default function BetaPage() {
  return (
    <div className="min-h-screen bg-background font-sans">
      <header className="sticky top-0 z-40 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto flex h-14 items-center justify-between px-4 sm:px-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            返回首页
          </Link>
          <div className="flex items-center gap-3">
            <Link href="/sign-in">
              <Button variant="ghost">登录</Button>
            </Link>
            <Link href="/sign-up">
              <Button className="rounded-full">注册</Button>
            </Link>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-10 sm:px-6 sm:py-16">
        <section className="relative overflow-hidden rounded-3xl border border-border/70 bg-gradient-to-br from-amber-50 via-orange-50 to-white p-8 shadow-sm sm:p-10">
          <div className="absolute -right-24 -top-24 h-56 w-56 rounded-full bg-orange-100/50 blur-3xl" />
          <div className="absolute -bottom-24 -left-24 h-56 w-56 rounded-full bg-amber-100/60 blur-3xl" />
          <div className="relative space-y-4">
            <Badge className="rounded-full bg-foreground text-background hover:bg-foreground">
              小红书购买用户专属内测
            </Badge>
            <h1 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
              AI Cut 内测介绍页
            </h1>
            <p className="max-w-3xl text-sm leading-7 text-muted-foreground sm:text-base">
              感谢你在小红书支持。当前版本为邀请制内测，凭邀请码即可登录使用。右上角可直接注册 / 登录。
            </p>
          </div>
        </section>

        <div className="my-8 border-t border-dashed border-border" />

        <section className="grid gap-6 lg:grid-cols-2">
          <Card className="border-indigo-200">
            <CardHeader>
              <CardTitle className="text-xl">如何开始内测</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-sm leading-7 text-muted-foreground">
                添加微信领取邀请码，注册账号激活后即可开始使用内测功能。
              </p>
              <div className="mx-auto w-fit rounded-2xl border border-border bg-white p-3 shadow-sm">
                <Image
                  src="/wechat.jpg"
                  alt="测试群微信二维码"
                  width={180}
                  height={180}
                  className="h-[180px] w-[180px]"
                />
              </div>
              <div className="rounded-lg border border-dashed border-border bg-muted/30 px-4 py-3 text-sm">
                <p className="text-muted-foreground">微信号</p>
                <p className="mt-1 font-semibold tracking-wide text-foreground">{WECHAT_ID}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  添加时请备注：内测
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-xl">内测说明</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3 text-sm text-muted-foreground sm:text-base">
                {BETA_NOTES.map((note, idx) => (
                  <li
                    key={note}
                    className="flex items-start gap-3 rounded-lg border border-border/60 bg-muted/20 px-4 py-3"
                  >
                    <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-foreground text-xs font-semibold text-background">
                      {idx + 1}
                    </span>
                    <span>{note}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </section>
      </main>
    </div>
  );
}
