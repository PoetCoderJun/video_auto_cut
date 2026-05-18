"use client";

type AnalyticsParams = Record<string, string | number | boolean | null | undefined>;

declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (
      command: "config" | "event" | "js",
      target: string | Date,
      params?: AnalyticsParams
    ) => void;
  }
}

export function trackEvent(eventName: string, params: AnalyticsParams = {}) {
  if (typeof window === "undefined" || typeof window.gtag !== "function") {
    return;
  }
  window.gtag("event", eventName, params);
}

export function getFileExtension(fileName: string): string {
  const extension = fileName.split(".").pop()?.trim().toLowerCase() || "";
  return extension && extension !== fileName.toLowerCase() ? extension : "unknown";
}

export function getFileSizeMbBucket(sizeBytes: number): string {
  const sizeMb = sizeBytes / 1024 / 1024;
  if (sizeMb < 50) return "under_50";
  if (sizeMb < 200) return "50_to_200";
  if (sizeMb < 500) return "200_to_500";
  if (sizeMb < 1024) return "500_to_1024";
  return "over_1024";
}
