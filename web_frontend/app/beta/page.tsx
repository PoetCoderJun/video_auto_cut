import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ArrowLeft, ArrowRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const WECHAT_ID = "PoetCoderJun";

export const metadata: Metadata = {
  title: "AI Cut 内测邀请",
  description: "AI Cut 内测邀请页。",
};

export default function BetaPage() {
  return (
    <div className="min-h-screen bg-background font-sans text-foreground">
      <header className="border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container mx-auto flex h-14 items-center justify-between px-3 sm:h-16 sm:px-6">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground sm:gap-2 sm:text-sm"
          >
            <ArrowLeft className="h-4 w-4" />
            返回首页
          </Link>
          <div className="flex items-center gap-2 sm:gap-3">
            <Link href="/sign-in">
              <Button variant="ghost" className="h-9 rounded-full px-3 text-sm sm:h-10 sm:px-4">
                登录
              </Button>
            </Link>
            <Link href="/sign-up">
              <Button className="h-9 rounded-full px-4 text-sm sm:h-10 sm:px-5">注册</Button>
            </Link>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-3 py-3 sm:flex sm:min-h-[calc(100svh-4rem)] sm:items-center sm:px-6 sm:py-6">
        <div className="w-full space-y-4">
          <section className="rounded-2xl border border-border/70 bg-card p-4 shadow-sm sm:rounded-3xl sm:p-6">
            <div className="space-y-2.5">
              <Badge className="rounded-full bg-foreground text-background hover:bg-foreground">
                AI Cut 内测邀请
              </Badge>
              <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-4xl">
                获取邀请码
              </h1>
              <p className="max-w-3xl text-sm leading-6 text-muted-foreground sm:text-base sm:leading-7">
                由于算力资源限制，当前版本为邀请制内测，凭邀请码即可登录使用。右上角可直接注册 /
                登录。
              </p>
              <Link href="/sign-up">
                <Button className="h-10 rounded-full px-4 sm:h-10">
                  去注册
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
            </div>
          </section>

          <section className="grid gap-4 lg:grid-cols-[1fr_1.06fr]">
            <div className="rounded-2xl border border-border bg-card shadow-sm">
              <div className="space-y-4 p-4 sm:p-5">
                <h2 className="text-lg font-semibold text-foreground sm:text-xl">添加微信</h2>
                <p className="text-sm leading-6 text-muted-foreground sm:text-base sm:leading-7">
                  由于平台限制，我只能邀请大家添加我的微信，我会一个个把邀请码发给大家。因为目前是业余时间做了这个网站，希望多多体谅。
                </p>
                <div className="mx-auto w-fit rounded-2xl border border-border bg-background p-3 shadow-sm">
                  <Image
                    src="/wechat.jpg"
                    alt="AI Cut 内测微信二维码"
                    width={184}
                    height={184}
                    className="h-44 w-44 rounded-lg object-contain sm:h-52 sm:w-52"
                    priority
                  />
                </div>
                <div className="rounded-lg border border-dashed border-border bg-muted/30 px-4 py-3 text-sm">
                  <p className="text-muted-foreground">微信号</p>
                  <p className="mt-1 font-semibold tracking-wide text-foreground">{WECHAT_ID}</p>
                  <p className="mt-1 text-xs text-muted-foreground">添加时请备注：内测</p>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-border bg-card shadow-sm">
              <div className="space-y-4 p-4 sm:p-5">
                <h2 className="text-lg font-semibold text-foreground sm:text-xl">给内测用户的一封信</h2>
                <div className="space-y-3 text-sm leading-7 text-muted-foreground sm:text-base sm:leading-8">
                  <p>感谢你愿意参加这次内测，也谢谢你愿意花时间体验这个产品。</p>
                  <p>
                    它还在持续打磨中，由于是首先源自于我自己的需求，很需要大家根据自己的剪口播需求和视频节奏来一起迭代。
                  </p>
                  <p>
                    如果你在使用过程中觉得哪里不顺手，或者有任何想法和建议，都欢迎直接告诉我。
                    AI 让开发和迭代变得更快，这也是这个产品能够落地的原因，你有需求我帮你直接实现。
                  </p>
                  <p>我会认真看每一条反馈，也会尽力把它一点点做好。</p>
                </div>
              </div>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
