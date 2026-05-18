# video_auto_cut

口播视频自动剪辑（Web + 本地流水线），当前部署方式仅支持 Railway。

## License & Commercial Boundary

本仓库源代码按 `AGPL-3.0-or-later` 开放，适合作为可自托管的开源代码库。PoetCut 名称、Logo、线上托管服务、生产环境配置、密钥、数据库、客户数据、分析账号、支付/商户配置和其他商业运营资产不包含在开源授权内。

如果你要自托管，需要配置自己的 Turso/libsql、对象存储、ASR、LLM、Better Auth 和站点 URL。官方线上服务可以继续保留私有的生产配置、运营规则、账单/支付链路和供应商路由。

更完整的开源边界见 `docs/open_source_strategy.md`。

## 目录约定

- `web_frontend/`：Next.js 前端
- `web_api/`：FastAPI API + worker
- `video_auto_cut/`：剪辑与转写流水线
- `scripts/`：运维脚本（保留 Railway/本地开发相关）
- `docs/`：设计与接口文档

## Quick Start

环境要求：

- Python 3.9
- `uv`

安装 `uv`：

```bash
# macOS（Homebrew）
brew install uv

# macOS / Linux 通用官方安装脚本
curl -LsSf https://astral.sh/uv/install.sh | sh
```

如果当前 shell 需要加载仓库里的本地凭证：

```bash
set -a
source .env
set +a
```

项目默认约定：

- Test 编辑链路已经收口为 Python direct prompt runner：`asr -> delete -> polish`，`chapter/highlight` 作为 sidecar 产物。
- 运行时直接使用 `.env` 中的 `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY`（或 `DASHSCOPE_API_KEY` fallback），不再依赖 PI provider、`.pi/settings.json` 或 repo-local PI extension。
- 模型调用默认关闭 thinking；如需开启，在 `.env` 设置 `LLM_ENABLE_THINKING=1`。

当前仓库的 Python 依赖仍通过 `requirements.txt` 安装，尚未切换到 `uv sync` 项目结构。

## 本地启动 direct prompt Test 流程

最简单的命令是：

```bash
./scripts/run_direct_prompt_test.sh test_data/media/1.wav
```

它会自动加载 `.env`，并执行：

1. ASR 转写
2. delete
3. polish
4. chapter sidecar
5. highlight sidecar

输出默认落到 `workdir/direct_prompt_runs/<时间戳>_<文件名>/`，其中：

- `test.summary.json`：本次运行汇总
- `*.raw.test.txt`：原始转录后的 Test 行
- `*.test.txt`：最终字幕行
- `*.test.srt`：最终字幕 SRT
- `*.chapters.txt`：最终章节
- `*.highlights.json`：高亮合同

也可以直接调用模块：

```bash
python -m video_auto_cut.direct_prompt_runner --task test --input test_data/media/1.wav --output workdir/direct_prompt_runs/manual/test.summary.json
```

## 本地开发

```bash
python -m pip install -r requirements.txt
cd web_frontend && npm install && cd ..
pkill -f "uvicorn web_api.app:app" || true
pkill -f "python -m web_api" || true
pkill -f "next dev --hostname 127.0.0.1 --port 3000" || true
./scripts/start_web_mvp.sh
```

- Frontend: `http://127.0.0.1:3000`
- API: `http://127.0.0.1:8000/api/v1`

本地 Web 启动现在只保留 **Turso + 本地 replica** 模式：请先在 `.env` 配置 `TURSO_DATABASE_URL`、`TURSO_AUTH_TOKEN`、`TURSO_LOCAL_REPLICA_PATH`，然后运行：

```bash
./scripts/start_web_mvp.sh debug   # 开发模式
./scripts/start_web_mvp.sh         # 生产构建模式（等价于 build）
```

## Railway 部署

Railway 不会读取本地 `.env`，必须在服务 Variables 中配置。

建议在同一 Railway 项目创建 3 个服务：

### 1) API 服务

- Root Directory：仓库根目录
- Dockerfile：`Dockerfile`
- Start Command：留空（使用 Dockerfile 默认 `uvicorn ... --port $PORT`）

### 2) Worker 服务

- Root Directory：仓库根目录
- Dockerfile：`Dockerfile`
- Start Command：`python -m web_api`

### 3) Frontend 服务

- Root Directory：`web_frontend`
- Dockerfile：`web_frontend/Dockerfile`

## 必要环境变量（至少）

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`
- `BETTER_AUTH_SECRET`（>= 32 字符）
- `DASHSCOPE_ASR_API_KEY`（或 `DASHSCOPE_API_KEY`）
- `OSS_ENDPOINT`
- `OSS_BUCKET`
- `OSS_ACCESS_KEY_ID`
- `OSS_ACCESS_KEY_SECRET`
- `NEXT_PUBLIC_SITE_URL`
- `BETTER_AUTH_URL`
- `WEB_CORS_ALLOWED_ORIGINS`
- `NEXT_PUBLIC_API_BASE`

## SEO / Analytics

- `NEXT_PUBLIC_GA_MEASUREMENT_ID`：Google Analytics 4 衡量 ID。当前生产代码默认使用 `G-5NFPXTC63E`；如需切换属性，在 Railway Frontend Variables 中覆盖该变量后重新部署。
- `NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION`：Google Search Console 的站点验证 meta 值，可选。填入后会输出 `google-site-verification`。

上线后建议在 Google Search Console 中提交：

```text
https://poetcut.online/sitemap.xml
```

## CORS / 互通检查

- API 的 `WEB_CORS_ALLOWED_ORIGINS` 必须包含前端完整 origin。
- 前端的 `NEXT_PUBLIC_API_BASE` 必须指向 API 的 `/api/v1`。

## Coupon 管理

创建：

```bash
python scripts/coupon_admin.py create --credits 5 --source xhs
```

批量创建：

```bash
python scripts/coupon_admin.py create --count 100 --credits 5 --source xhs
```

查看：

```bash
python scripts/coupon_admin.py list --limit 50
```

禁用：

```bash
python scripts/coupon_admin.py disable --code CPN-XXXX
```

## 文档

详细设计和接口文档见 `docs/`。
