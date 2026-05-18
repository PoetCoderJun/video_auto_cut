import "./globals.css";
import type { Metadata } from "next";
import Analytics from "@/components/analytics";
import { Toaster } from "@/components/ui/sonner";

const siteName = "PoetCut";
const siteDescription =
  "PoetCut 是面向中文口播创作者的 AI 剪辑工具，自动删废话、整理字幕和章节，并生成进度条、高亮等可发布包装。";
const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "http://127.0.0.1:3000";
const googleSiteVerification =
  process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION?.trim();

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  applicationName: siteName,
  title: {
    default: "PoetCut | AI口播剪辑，自动删废话并导出成片",
    template: `%s | PoetCut`,
  },
  description: siteDescription,
  keywords: [
    "PoetCut",
    "AI Cut",
    "AI口播剪辑",
    "AI网感剪辑",
    "AI网感口播剪辑",
    "AI 口播剪辑",
    "AI口播视频剪辑",
    "AI 视频剪辑",
    "口播视频剪辑",
    "口播视频自动剪辑",
    "口播自动剪辑",
    "口播自动删废话",
    "自动删除废话",
    "自动剪废话",
    "口播字幕剪辑",
    "口播视频包装",
    "自动视频包装",
    "字幕驱动剪辑",
    "个人IP口播剪辑",
    "小红书口播视频",
    "小红书口播剪辑",
    "自动生成字幕",
    "自动生成章节",
  ],
  authors: [{ name: "PoetCut" }],
  creator: "PoetCut",
  publisher: "PoetCut",
  category: "AI video editing",
  alternates: {
    canonical: "/",
  },
  openGraph: {
    type: "website",
    url: siteUrl,
    title: "PoetCut | AI口播剪辑工具",
    description: siteDescription,
    siteName,
    locale: "zh_CN",
  },
  twitter: {
    card: "summary_large_image",
    title: "PoetCut | AI口播剪辑工具",
    description: siteDescription,
  },
  ...(googleSiteVerification
    ? {
        verification: {
          google: googleSiteVerification,
        },
      }
    : {}),
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-image-preview": "large",
      "max-snippet": -1,
      "max-video-preview": -1,
    },
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-background font-sans antialiased" suppressHydrationWarning>
        {children}
        <Analytics />
        <Toaster />
      </body>
    </html>
  );
}
