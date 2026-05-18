import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------
 * 统一的视觉 token —— 在浅色卡片上保证清晰可读
 * ------------------------------------------------------------------ */
const C = {
  /** 主要图形（中等灰，不用 opacity） */
  main: "#475569", // slate-600
  /** 次要图形（浅灰） */
  sub: "#94a3b8", // slate-400
  /** 极淡装饰 */
  dim: "#cbd5e1", // slate-300
  /** 背景色块 */
  bg: "#f1f5f9", // slate-100
} as const;

/**
 * 步骤 1：上传视频 —— 视频文件飞向云端
 */
export function UploadIllustration({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 200 140"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("w-full h-auto", className)}
      aria-hidden="true"
    >
      {/* 背景色块 */}
      <rect x="20" y="20" width="160" height="100" rx="14" fill={C.bg} />

      {/* 云朵 */}
      <path
        d="M72 44 Q78 38 86 41 Q92 35 100 38 Q108 35 114 41 Q122 38 128 44"
        stroke={C.dim}
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
      />

      {/* 上传箭头 */}
      <path d="M100 55 L100 78" stroke={C.main} strokeWidth="3" strokeLinecap="round" />
      <path
        d="M92 62 L100 54 L108 62"
        stroke={C.main}
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* 视频文件 */}
      <rect x="78" y="76" width="44" height="32" rx="6" fill="white" stroke={C.main} strokeWidth="2" />

      {/* 文件内播放按钮 */}
      <circle cx="100" cy="92" r="8" fill={C.bg} />
      <polygon points="97,88 97,96 105,92" fill={C.main} />

      {/* 文件底部进度条 */}
      <rect x="86" y="102" width="28" height="3" rx="1.5" fill={C.dim} />

      {/* 漂浮小点 */}
      <circle cx="62" cy="84" r="2.5" fill={C.dim} />
      <circle cx="138" cy="72" r="2" fill={C.dim} />
      <circle cx="144" cy="94" r="1.5" fill={C.dim} />
    </svg>
  );
}

/**
 * 步骤 2：AI 智能精简 —— AI 分析并裁剪冗余内容
 */
export function AICutIllustration({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 200 140"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("w-full h-auto", className)}
      aria-hidden="true"
    >
      {/* 背景色块 */}
      <rect x="20" y="20" width="160" height="100" rx="14" fill={C.bg} />

      {/* AI 核心 */}
      <circle cx="100" cy="46" r="14" fill="white" stroke={C.main} strokeWidth="2" />
      <circle cx="100" cy="46" r="5" fill={C.main} />

      {/* 连接线 */}
      <path d="M86 46 L58 62" stroke={C.dim} strokeWidth="1.5" strokeLinecap="round" />
      <path d="M114 46 L142 62" stroke={C.dim} strokeWidth="1.5" strokeLinecap="round" />

      {/* 左侧：冗余文字（被划掉） */}
      <rect x="44" y="64" width="48" height="5" rx="2.5" fill={C.dim} />
      <rect x="44" y="73" width="38" height="5" rx="2.5" fill={C.dim} />
      <rect x="44" y="82" width="52" height="5" rx="2.5" fill={C.dim} />
      <rect x="44" y="91" width="28" height="5" rx="2.5" fill={C.dim} />

      {/* 删除线 */}
      <line x1="42" y1="62" x2="100" y2="96" stroke={C.sub} strokeWidth="1.5" strokeLinecap="round" />

      {/* 虚线切割 */}
      <line x1="100" y1="60" x2="100" y2="102" stroke={C.main} strokeWidth="2" strokeDasharray="5 4" />

      {/* 右侧：保留内容（更醒目） */}
      <rect x="114" y="70" width="40" height="5" rx="2.5" fill={C.main} />
      <rect x="114" y="79" width="32" height="5" rx="2.5" fill={C.main} />
      <rect x="114" y="88" width="38" height="5" rx="2.5" fill={C.main} />

      {/* 底部小剪刀 */}
      <path d="M126 100 L129 104 L126 108" stroke={C.sub} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M134 100 L131 104 L134 108" stroke={C.sub} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * 步骤 3：快速导出成片 —— 带字幕和章节的成品视频
 */
export function ExportIllustration({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 200 140"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn("w-full h-auto", className)}
      aria-hidden="true"
    >
      {/* 背景色块 */}
      <rect x="20" y="20" width="160" height="100" rx="14" fill={C.bg} />

      {/* 导出样片截图外框 */}
      <rect x="38" y="34" width="124" height="72" rx="10" fill="white" stroke={C.main} strokeWidth="2" />
      <clipPath id="export-sample-clip">
        <rect x="43" y="39" width="114" height="62" rx="6" />
      </clipPath>
      <g clipPath="url(#export-sample-clip)">
        <rect x="43" y="39" width="114" height="62" fill="#111827" />
        <rect x="43" y="39" width="114" height="62" fill="#334155" opacity="0.35" />
        <rect x="43" y="77" width="114" height="24" fill="#020617" opacity="0.72" />

        {/* 口播画面剪影 */}
        <circle cx="94" cy="57" r="10" fill="#e2e8f0" opacity="0.9" />
        <path d="M78 89 Q94 70 112 89 L118 101 L72 101 Z" fill="#cbd5e1" opacity="0.9" />
        <rect x="118" y="45" width="28" height="18" rx="3" fill="#64748b" opacity="0.75" />
        <rect x="123" y="50" width="18" height="3" rx="1.5" fill="#cbd5e1" opacity="0.7" />
        <rect x="123" y="56" width="12" height="3" rx="1.5" fill="#cbd5e1" opacity="0.45" />

        {/* 章节标签 */}
        <rect x="49" y="45" width="44" height="10" rx="3" fill="#020617" opacity="0.72" />
        <circle cx="55" cy="50" r="2" fill="#34d399" />
        <rect x="60" y="48" width="26" height="3.5" rx="1.75" fill="white" opacity="0.82" />

        {/* 字幕和高亮 */}
        <rect x="59" y="73" width="82" height="8" rx="4" fill="#020617" opacity="0.55" />
        <rect x="66" y="75.5" width="26" height="3" rx="1.5" fill="white" />
        <rect x="94" y="73.8" width="16" height="6.2" rx="2" fill="#6ee7b7" />
        <rect x="113" y="75.5" width="20" height="3" rx="1.5" fill="white" />

        {/* 分段进度条 */}
        <rect x="56" y="91" width="88" height="2.5" rx="1.25" fill="white" opacity="0.25" />
        <rect x="56" y="91" width="35" height="2.5" rx="1.25" fill="#6ee7b7" />
        <rect x="92" y="91" width="28" height="2.5" rx="1.25" fill="#67e8f9" />
      </g>

      {/* 完成勾选 */}
      <circle cx="158" cy="46" r="7" fill="white" stroke={C.main} strokeWidth="1.5" />
      <path d="M155 46 L157 48 L161 44" stroke={C.main} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
