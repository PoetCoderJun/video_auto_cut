import { cn } from "@/lib/utils";

/**
 * PoetCut 品牌 Logo —— 简洁的剪刀符号
 *
 * 深色圆角方块 + 白色剪刀图形
 */
type LogoProps = {
  className?: string;
  /** 是否显示右侧文字 "PoetCut" */
  showText?: boolean;
  /** 图标尺寸（默认 32） */
  iconSize?: number;
};

export function LogoIcon({ className, size = 32 }: { className?: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="PoetCut Logo"
    >
      {/* 深色背景 */}
      <rect width="32" height="32" rx="8" fill="#0f172a" />

      {/* 剪刀上半刃 */}
      <path
        d="M11 9 L16 16 L21 9"
        stroke="white"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* 剪刀下半刃 */}
      <path
        d="M11 23 L16 16 L21 23"
        stroke="white"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* 中心轴点 */}
      <circle cx="16" cy="16" r="2.5" fill="white" />
    </svg>
  );
}

export default function Logo({ className, showText = true, iconSize = 32 }: LogoProps) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <LogoIcon size={iconSize} />
      {showText && (
        <span className="text-lg font-bold tracking-tight text-foreground">
          PoetCut
        </span>
      )}
    </div>
  );
}
