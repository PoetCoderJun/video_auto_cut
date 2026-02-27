# video_auto_cut

口播视频自动剪辑（Web + 本地流水线）。

## 本地开发启动

```bash
python -m pip install -r requirements.txt
cd web_frontend && npm install && cd ..
./scripts/start_web_mvp.sh
```

- Frontend: `http://127.0.0.1:3000`
- API: `http://127.0.0.1:8000/api/v1`

## 云端部署（Ubuntu 单机）

### 1) 一键安装依赖

```bash
./scripts/install_ubuntu.sh
```

### 2) 配置环境变量

```bash
cp .env.example .env
```

按你的线上域名/密钥填好 `.env`，至少要改：

- `BETTER_AUTH_SECRET`（生产必须非默认，且至少 32 位）
- `TURSO_DATABASE_URL` / `TURSO_AUTH_TOKEN`
- `ASR_DASHSCOPE_API_KEY`（或 `DASHSCOPE_API_KEY`）
- `OSS_ENDPOINT` / `OSS_BUCKET` / `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET`
- `NEXT_PUBLIC_SITE_URL` / `BETTER_AUTH_URL` / `WEB_CORS_ALLOWED_ORIGINS`

### 2.1 配置流程（推荐顺序）

1. 先生成高强度鉴权密钥（至少 32 位）  
`npx @better-auth/cli secret` 或 `openssl rand -base64 32`
2. 填数据库参数（`TURSO_DATABASE_URL`、`TURSO_AUTH_TOKEN`）
3. 填 ASR 参数（`ASR_DASHSCOPE_API_KEY` 或 `DASHSCOPE_API_KEY`）
4. 填 OSS 参数（`OSS_ENDPOINT`、`OSS_BUCKET`、`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`）；若前端直传 OSS，还需在阿里云控制台为该桶配置 **CORS**：来源填前端域名（如 `https://你的域名.com` 或 `http://localhost:3000`），允许方法包含 **PUT**，允许头包含 **Content-Type**（或填 `*`），否则浏览器直传会返回 403。
5. 填站点域名参数（`NEXT_PUBLIC_SITE_URL`、`BETTER_AUTH_URL`、`WEB_CORS_ALLOWED_ORIGINS`）
6. 仅单机测试时可先用 `http://127.0.0.1:3000`；正式上线改成 HTTPS 域名

### 2.2 配置完成后自检

```bash
# 检查关键变量是否都存在
grep -E '^(BETTER_AUTH_SECRET|TURSO_DATABASE_URL|TURSO_AUTH_TOKEN|ASR_DASHSCOPE_API_KEY|DASHSCOPE_API_KEY|OSS_ENDPOINT|OSS_BUCKET|OSS_ACCESS_KEY_ID|OSS_ACCESS_KEY_SECRET|NEXT_PUBLIC_SITE_URL|BETTER_AUTH_URL|WEB_CORS_ALLOWED_ORIGINS)=' .env
```

说明：

- 若你只填了 `DASHSCOPE_API_KEY`，也可正常跑 ASR（代码会自动回退）。
- `WEB_CORS_ALLOWED_ORIGINS` 可以写多个，用英文逗号分隔。
- 生产环境不要用 `127.0.0.1` 作为站点 URL。

### 3) 生产模式启动

```bash
./scripts/start_web_prod.sh
```

说明：

- `start_web_prod.sh` 会执行 `next build` + `next start`，并启动 FastAPI + worker。
- 若依赖缺失，会直接报错并提示先跑 `install_ubuntu.sh`。
- 生产模式下会强制检查 `BETTER_AUTH_SECRET`，避免误用开发默认密钥。
- 强校验规则：`BETTER_AUTH_SECRET` 不能为空、不能是默认值、长度至少 32。
- 若仅本地开发调试，可用 `start_web_mvp.sh`；若临时关闭鉴权可设 `WEB_AUTH_ENABLED=0`（不建议生产使用）。
- 当 `ASR_BACKEND=dashscope_filetrans` 时，Python 侧不需要 `torch/qwen-asr/ffmpeg-python`。
- 但系统层 `ffmpeg/ffprobe` 仍需保留（用于渲染与媒体探测）。

## systemd 托管（推荐线上）

模板文件在 `deploy/systemd/`，也提供一键安装脚本：

```bash
./scripts/install_systemd_services.sh
```

如需安装后立刻启动：

```bash
ENABLE_NOW=1 ./scripts/install_systemd_services.sh
```

手工方式如下：

- `video-auto-cut-api.service`
- `video-auto-cut-worker.service`
- `video-auto-cut-frontend.service`
- `video-auto-cut.env.example`

典型步骤：

