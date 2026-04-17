# video_auto_cut

口播视频自动剪辑（Web + 本地流水线），当前部署方式仅支持 Railway。

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
- `pi`（可选；用于代理式协作，依赖 Node.js 20+）

安装 `uv`：

```bash
# macOS（Homebrew）
brew install uv

# macOS / Linux 通用官方安装脚本
curl -LsSf https://astral.sh/uv/install.sh | sh
```

安装 `pi`：

```bash
npm install -g @mariozechner/pi-coding-agent
```

如果当前 shell 需要加载仓库里的本地凭证：

```bash
set -a
source .env
set +a
```

当前仓库的 Python 依赖仍通过 `requirements.txt` 安装，尚未切换到 `uv sync` 项目结构。

## 本地启动 PI 并直接执行四步剪辑

仓库已经通过 `.pi/settings.json` 配好自动加载 `skills/`，所以只要从仓库根目录启动，PI 会自动发现本地 skills。

最简单的命令是：

```bash
./scripts/run_pi_test.sh test_data/media/1.wav
```

它会自动执行：

1. `asr-transcribe`
2. `delete`
3. `polish`
4. `chapter`

输出默认落到 `workdir/pi_runs/<时间戳>_<文件名>/`，其中：

- `test.summary.json`：本次运行汇总
- `*.raw.test.json`：原始转录后的 Test 行
- `*.test.json`：最终字幕行
- `*.test.srt`：最终字幕 SRT
- `*.chapters.json`：最终章节

如果要直接进 PI 交互模式，也可以：

```bash
cd /path/to/video_auto_cut
set -a && source .env && set +a
pi
```

然后让它按项目里的 `test-agent-editing` 工作流做四步剪辑。

## 本地开发

```bash
python -m pip install -r requirements.txt
cd web_frontend && npm install && cd ..
pkill -f "uvicorn web_api.app:app" || true
pkill -f "python -m web_api" || true
pkill -f "next dev --hostname 127.0.0.1 --port 3000" || true
WEB_DB_LOCAL_ONLY=1 ./scripts/start_web_mvp.sh debug
./scripts/start_web_mvp.sh
```

- Frontend: `http://127.0.0.1:3000`
- API: `http://127.0.0.1:8000/api/v1`

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

## CORS / 互通检查

- API 的 `WEB_CORS_ALLOWED_ORIGINS` 必须包含前端完整 origin。
- 前端的 `NEXT_PUBLIC_API_BASE` 必须指向 API 的 `/api/v1`。

## Coupon 管理

创建：

```bash
python scripts/coupon_admin.py create --credits 20 --source xhs
```

批量创建：

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

## 文档

详细设计和接口文档见 `docs/`。
