# video_auto_cut

口播视频自动剪辑（Web + 本地流水线），当前部署方式仅支持 Railway。

## 目录约定

- `web_frontend/`：Next.js 前端
- `web_api/`：FastAPI API + worker
- `video_auto_cut/`：剪辑与转写流水线
- `scripts/`：运维脚本（保留 Railway/本地开发相关）
- `docs/`：设计与接口文档

## 本地开发

```bash
python -m pip install -r requirements.txt
cd web_frontend && npm install && cd ..
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
- `ASR_DASHSCOPE_API_KEY`（或 `DASHSCOPE_API_KEY`）
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
