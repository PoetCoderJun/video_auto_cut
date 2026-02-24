import type {Metadata} from "next";
import HomePageClient from "../components/home-page-client";

export const metadata: Metadata = {
  title: "AI 视频智能剪辑 | 自动删废话与章节整理",
  description: "上传口播视频，自动提取字幕、精简内容并生成章节，快速导出可发布成片。",
  alternates: {
    canonical: "/",
  },
  keywords: [
    "AI 视频剪辑",
    "自动剪辑视频",
    "口播视频精简",
    "自动生成章节",
    "字幕驱动剪辑",
  ],
};

const softwareApplicationLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "AI 视频智能剪辑",
  applicationCategory: "MultimediaApplication",
  operatingSystem: "Web",
  description: "自动提取字幕、精简口播内容并生成章节，帮助快速导出视频成片。",
};

const faqLd = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: [
    {
      "@type": "Question",
      name: "支持哪些视频格式？",
      acceptedAnswer: {
        "@type": "Answer",
        text: "支持 MP4、MOV、MKV、WebM、M4V、TS、M2TS、MTS。",
      },
    },
    {
      "@type": "Question",
      name: "一次处理大概需要多久？",
      acceptedAnswer: {
        "@type": "Answer",
        text: "取决于视频时长和机器性能，通常几分钟到十几分钟。",
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
