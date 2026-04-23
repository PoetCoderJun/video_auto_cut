"use client";

const MOBILE_DEVICE_PATTERN =
  /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile|Tablet|Windows Phone|HarmonyOS/i;

type NavigatorWithUAData = Navigator & {
  userAgentData?: {
    mobile?: boolean;
    brands?: Array<{
      brand?: string;
      version?: string;
    }>;
  };
};

export function isUnsupportedMobileUploadDevice(): boolean {
  if (typeof window === "undefined" || typeof navigator === "undefined") {
    return false;
  }

  const runtimeNavigator = navigator as NavigatorWithUAData;
  const userAgent = runtimeNavigator.userAgent || "";
  const vendor = runtimeNavigator.vendor || "";
  const mobileByUA = MOBILE_DEVICE_PATTERN.test(`${userAgent} ${vendor}`);
  const mobileByClientHints = runtimeNavigator.userAgentData?.mobile === true;
  const ipadLikeDesktop =
    runtimeNavigator.platform === "MacIntel" && runtimeNavigator.maxTouchPoints > 1;

  return mobileByUA || mobileByClientHints || ipadLikeDesktop;
}

export function isUnsupportedLocalVideoBrowser(): boolean {
  if (typeof window === "undefined" || typeof navigator === "undefined") {
    return false;
  }

  const runtimeNavigator = navigator as NavigatorWithUAData;
  const userAgent = runtimeNavigator.userAgent || "";
  const vendor = runtimeNavigator.vendor || "";
  const brands = runtimeNavigator.userAgentData?.brands || [];
  const brandNames = brands.map((item) => String(item?.brand || ""));

  const isEdge =
    /\bEdg\//.test(userAgent) ||
    brandNames.some((brand) => /Microsoft Edge/i.test(brand));
  const isOpera =
    /\bOPR\//.test(userAgent) ||
    brandNames.some((brand) => /Opera/i.test(brand));
  const isChromeLike =
    /(?:Headless)?Chrome\//.test(userAgent) ||
    brandNames.some((brand) => /Chrom(e|ium)/i.test(brand));
  const isDesktopChrome =
    isChromeLike &&
    /Google/i.test(vendor) &&
    !isEdge &&
    !isOpera;

  return !isDesktopChrome;
}

export function buildGuestDeviceFingerprint(): string {
  if (typeof window === "undefined" || typeof navigator === "undefined") {
    return "server";
  }

  const runtimeNavigator = navigator as NavigatorWithUAData;
  const screenValue = typeof window.screen !== "undefined" ? window.screen : null;
  const timezone =
    typeof Intl !== "undefined"
      ? Intl.DateTimeFormat().resolvedOptions().timeZone || ""
      : "";

  const payload = {
    userAgent: runtimeNavigator.userAgent || "",
    language: runtimeNavigator.language || "",
    languages: Array.isArray(runtimeNavigator.languages) ? runtimeNavigator.languages : [],
    platform: runtimeNavigator.platform || "",
    vendor: runtimeNavigator.vendor || "",
    hardwareConcurrency:
      typeof runtimeNavigator.hardwareConcurrency === "number"
        ? runtimeNavigator.hardwareConcurrency
        : 0,
    maxTouchPoints:
      typeof runtimeNavigator.maxTouchPoints === "number"
        ? runtimeNavigator.maxTouchPoints
        : 0,
    webdriver: Boolean((runtimeNavigator as Navigator & {webdriver?: boolean}).webdriver),
    screen: screenValue
      ? {
          width: Number(screenValue.width || 0),
          height: Number(screenValue.height || 0),
          colorDepth: Number(screenValue.colorDepth || 0),
          pixelDepth: Number(screenValue.pixelDepth || 0),
        }
      : null,
    timezone,
  };

  return JSON.stringify(payload);
}
