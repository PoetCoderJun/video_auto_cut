#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from coupon_admin import load_env_file, row_value
from web_api.db import get_conn, init_db


DEFAULT_TEMPLATE = """已收到，感谢支持。

你的 PoetCut 兑换码是：
{{CODE}}

使用方式：
1. 打开 PoetCut
2. 登录账号
3. 点击首页「兑换码兑换」
4. 输入上面的兑换码
5. 兑换成功后到账 5 次剪辑额度

这个兑换码仅可使用一次，请不要发给其他人。"""


def fetch_codes(source: str, limit: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT code
            FROM coupon_codes
            WHERE source = ?
              AND status = 'ACTIVE'
              AND COALESCE(used_count, 0) = 0
            ORDER BY coupon_id ASC
            LIMIT ?
            """,
            (source, int(limit)),
        ).fetchall()
    return [str(row_value(row, "code", 0)).strip() for row in rows if str(row_value(row, "code", 0)).strip()]


def render_html(*, codes: list[str], template: str, source: str) -> str:
    codes_json = json.dumps(codes, ensure_ascii=False)
    template_json = json.dumps(template, ensure_ascii=False)
    title = f"PoetCut 小红书发码助手 - {source}"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif; }}
    body {{ margin: 0; background: #f8fafc; color: #0f172a; }}
    main {{ max-width: 680px; margin: 0 auto; padding: 18px; }}
    h1 {{ margin: 8px 0 6px; font-size: 24px; line-height: 1.2; }}
    p {{ color: #475569; line-height: 1.55; }}
    .panel {{ background: white; border: 1px solid #e2e8f0; border-radius: 14px; padding: 16px; box-shadow: 0 8px 24px rgba(15, 23, 42, .06); }}
    .stats {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 14px 0; }}
    .stat {{ border: 1px solid #e2e8f0; border-radius: 12px; padding: 10px; background: #f8fafc; }}
    .stat b {{ display: block; font-size: 20px; }}
    label {{ display: block; margin: 14px 0 6px; font-size: 13px; font-weight: 700; }}
    input, textarea {{ width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 12px; padding: 12px; font: inherit; background: white; }}
    textarea {{ min-height: 230px; resize: vertical; line-height: 1.5; }}
    button {{ width: 100%; border: 0; border-radius: 999px; padding: 14px 16px; font-size: 16px; font-weight: 800; color: white; background: #111827; margin-top: 10px; }}
    button.secondary {{ color: #111827; background: #e2e8f0; }}
    button.warn {{ background: #b91c1c; }}
    .code {{ margin-top: 10px; padding: 12px; border-radius: 12px; background: #ecfeff; color: #155e75; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 18px; text-align: center; }}
    .hint {{ font-size: 12px; color: #64748b; }}
  </style>
</head>
<body>
  <main>
    <h1>PoetCut 小红书发码助手</h1>
    <p>手机打开这个文件，点「复制回复」后粘贴到小红书私信。它只在本机记录已发状态，不会自动操作小红书。</p>
    <section class="panel">
      <div class="stats">
        <div class="stat"><span>总数</span><b id="total">0</b></div>
        <div class="stat"><span>已发</span><b id="used">0</b></div>
        <div class="stat"><span>剩余</span><b id="left">0</b></div>
      </div>
      <label for="buyer">买家备注，可选</label>
      <input id="buyer" placeholder="例如：小红书昵称 / 付款时间" />
      <div class="code" id="currentCode">-</div>
      <label for="reply">待发送回复</label>
      <textarea id="reply" readonly></textarea>
      <button id="copyBtn">复制回复</button>
      <button id="markBtn" class="secondary">标记已发并切到下一个</button>
      <button id="undoBtn" class="secondary">撤回上一次标记</button>
      <button id="resetBtn" class="warn">清空本机已发记录</button>
      <p class="hint">提示：如果浏览器不允许自动复制，点进文本框全选复制即可。</p>
    </section>
  </main>
  <script>
    const CODES = {codes_json};
    const TEMPLATE = {template_json};
    const STORAGE_KEY = "poetcut_xhs_used_codes_" + {json.dumps(source)};
    const LOG_KEY = "poetcut_xhs_sent_log_" + {json.dumps(source)};
    const usedSet = () => new Set(JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]"));
    const saveUsed = (set) => localStorage.setItem(STORAGE_KEY, JSON.stringify([...set]));
    const log = () => JSON.parse(localStorage.getItem(LOG_KEY) || "[]");
    const saveLog = (items) => localStorage.setItem(LOG_KEY, JSON.stringify(items));
    const nextCode = () => CODES.find((code) => !usedSet().has(code)) || "";
    const renderReply = (code) => TEMPLATE.replaceAll("{{CODE}}", code || "暂无可用兑换码");
    function refresh() {{
      const used = usedSet();
      const code = nextCode();
      document.getElementById("total").textContent = String(CODES.length);
      document.getElementById("used").textContent = String(used.size);
      document.getElementById("left").textContent = String(Math.max(0, CODES.length - used.size));
      document.getElementById("currentCode").textContent = code || "暂无可用兑换码";
      document.getElementById("reply").value = renderReply(code);
    }}
    async function copyReply() {{
      const text = document.getElementById("reply").value;
      try {{
        await navigator.clipboard.writeText(text);
        alert("已复制，可以去小红书粘贴发送。");
      }} catch {{
        const reply = document.getElementById("reply");
        reply.focus();
        reply.select();
        document.execCommand("copy");
        alert("已选中回复文本，如未复制成功请手动复制。");
      }}
    }}
    function markSent() {{
      const code = nextCode();
      if (!code) return alert("没有剩余兑换码了。");
      const used = usedSet();
      used.add(code);
      saveUsed(used);
      const items = log();
      items.push({{ code, buyer: document.getElementById("buyer").value.trim(), sentAt: new Date().toISOString() }});
      saveLog(items);
      document.getElementById("buyer").value = "";
      refresh();
    }}
    function undo() {{
      const items = log();
      const last = items.pop();
      if (!last) return alert("没有可撤回记录。");
      saveLog(items);
      const used = usedSet();
      used.delete(last.code);
      saveUsed(used);
      refresh();
    }}
    document.getElementById("copyBtn").addEventListener("click", copyReply);
    document.getElementById("markBtn").addEventListener("click", markSent);
    document.getElementById("undoBtn").addEventListener("click", undo);
    document.getElementById("resetBtn").addEventListener("click", () => {{
      if (confirm("确定清空这个手机上的已发记录？不会影响数据库。")) {{
        localStorage.removeItem(STORAGE_KEY);
        localStorage.removeItem(LOG_KEY);
        refresh();
      }}
    }});
    refresh();
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a phone-friendly XHS coupon reply kit.")
    parser.add_argument("--source", default="xhs-20260518", help="coupon source tag")
    parser.add_argument("--limit", type=int, default=500, help="max coupons to export")
    parser.add_argument(
        "--out-dir",
        default=str(REPO_ROOT / "workdir" / "xhs_reply_kit"),
        help="output directory; keep it outside git",
    )
    args = parser.parse_args()

    load_env_file(REPO_ROOT / ".env")
    init_db()

    codes = fetch_codes(args.source, args.limit)
    if not codes:
        raise SystemExit(f"no active unused coupons found for source={args.source}")

    out_dir = Path(args.out_dir).expanduser()
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "codes.txt").write_text("\n".join(codes) + "\n", encoding="utf-8")
    (out_dir / "reply_template.txt").write_text(DEFAULT_TEMPLATE + "\n", encoding="utf-8")
    (out_dir / "xhs_coupon_sender.html").write_text(
        render_html(codes=codes, template=DEFAULT_TEMPLATE, source=args.source),
        encoding="utf-8",
    )
    (out_dir / "README.md").write_text(
        "\n".join(
            [
                "# PoetCut 小红书发码助手",
                "",
                "把 `xhs_coupon_sender.html` 通过 AirDrop、微信文件传输助手或 iCloud Drive 发到手机。",
                "手机打开后点击「复制回复」，再粘贴到小红书私信。",
                "",
                "注意：已发状态保存在手机浏览器本地，不会回写数据库。",
                "真正核销仍以用户在 PoetCut 里兑换成功为准。",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"exported {len(codes)} codes to {out_dir}")
    print(f"open on phone: {out_dir / 'xhs_coupon_sender.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
