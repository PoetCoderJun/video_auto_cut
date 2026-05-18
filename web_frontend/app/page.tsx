import type {Metadata} from "next";
import HomePageClient from "../components/home-page-client";

export const metadata: Metadata = {
  title: "AI 口播视频自动剪辑、删废话与字幕导出",
  description:
    "PoetCut 帮口播创作者自动转字幕、删除废话和重复表达、整理章节，并在浏览器中导出带字幕和进度条的可发布视频。",
  alternates: {
    canonical: "/",
  },
  keywords: [
    "PoetCut",
    "AI Cut",
    "AI 视频剪辑",
    "AI 口播视频剪辑",
    "自动剪辑视频",
    "自动删除废话",
    "口播视频精简",
    "小红书口播视频剪辑",
    "自动生成章节",
    "字幕驱动剪辑",
  ],
};

const softwareApplicationLd = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "PoetCut",
  alternateName: ["AI Cut", "AI 视频智能剪辑"],
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
    "PoetCut 面向口播视频创作者，自动提取字幕、删除废话和重复表达、整理章节，并帮助快速导出视频成片。",
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
