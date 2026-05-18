import type { Metadata } from "next";

import SeoArticlePage from "@/components/seo-article-page";

export const metadata: Metadata = {
  title: "小红书和知识口播视频 AI 剪辑",
  description:
    "PoetCut 适合小红书、知识分享、课程切片和个人 IP 口播视频，自动删废话、整理字幕章节并导出可发布成片。",
  alternates: {
    canonical: "/use-cases/koubo-video-editing",
  },
};

export default function KouboVideoEditingPage() {
  return (
    <SeoArticlePage
      eyebrow="使用场景"
      title="适合小红书和知识类口播的视频自动剪辑"
      description="口播创作者最耗时的环节往往不是拍摄，而是把说错、停顿、重复表达和无效铺垫剪掉。PoetCut 的目标是把这部分后期流程压缩到一次上传和一次确认。"
      sections={[
        {
          title: "小红书口播",
          body:
            "适合教程、经验分享、产品讲解、个人观点等内容。录制时可以保持自然表达，后期再让 AI 生成更紧凑的版本。",
        },
        {
          title: "课程和知识切片",
          body:
            "对较长内容，章节整理能帮助把信息分段，导出时也能保留字幕和章节提示，方便观众快速跟上重点。",
        },
        {
          title: "个人 IP 日更",
          body:
            "当创作者需要持续发布，自动转字幕、自动删废话和浏览器本地导出能减少重复劳动，把时间留给选题和表达。",
        },
      ]}
    />
  );
}
