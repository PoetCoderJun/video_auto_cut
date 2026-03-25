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
  const isDesktopChrome =
    /\bChrome\//.test(userAgent) &&
    /Google/i.test(vendor) &&
    !isEdge &&
    !isOpera;

  return !isDesktopChrome;
}
