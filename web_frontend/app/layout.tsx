import "./globals.css";
import type { Metadata } from "next";
import Analytics from "@/components/analytics";
import { Toaster } from "@/components/ui/sonner";

const siteName = "PoetCut";
const siteDescription =
  "PoetCut 是面向口播创作者的 AI 视频剪辑工具，自动转字幕、删除废话和重复表达、整理章节，并在浏览器中导出可发布成片。";
const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "http://127.0.0.1:3000";
const googleSiteVerification =
  process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION?.trim();

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  applicationName: siteName,
  title: {
    default: "PoetCut | AI 口播视频自动剪辑与字幕精剪",
    template: `%s | PoetCut`,
  },
  description: siteDescription,
  keywords: [
    "PoetCut",
    "AI Cut",
    "AI 视频剪辑",
    "口播视频剪辑",
    "自动删除废话",
    "字幕驱动剪辑",
    "小红书口播视频",
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
    title: "PoetCut | AI 口播视频自动剪辑",
    description: siteDescription,
    siteName,
    locale: "zh_CN",
  },
  twitter: {
    card: "summary_large_image",
    title: "PoetCut | AI 口播视频自动剪辑",
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
