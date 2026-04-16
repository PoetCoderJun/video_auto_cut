import type { Context, Model, SimpleStreamOptions } from "@mariozechner/pi-ai";
import { streamSimpleOpenAICompletions } from "@mariozechner/pi-ai";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

function uniqueModels(...values: Array<string | undefined>): string[] {
  return Array.from(
    new Set(
      values
        .map((value) => (value || "").trim())
        .filter((value) => value.length > 0),
    ),
  );
}

function isQwenReasoningModel(id: string): boolean {
  return id === "qwen3.6-plus";
}

function isKimiReasoningModel(id: string): boolean {
  return id === "kimi-k2.5";
}

function forceQwenThinkingOff(payload: unknown): unknown {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return payload;
  }
  const next = { ...(payload as Record<string, unknown>) };
  next.enable_thinking = false;
  delete next.reasoning_effort;
  delete next.reasoning;
  if ("chat_template_kwargs" in next) {
    const current = next.chat_template_kwargs;
    next.chat_template_kwargs =
      current && typeof current === "object" && !Array.isArray(current)
        ? { ...(current as Record<string, unknown>), enable_thinking: false }
        : { enable_thinking: false };
  }
  return next;
}

function forceKimiThinkingOff(payload: unknown): unknown {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return payload;
  }
  const next = { ...(payload as Record<string, unknown>) };
  next.enable_thinking = false;
  delete next.thinking;
  delete next.reasoning_effort;
  delete next.reasoning;
  delete next.chat_template_kwargs;
  return next;
}

function streamVacLlm(
  model: Model<"openai-completions">,
  context: Context,
  options?: SimpleStreamOptions,
) {
  return streamSimpleOpenAICompletions(model, context, {
    ...options,
    onPayload: async (payload, currentModel) => {
      const upstream = await options?.onPayload?.(payload, currentModel);
      if (currentModel.id === "qwen3.6-plus") {
        return forceQwenThinkingOff(upstream ?? payload);
      }
      if (currentModel.id === "kimi-k2.5") {
        return forceKimiThinkingOff(upstream ?? payload);
      }
      return upstream;
    },
  });
}

export default function registerProjectLlmProvider(pi: ExtensionAPI) {
  const baseUrl = (process.env.LLM_BASE_URL || "").trim();
  if (!baseUrl) return;

  const apiKeyEnv = process.env.LLM_API_KEY
    ? "LLM_API_KEY"
    : process.env.DASHSCOPE_API_KEY
      ? "DASHSCOPE_API_KEY"
      : "";
  const models = uniqueModels(
    process.env.LLM_MODEL,
    "kimi-k2.5",
    "qwen-plus",
    "qwen-flash",
    "qwen3.6-plus",
    "test-model",
  ).map((id) => ({
    id,
    name: id,
    reasoning: id.includes("kimi") || id.includes("gpt") || isQwenReasoningModel(id) || isKimiReasoningModel(id),
    input: ["text"] as const,
    contextWindow: 262144,
    maxTokens: 32768,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    compat: {
      supportsDeveloperRole: false,
      supportsReasoningEffort: false,
      thinkingFormat: isQwenReasoningModel(id) ? "qwen" : "openai",
      maxTokensField: "max_tokens" as const,
    },
  }));

  pi.registerProvider("vac-llm", {
    baseUrl,
    api: "openai-completions",
    apiKey: apiKeyEnv || "LLM_API_KEY",
    authHeader: true,
    streamSimple: streamVacLlm,
    models,
  });
}
