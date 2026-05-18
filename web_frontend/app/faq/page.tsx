import type { Metadata } from "next";

import SeoArticlePage from "@/components/seo-article-page";

export const metadata: Metadata = {
  title: "PoetCut 常见问题",
  description:
    "了解 PoetCut 支持的视频格式、浏览器要求、数据处理方式和限时免费使用方式。",
  alternates: {
    canonical: "/faq",
  },
};

export default function FaqPage() {
  return (
    <SeoArticlePage
      eyebrow="常见问题"
      title="PoetCut 使用前常见问题"
      description="这里整理了口播视频上传、AI 精简、字幕章节和浏览器导出的几个基础问题。"
      sections={[
        {
          title: "支持哪些视频格式？",
          body:
            "当前支持 MP4、MOV、MKV、WebM、M4V、TS、M2TS、MTS 等主流格式，适合桌面浏览器上传口播视频。",
        },
        {
          title: "为什么推荐桌面版 Chrome？",
          body:
            "PoetCut 的最终导出依赖浏览器本地渲染能力。桌面版 Chrome 的兼容性和图形能力更稳定，能减少导出失败。",
        },
        {
          title: "视频会保存在哪里？",
          body:
            "上传的视频会用于云端语音转写和 AI 分析；最终成片导出在本地浏览器完成，不会把导出成片上传到服务器。",
        },
        {
          title: "当前如何使用？",
          body:
            "当前处于限时免费阶段，登录账号后即可上传、处理并导出。后续如果计费方式变化，会在产品内明确说明。",
        },
      ]}
    />
  );
}
