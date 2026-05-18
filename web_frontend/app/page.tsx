import type {Metadata} from "next";
import HomePageClient from "../components/home-page-client";

export const metadata: Metadata = {
  title: "AI口播剪辑：随便录，几分钟一键出片",
  description:
    "PoetCut 帮中文口播创作者自动删除废话、停顿和重复表达，全自动包装字幕、进度条和章节，只需上传原始口播视频即可得到可发布草稿。",
  alternates: {
    canonical: "/",
  },
  keywords: [
    "PoetCut",
    "AI Cut",
    "AI口播剪辑",
    "AI网感剪辑",
    "AI网感口播剪辑",
    "AI 口播剪辑",
    "AI口播视频剪辑",
    "AI 视频剪辑",
    "AI 口播视频剪辑",
    "口播视频自动剪辑",
    "口播自动删废话",
    "口播字幕剪辑",
    "口播视频包装",
    "视频进度条自动生成",
    "章节卡自动生成",
    "关键词高光",
    "自动剪辑视频",
    "自动删除废话",
    "自动剪废话",
    "口播视频精简",
    "个人IP口播剪辑",
    "小红书口播视频剪辑",
    "自动生成章节",
    "字幕驱动剪辑",
  ],
};

const softwareApplicationLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "PoetCut",
  alternateName: ["AI Cut", "AI口播剪辑", "AI 视频智能剪辑"],
  url: "https://poetcut.online",
  applicationCategory: "MultimediaApplication",
  operatingSystem: "Web",
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "CNY",
    availability: "https://schema.org/InStock",
  },
  description:
    "PoetCut 面向中文口播视频创作者，把原始口播自动剪成可发布视频，删除废话和重复表达、整理字幕章节，并生成进度条和高亮包装。",
};

const faqLd = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: [
    {
      "@type": "Question",
      name: "PoetCut 支持哪些视频格式？",
      acceptedAnswer: {
        "@type": "Answer",
        text: "支持 MP4、MOV、MKV、WebM、M4V、TS、M2TS、MTS，单次最长 10 分钟。",
      },
    },
    {
      "@type": "Question",
      name: "PoetCut 适合做 AI口播剪辑吗？",
      acceptedAnswer: {
        "@type": "Answer",
        text: "适合。PoetCut 主要面向中文口播视频，把自然讲话中的口误、停顿、重复和改口整理成可编辑字幕，再生成章节、进度条、高亮等视频包装。",
      },
    },
    {
      "@type": "Question",
      name: "能自动删除口播视频里的废话吗？",
      acceptedAnswer: {
        "@type": "Answer",
        text: "可以。PoetCut 会根据字幕和上下文识别停顿、口头禅、重复表达和说错后重来的片段，生成可编辑的精简草稿。",
      },
    },
    {
      "@type": "Question",
      name: "对浏览器有什么要求？",
      acceptedAnswer: {
        "@type": "Answer",
        text: "请使用桌面版 Chrome。由于导出渲染依赖浏览器本地 FFmpeg，暂不支持 Edge、Safari、Firefox 及移动端浏览器。",
      },
    },
    {
      "@type": "Question",
      name: "视频数据安全吗？会上传到哪里？",
      acceptedAnswer: {
        "@type": "Answer",
        text: "视频上传至阿里云 OSS 用于云端 AI 语音转写与分析，分析完成后不会长期保留。最终视频导出渲染完全在本地浏览器中完成，成片不会上传至服务器。",
      },
    },
    {
      "@type": "Question",
      name: "PoetCut 现在怎么使用？",
      acceptedAnswer: {
        "@type": "Answer",
        text: "当前是限时免费阶段。登录账号后即可上传、处理并导出，暂时不展示额度，也不会扣除额度。",
      },
    },
  ],
};

export default function HomePage() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{__html: JSON.stringify(softwareApplicationLd)}} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{__html: JSON.stringify(faqLd)}} />
      <HomePageClient />
    </>
  );
}
