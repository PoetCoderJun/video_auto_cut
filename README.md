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

只有一套码：`coupon code`。

- 前端文案可显示“邀请码”
- 实际兑换和校验是 coupon
- 线上来源是 Turso 的 `coupon_codes` 表

## `.env` 关键配置

```env
TURSO_DATABASE_URL=libsql://<your-db>-<org>.turso.io
TURSO_AUTH_TOKEN=<your-token>
TURSO_LOCAL_REPLICA_PATH=./workdir/web_api_turso_replica.db

# ASR: OSS + DashScope Filetrans
ASR_BACKEND=dashscope_filetrans
ASR_DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com
ASR_DASHSCOPE_MODEL=qwen3-asr-flash-filetrans
ASR_DASHSCOPE_TASK=
ASR_DASHSCOPE_API_KEY=<optional, fallback to DASHSCOPE_API_KEY>
ASR_DASHSCOPE_LANGUAGE_HINTS=zh,en
ASR_DASHSCOPE_ENABLE_WORDS=1
ASR_DASHSCOPE_SENTENCE_RULE_WITH_PUNC=1
ASR_DASHSCOPE_WORD_SPLIT_ENABLED=1
ASR_DASHSCOPE_WORD_SPLIT_ON_COMMA=1
ASR_DASHSCOPE_WORD_SPLIT_COMMA_PAUSE_S=0.4
ASR_DASHSCOPE_WORD_SPLIT_MIN_CHARS=12
ASR_DASHSCOPE_WORD_VAD_GAP_S=1.0
ASR_DASHSCOPE_WORD_MAX_SEGMENT_S=8.0
ASR_DASHSCOPE_INSERT_NO_SPEECH=1
ASR_DASHSCOPE_INSERT_HEAD_NO_SPEECH=1
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_BUCKET=<your-oss-bucket>
OSS_ACCESS_KEY_ID=<your-ak>
OSS_ACCESS_KEY_SECRET=<your-sk>
OSS_AUDIO_PREFIX=video-auto-cut/asr
OSS_SIGNED_URL_TTL_SECONDS=86400
```

## 管理 Coupon（直接写线上库）

创建：

```bash
python scripts/coupon_admin.py create --credits 20 --source xhs
```

批量创建（一次创建 n 个）：

```bash
python scripts/coupon_admin.py create --count 20 --credits 20 --source xhs
```

查看：

```bash
python scripts/coupon_admin.py list --limit 50
```

禁用：

```bash
python scripts/coupon_admin.py disable --code CPN-XXXX
```

字段说明：
- `code`: coupon 码（唯一）
- `credits`: 发放额度
- `used_count`: 是否已兑换（`0` 未兑换，`1` 已兑换）
- `expires_at`: 过期时间（ISO，空=不过期）
- `status`: `ACTIVE` / `DISABLED`
- `source`: 渠道来源

## 线上校验逻辑

用户提交码时，后端直接查 `coupon_codes`，并校验：
- 码存在且 `status=ACTIVE`
- 未过期
- `used_count = 0`

通过后写入：
- `credit_ledger`（额度流水）
- `coupon_codes.used_count` 置为 `1`
- `coupon_codes.status` 置为 `DISABLED`

所以现在是：**coupon 定义和兑换结果都在线上库**。
