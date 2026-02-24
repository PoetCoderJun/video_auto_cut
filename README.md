# video_auto_cut

口播视频自动剪辑（Web + 本地流水线）。

## Web 启动（最小）

```bash
python -m pip install -r requirements.txt
cd web_frontend && npm install && cd ..
./scripts/start_web_mvp.sh
```

- Frontend: `http://127.0.0.1:3000`
- API: `http://127.0.0.1:8000/api/v1`

## 单一 Coupon 码体系

现在只有一套码：`coupon code`。

- 前端输入框文案可能仍显示“邀请码”
- 但输入和验证的就是 coupon code
- 不再维护 invite 和 coupon 两套数据源

## 本地 CSV（唯一码源）

默认文件：`./workdir/activation_codes.csv`

CSV 列固定为：

```text
code,credits,max_uses,expires_at,status,source
```

字段说明：
- `code`: coupon 码（唯一）
- `credits`: 发放额度（正整数）
- `max_uses`: 最大可用次数（空=不限）
- `expires_at`: 过期时间（ISO，如 `2026-12-31T23:59:59Z`，空=不过期）
- `status`: `ACTIVE` / `DISABLED`
- `source`: 渠道标记（如 `xhs`）

## `.env` 关键配置

```env
# 本地 coupon CSV 路径（默认就是这个）
COUPON_CODE_SHEET_LOCAL_CSV=./workdir/activation_codes.csv

# API 读取该 CSV。建议用 file:// 绝对路径
COUPON_CODE_SHEET_CSV_URL=file:///Users/huzujun/Desktop/video_auto_cut/workdir/activation_codes.csv
COUPON_CODE_SHEET_CACHE_SECONDS=60
```

如果不配 `COUPON_CODE_SHEET_CSV_URL`，系统会自动回退到 `COUPON_CODE_SHEET_LOCAL_CSV`。

## 创建 Coupon（会直接写入 CSV）

创建一条：

```bash
python scripts/coupon_admin.py create --credits 20 --max-uses 100 --source xhs
```

查看：

```bash
python scripts/coupon_admin.py list
```

初始化空 CSV（只写表头）：

```bash
python scripts/coupon_admin.py template
```

兼容命令（等价）：

```bash
python scripts/invite_admin.py create --credits 20 --max-uses 100 --source xhs
```

## 验证逻辑在哪

系统验证 coupon 时，读的是本地 CSV（经缓存）。

数据库里只维护：
- `activation_code_redemptions`（记录某码被哪些用户用过，用于次数限制）
- `credit_wallets` / `credit_ledger`（额度余额和流水）

也就是说：**coupon 内容本身不在数据库维护，数据库只记录“使用结果”**。
