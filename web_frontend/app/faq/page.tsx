import type { Metadata } from "next";

import SeoArticlePage from "@/components/seo-article-page";

export const metadata: Metadata = {
  title: "PoetCut AI网感口播剪辑常见问题",
  description:
    "了解 PoetCut AI网感口播剪辑支持的视频格式、剪辑层、字幕层、包装层、自动删废话、数据处理方式和兑换码额度。",
  alternates: {
    canonical: "/faq",
  },
};

export default function FaqPage() {
  return (
    <SeoArticlePage
      eyebrow="AI网感口播剪辑 FAQ"
      title="PoetCut 使用前常见问题"
      description="这里整理了口播视频上传、AI口播剪辑、自动删废话、字幕章节和浏览器导出的几个基础问题。"
      sections={[
        {
          title: "支持哪些视频格式？",
          body:
            "当前支持 MP4、MOV、MKV、WebM、M4V、TS、M2TS、MTS 等主流格式，适合桌面浏览器上传口播视频。",
        },
        {
          title: "PoetCut 是 AI口播剪辑工具吗？",
          body:
            "是。PoetCut 的核心流程是把中文口播视频转成字幕，再用 AI 判断口误、停顿、重复表达和废话，最后导出带字幕章节的视频。",
        },
        {
          title: "PoetCut 和 Typeless 这类语音打字产品像在哪里？",
          body:
            "它们都不满足于逐字转写。语音打字产品把自然口述整理成清晰文字；PoetCut 把自然口播整理成可发布视频，并处理字幕、章节、进度条和高亮包装。",
        },
        {
          title: "AI网感剪辑一般包括哪些层？",
          body:
            "一般包括三层：剪辑层负责去停顿、删废话、删重复和分章节；字幕层负责自动字幕、润色、断句和关键词高光；包装层负责进度条、章节卡、花字、转场、片头、封面和模板化风格。",
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
            "新账号赠送 1 次体验剪辑。体验额度用完后，可以通过首页的小红书购买入口购买兑换码，目前套餐是 30 元 5 次剪辑。",
        },
      ]}
    />
  );
}
