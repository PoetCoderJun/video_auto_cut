import Link from "next/link";
import { ArrowLeft, ArrowRight } from "lucide-react";

import { Button } from "@/components/ui/button";

type SeoArticlePageProps = {
  eyebrow: string;
  title: string;
  description: string;
  sections: Array<{
    title: string;
    body: string;
  }>;
};

export default function SeoArticlePage({
  eyebrow,
  title,
  description,
  sections,
}: SeoArticlePageProps) {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
        <Link
          href="/"
          className="mb-10 inline-flex items-center gap-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          返回 PoetCut
        </Link>
        <article>
          <p className="text-sm font-semibold text-primary">{eyebrow}</p>
          <h1 className="mt-3 text-3xl font-extrabold tracking-tight sm:text-5xl">
            {title}
          </h1>
          <p className="mt-5 text-base leading-8 text-muted-foreground sm:text-lg">
            {description}
          </p>
          <div className="mt-10 space-y-9">
            {sections.map((section) => (
              <section key={section.title}>
                <h2 className="text-xl font-bold tracking-tight">{section.title}</h2>
                <p className="mt-3 text-sm leading-7 text-muted-foreground sm:text-base">
                  {section.body}
                </p>
              </section>
            ))}
          </div>
        </article>
        <div className="mt-12 rounded-xl border bg-card p-5">
          <h2 className="text-lg font-bold">试试自动剪一条口播视频</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            上传视频后，PoetCut 会自动转字幕、识别冗余表达、整理章节，并在浏览器中导出带字幕和章节进度的成片。
          </p>
          <Link href="/">
            <Button className="mt-4 rounded-full">
              回到首页上传
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </Link>
        </div>
      </div>
    </main>
  );
}
