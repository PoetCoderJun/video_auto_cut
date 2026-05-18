import type { Metadata } from "next";

import SeoArticlePage from "@/components/seo-article-page";

export const metadata: Metadata = {
  title: "字幕驱动的视频剪辑工具",
  description:
    "PoetCut 把口播视频转成可编辑字幕，通过文字精简、章节整理和本地浏览器导出，降低短视频后期制作成本。",
  alternates: {
    canonical: "/features/subtitle-driven-editing",
  },
};

export default function SubtitleDrivenEditingPage() {
  return (
    <SeoArticlePage
      eyebrow="字幕驱动剪辑"
      title="像改文稿一样剪口播视频"
      description="传统剪辑需要在时间轴上找停顿和口误。PoetCut 先把口播内容变成结构化字幕，让剪辑动作围绕文字展开，更适合知识分享、课程片段、个人 IP 和小红书口播内容。"
      sections={[
        {
          title: "先看懂内容，再做剪辑",
          body:
            "系统会先完成语音转写，再进入 AI 精简和润色阶段。这样每一次删除都尽量基于上下文，而不是只依赖声音空白或固定规则。",
        },
        {
          title: "章节和进度条自动整理",
          body:
            "长一点的口播视频会自动生成章节结构，导出时可以渲染章节卡片和进度提示，让观众更容易理解视频脉络。",
        },
        {
          title: "导出前仍可编辑",
          body:
            "进入编辑页后，用户可以继续调整字幕文本、删除状态和章节边界，再生成最终导出配置。",
        },
      ]}
    />
  );
}
