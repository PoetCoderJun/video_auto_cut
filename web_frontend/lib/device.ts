"use client";

const MOBILE_DEVICE_PATTERN =
  /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini|Mobile|Tablet|Windows Phone|HarmonyOS/i;

type NavigatorWithUAData = Navigator & {
  userAgentData?: {
    mobile?: boolean;
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
