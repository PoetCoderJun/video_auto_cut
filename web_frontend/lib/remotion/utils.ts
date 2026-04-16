import type { WebRenderConfig } from "../api";

export function getRenderConfigTotalDuration(
  config: WebRenderConfig | null,
): number {
  if (!config) return 1;

  return Math.max(
    1,
    config.input_props.captions.reduce(
      (max, item) => Math.max(max, item.end),
      0,
    ),
    config.input_props.topics.reduce(
      (max, item) => Math.max(max, item.end),
      0,
    ),
    config.input_props.segments.reduce(
      (sum, item) => sum + Math.max(0, item.end - item.start),
      0,
    ),
  );
}
