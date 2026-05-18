import type {MetadataRoute} from "next";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "http://127.0.0.1:3000";

export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();
  const routes: Array<{
    path: string;
    changeFrequency: MetadataRoute.Sitemap[number]["changeFrequency"];
    priority: number;
  }> = [
    { path: "", changeFrequency: "weekly", priority: 1 },
    { path: "/ai-koubo-jianji", changeFrequency: "weekly", priority: 0.95 },
    { path: "/features/remove-filler-words", changeFrequency: "monthly", priority: 0.8 },
    { path: "/features/subtitle-driven-editing", changeFrequency: "monthly", priority: 0.8 },
    { path: "/use-cases/koubo-video-editing", changeFrequency: "monthly", priority: 0.8 },
    { path: "/faq", changeFrequency: "monthly", priority: 0.7 },
  ];

  return routes.map((route) => ({
    url: `${siteUrl}${route.path}`,
    lastModified,
    changeFrequency: route.changeFrequency,
    priority: route.priority,
  }));
}
