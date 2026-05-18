import type { Metadata } from "next";

import SeoArticlePage from "@/components/seo-article-page";

export const metadata: Metadata = {
  title: "AI网感口播剪辑：剪辑层、字幕层、包装层自动化",
  description:
    "PoetCut 参考语音打字产品的思路，把自然口播里的思考、停顿、口误、重复和废话整理成可编辑字幕，并自动完成剪辑层、字幕层、包装层的发布流程。",
  alternates: {
    canonical: "/ai-koubo-jianji",
  },
  keywords: [
    "AI口播剪辑",
    "AI网感剪辑",
    "AI网感口播剪辑",
    "AI 口播剪辑",
    "AI口播视频剪辑",
    "口播视频自动剪辑",
    "口播自动删废话",
    "口播字幕剪辑",
    "小红书口播剪辑",
  ],
};

export default function AiKouboJianjiPage() {
  return (
    <SeoArticlePage
      eyebrow="AI口播剪辑"
      title="AI网感口播剪辑：从自然讲话到可发布视频"
      description="PoetCut 专注中文口播视频后期。它解决的不是单纯 ASR 转写，而是把真实讲话里的思考、停顿、口误、重复表达和废话整理成可编辑字幕，再生成带章节、进度条和高亮的成片。"
      sections={[
        {
          title: "和 Typeless 这类语音打字产品的共同点",
          body:
            "语音打字产品的价值不是逐字记录，而是把自然口述整理成能直接发送的文字。PoetCut 做的是视频版：把原始口播整理成观众能看下去的字幕、节奏和包装。",
        },
        {
          title: "AI网感剪辑的三层结构",
          body:
            "剪辑层负责去停顿、去废话、删重复、压缩节奏和分章节；字幕层负责自动字幕、润色、断句重排和关键词高光；包装层负责进度条、章节卡、花字、转场、封面和行业模板。PoetCut 会优先把口播最耗时的剪辑层和字幕层自动化，并逐步覆盖包装层。",
        },
        {
          title: "ASR 的结果不是成片",
          body:
            "普通 ASR 会把嗯、啊、停顿、错词、重复、说到一半重来都写进字幕里。真正的口播剪辑需要理解最终意图，保留有用内容，删除干扰表达。",
        },
        {
          title: "剪辑不应该只靠拖时间轴",
          body:
            "口播视频的剪辑点往往藏在文字语义里。PoetCut 先把视频变成可编辑字幕，再围绕字幕做删除、恢复、章节和导出，让剪辑更直观。",
        },
        {
          title: "包装也是口播剪辑的一部分",
          body:
            "字幕、进度条、章节标题、高亮词，本质上都是把原始口播变成可发布内容。PoetCut 希望把这些重复包装步骤自动化，而不是让创作者每条视频都重新做一遍。",
        },
      ]}
    />
  );
}
