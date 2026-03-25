import { MOCK_CAN_DECODE_FALSE_MARKER } from "./video-render-compatibility";

function getFileStem(name: string): string {
  const dotIndex = name.lastIndexOf(".");
  if (dotIndex <= 0) return name || "source";
  return name.slice(0, dotIndex);
}

function stripMockMarkers(name: string): string {
  const escapedMarker = MOCK_CAN_DECODE_FALSE_MARKER.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return name
    .replace(new RegExp(escapedMarker, "ig"), "")
    .replace(/__+/g, "_")
    .replace(/^_+|_+$/g, "");
}

export function getBrowserCompatibleOutputName(sourceName: string): string {
  const normalizedStem = stripMockMarkers(getFileStem(sourceName)).trim() || "source";
  return `${normalizedStem}_browser_compatible.mp4`;
}
