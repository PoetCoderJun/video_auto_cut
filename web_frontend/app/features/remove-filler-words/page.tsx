import type { Metadata } from "next";

import SeoArticlePage from "@/components/seo-article-page";

export const metadata: Metadata = {
  title: "AI口播剪辑自动删废话、停顿和重复表达",
  description:
    "PoetCut 面向中文 AI口播剪辑场景，自动识别说错、重复、停顿和无效语气词，把一次录制整理成更紧凑的可发布视频。",
  alternates: {
    canonical: "/features/remove-filler-words",
  },
};

export default function RemoveFillerWordsPage() {
  return (
    <SeoArticlePage
      eyebrow="AI口播剪辑"
      title="自动删除口播视频里的废话和重复表达"
      description="很多口播视频并不是内容不好，而是录制时会自然出现停顿、返工、口头禅和重复说明。就像语音打字工具不会只保留逐字口述，PoetCut 也会先把视频转成可编辑字幕，再根据语义判断哪些片段应该保留、哪些片段可以删除。"
      sections={[
        {
          title: "适合一次录制的真实口播",
          body:
            "创作者可以先完整讲完，不必因为一句话说错就重新开始。后期阶段再用 AI 找出重复句、无信息停顿和明显口误，减少人工拖时间轴的时间。",
        },
        {
          title: "字幕和画面同步剪辑",
          body:
            "PoetCut 的剪辑以字幕行为核心，删除字幕时会同步影响对应的视频片段，让口播剪辑更接近编辑文稿，而不是反复拖动传统剪辑轨道。",
        },
        {
          title: "保留人工确认",
          body:
            "AI 会给出精简后的草稿，但用户仍然可以在导出前检查字幕、恢复误删内容、调整章节，保证效率和可控性同时存在。",
        },
      ]}
    />
  );
}