```bash
sudo mkdir -p /etc/video-auto-cut
sudo cp deploy/systemd/video-auto-cut.env.example /etc/video-auto-cut/video-auto-cut.env
sudo cp deploy/systemd/video-auto-cut-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now video-auto-cut-api.service video-auto-cut-worker.service video-auto-cut-frontend.service
```

## Railway 部署（国外免备案）

Railway **不会读取你本地的 `.env` 文件**。必须在每个服务的 **Variables** 里逐条添加环境变量（项目 → 选中服务 → Variables 标签 → Add Variable），键名与 `.env` 中一致，值填你的真实配置。部署时 Railway 会把它们注入到容器里。

从 GitHub 连接仓库后，在同一项目下创建 **三个服务**，均从同一仓库部署，通过 **Root Directory** 和 **Start Command** 区分：

### 1) 服务 API

- **Root Directory**：留空（仓库根目录）
- **Dockerfile Path**：`Dockerfile`（根目录）
- **Start Command**：留空（使用 Dockerfile 默认：`uvicorn ... --port $PORT`）
- **Variables**：在 API 服务的 Variables 里添加以下变量（可对照本地 `.env` 或 `.env.example` 填写；`API_PORT`/`FRONTEND_PORT` 可不填，Railway 用 `PORT`）：
  - **必填**：`TURSO_DATABASE_URL`、`TURSO_AUTH_TOKEN`、`BETTER_AUTH_SECRET`（至少 32 位）、`ASR_DASHSCOPE_API_KEY` 或 `DASHSCOPE_API_KEY`、`OSS_ENDPOINT`、`OSS_BUCKET`、`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`
  - **URL**（填 Railway 生成后的真实域名）：`NEXT_PUBLIC_SITE_URL`、`BETTER_AUTH_URL`、`WEB_CORS_ALLOWED_ORIGINS` 填前端公网 URL（如 `https://xxx.up.railway.app`）；`NEXT_PUBLIC_API_BASE` 填 API 公网 URL（如 `https://yyy.up.railway.app/api/v1`）。首次可先占位，生成域名后改掉并 Redeploy。

### 2) 服务 Worker

- **Root Directory**：留空
- **Dockerfile Path**：`Dockerfile`（与 API 同一镜像）
- **Start Command**：`python -m web_api`
- **Variables**：与 API 完全一致（同一套 Turso、Auth、OSS、ASR 等），在 Worker 服务的 Variables 里再配一遍或使用 Railway 的 Shared Variables。

### 3) 服务 Frontend

- **Root Directory**：`web_frontend`
- **Dockerfile Path**：`Dockerfile`（即 `web_frontend/Dockerfile`）
- **Variables**：至少提供 `NEXT_PUBLIC_SITE_URL`、`NEXT_PUBLIC_API_BASE`（以及 Better Auth 相关），值为前端、API 的最终公网 URL；首次可占位，域名确定后改值并 **Redeploy** 以重新 build。

### 4) 服务间引用与 CORS

- API 的 `WEB_CORS_ALLOWED_ORIGINS` 必须包含前端的完整 origin（如 `https://your-frontend.up.railway.app`）。
- 前端的 `NEXT_PUBLIC_API_BASE` 必须指向 API 的 `/api/v1`（如 `https://your-api.up.railway.app/api/v1`）。

### 5) API+Worker 合并部署（推荐）

若将 API 与 Worker 合并为同一服务（共享 workdir），**Start Command** 必须：

1. 让 uvicorn 作为前台进程（否则 Railway 会 502）
2. **API 与 Worker 使用不同的 Turso 本地 replica 路径**，否则会冲突报 `wal_insert_begin failed`

```bash
sh -c "(TURSO_LOCAL_REPLICA_PATH=/app/workdir/replica_worker.db python -m web_api &) && exec env TURSO_LOCAL_REPLICA_PATH=/app/workdir/replica_api.db uvicorn web_api.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"
```

（Worker 用自己的 replica 文件，API 用另一个，二者都 sync 远程 Turso，互不锁文件。）

推送代码后，Railway 会按各自 Root Directory / Dockerfile / Start Command 自动构建并部署对应服务。

## 部署位置建议

- **Railway**：国外部署、免备案、自带 HTTPS，见上文「Railway 部署」。
- 阿里云 `ECS / 轻量应用服务器`：可直接部署（当前项目最匹配）。
- 阿里云 `ECI`：可部署，但需要你自己容器化和日志/持久化方案。
- `Vercel / EdgeOne`：只能放前端层，不能直接承载 Python API + worker + ffmpeg 链路。

## 单一 Coupon 码体系

只有一套码：`coupon code`。

- 前端文案可显示“邀请码”
- 实际兑换和校验是 coupon
- 线上来源是 Turso 的 `coupon_codes` 表

## 管理 Coupon（直接写线上库）

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
