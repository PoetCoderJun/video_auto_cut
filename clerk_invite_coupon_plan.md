# Clerk 注册邀请码 + Coupon 额度设计文档（v1.1）

更新时间：2026-02-24
适用范围：`web_frontend`（Next.js） + `web_api`（FastAPI + SQLite）

## 1. 目标与范围

### 1.1 业务目标

1. 接入 Clerk 用户体系，支持邮箱 + 密码注册/登录。
2. 注册阶段提供邀请码选填项；填写且有效时可领取免费额度，不填也可正常使用基础流程。
3. 使用 Coupon 管理额度：
   1. 新用户默认赠送 20 次额度（按系统欢迎券发放）。
   2. 未来可手动发放/兑换 Coupon（例如 20 次/50 次）。
4. 用户每次进入 Step2（章节生成阶段）消耗 1 次额度。

### 1.2 明确不做（当前阶段）

1. 不接 Stripe、Apple Pay 等在线支付。
2. 不做复杂订阅（按月包、团队席位、阶梯计费）。
3. 不做多租户组织权限（先按单用户模型）。

### 1.3 本轮确认的简化扩展点（已定）

1. 仅在 Coupon 增加一个来源字段：`source_user_id`。
2. 含义：该 Coupon 来自于哪个用户 ID（可为空）。
3. 目标：保持 MVP 简单，同时保留最小增长归因能力。
4. 当前不新增复杂推广规则（邀请返利、层级奖励、反作弊等暂不做）。

## 2. 用户体验流程（目标态）

1. 用户进入 Landing Page。
2. 顶部显示登录/注册入口（Clerk）。
3. 页面主按钮为“开始创作/一键创作”。
4. 点击主按钮：
   1. 未登录：跳转登录/注册。
   2. 已登录：进入工作流（上传 -> Step1 -> Step2 -> Step3/4）。
5. 当用户从 Step1 确认进入 Step2 时，系统扣减 1 次额度。
6. 若额度不足，阻止进入 Step2，并提示输入 Coupon 兑换。

## 3. 核心业务规则

### 3.1 邀请码规则

1. 邀请码支持有效期、最大使用次数、启用/禁用状态。
2. 每个用户只能完成一次“邀请码激活”。
3. 注册成功的判定标准：
   1. Clerk 账号存在 + 已登录。
   2. 本地业务用户可选完成邀请码激活（激活后获得欢迎额度）。
4. 未激活邀请码用户：允许登录并可调用主流程 API；仅不享受邀请码赠送额度。

### 3.2 Coupon 与额度规则

1. Coupon 是“发放额度”的载体，不直接绑定支付。
2. 每个 Coupon 具备：
   1. 代码（唯一）。
   2. 额度值（如 20）。
   3. 有效期（可空）。
   4. 最大兑换次数。
   5. 每用户可兑换次数（默认 1）。
3. 新用户赠送额度通过系统券 `WELCOME20` 发放，记账方式与普通 Coupon 一致。
4. 额度消耗规则：`step2/run` 成功受理时扣 1 次。
5. 幂等要求：同一个 `job_id` 最多扣 1 次（防重复点击/重试重复扣费）。
6. Coupon 可选记录 `source_user_id`，供后续按来源用户做统计。

### 3.3 扣费时机（与你现有流程对齐）

当前前端流程是：
`confirmStep1 -> runStep2 -> 轮询等待 STEP2_READY`

因此扣费放在后端 `POST /jobs/{job_id}/step2/run` 最稳妥：

1. 在校验 `STEP1_CONFIRMED` 后执行“额度扣减 + 入队 step2”事务。
2. 若额度不足，直接返回业务错误，不入队。
3. 若前端重试同一个 `job_id`，依靠幂等键不重复扣。

## 4. 技术架构设计

## 4.1 鉴权模型（Clerk）

1. 前端用 Clerk 管理登录态。
2. 前端请求 `web_api` 时携带 Bearer Token。
3. 后端新增认证中间件：
   1. 校验 Clerk JWT（JWKS）。
   2. 提取 `clerk_user_id`、邮箱等身份信息。
   3. 注入请求上下文 `current_user`。
4. 所有业务接口默认要求登录（除健康检查、公开静态资源）。

## 4.2 数据归属模型

1. `jobs` 增加 `owner_user_id`（Clerk user id）。
2. 查询/操作 job 时必须校验归属（只能访问自己的 job）。
3. 后续若做团队协作，再扩展 owner 模型。

## 5. 数据库设计（SQLite）

在 `web_api/db.py` 初始化脚本基础上增加以下表：

### 5.1 用户与激活

1. `users`
   1. `user_id TEXT PRIMARY KEY`（Clerk user id）
   2. `email TEXT NOT NULL`
   3. `status TEXT NOT NULL`（`PENDING_INVITE` / `ACTIVE` / `DISABLED`）
   4. `invite_activated_at TEXT`
   5. `created_at TEXT NOT NULL`
   6. `updated_at TEXT NOT NULL`

### 5.2 邀请码

1. `invite_codes`
   1. `invite_id INTEGER PK`
   2. `code_hash TEXT UNIQUE NOT NULL`
   3. `max_uses INTEGER NOT NULL`
   4. `used_count INTEGER NOT NULL DEFAULT 0`
   5. `expires_at TEXT`
   6. `status TEXT NOT NULL`（`ACTIVE` / `DISABLED`）
   7. `created_at TEXT NOT NULL`

2. `invite_claims`
   1. `claim_id INTEGER PK`
   2. `invite_id INTEGER NOT NULL`
   3. `user_id TEXT NOT NULL`
   4. `claimed_at TEXT NOT NULL`
   5. 唯一索引：`UNIQUE(user_id)`（每个用户仅一次激活）

### 5.3 Coupon 与额度账本

1. `coupons`
   1. `coupon_id INTEGER PK`
   2. `code_hash TEXT UNIQUE NOT NULL`
   3. `credits INTEGER NOT NULL`
   4. `max_redemptions INTEGER`
   5. `redeemed_count INTEGER NOT NULL DEFAULT 0`
   6. `expires_at TEXT`
   7. `status TEXT NOT NULL`（`ACTIVE` / `DISABLED`）
   8. `created_at TEXT NOT NULL`
   9. `source_user_id TEXT`（可空，记录来源用户 ID）

2. `coupon_redemptions`
   1. `redemption_id INTEGER PK`
   2. `coupon_id INTEGER NOT NULL`
   3. `user_id TEXT NOT NULL`
   4. `credits INTEGER NOT NULL`
   5. `redeemed_at TEXT NOT NULL`
   6. 唯一索引：`UNIQUE(coupon_id, user_id)`（默认单用户一次）

3. `credit_ledger`
   1. `entry_id INTEGER PK`
   2. `user_id TEXT NOT NULL`
   3. `delta INTEGER NOT NULL`（加额度为正，扣额度为负）
   4. `reason TEXT NOT NULL`（`WELCOME_GRANT` / `COUPON_REDEEM` / `STEP2_CONSUME`）
   5. `job_id TEXT`
   6. `idempotency_key TEXT UNIQUE NOT NULL`
   7. `created_at TEXT NOT NULL`

4. `credit_wallets`
   1. `user_id TEXT PRIMARY KEY`
   2. `balance INTEGER NOT NULL DEFAULT 0`
   3. `updated_at TEXT NOT NULL`

### 5.4 现有表改造

1. `jobs` 增加字段：`owner_user_id TEXT NOT NULL`。
2. 新增索引：`idx_jobs_owner_updated(owner_user_id, updated_at)`。

## 6. API 设计（增量）

## 6.1 认证与用户

1. `GET /api/v1/me`
   1. 返回用户基础信息 + 激活状态 + 当前余额。

2. `POST /api/v1/auth/invite/activate`
   1. 登录态调用，提交邀请码。
   2. 成功后：
      1. `users.status -> ACTIVE`
      2. 记录 `invite_claims`
      3. 发放欢迎券 20 次（记入 `credit_ledger` + `credit_wallets`）

## 6.2 Coupon

1. `POST /api/v1/coupons/redeem`
   1. 参数：`code`
   2. 成功后增加余额并返回最新余额。

2. `GET /api/v1/credits`
   1. 返回 `balance` + 最近 N 条流水（可选）。

## 6.3 现有工作流接口改造

1. `POST /api/v1/jobs`
   1. 改为必须登录。
   2. 要求 `users.status=ACTIVE`。
   3. 创建 job 时写入 `owner_user_id`。

2. `GET /api/v1/jobs/{job_id}` 及其他 job 相关接口
   1. 增加 job owner 校验。

3. `POST /api/v1/jobs/{job_id}/step2/run`
   1. 执行扣费事务（`-1`）。
   2. 扣费成功才允许入队 step2。
   3. 余额不足返回 `INSUFFICIENT_CREDITS`。

## 6.4 新增错误码

1. `UNAUTHORIZED`（401）
2. `FORBIDDEN`（403）
3. `INVITE_CODE_INVALID`（422）
4. `INVITE_CODE_EXPIRED`（422）
5. `INVITE_CODE_EXHAUSTED`（422）
6. `COUPON_INVALID`（422）
7. `COUPON_ALREADY_REDEEMED`（409）
8. `INSUFFICIENT_CREDITS`（402 或 409，建议先用 409 以保持现有风格）

## 7. 前端改造（Next.js）

目标文件（当前仓库）：

1. `web_frontend/app/layout.tsx`
2. `web_frontend/app/page.tsx`
3. `web_frontend/components/job-workspace.tsx`
4. `web_frontend/lib/api.ts`

改造点：

1. 全局接入 Clerk Provider。
2. Landing 顶部展示登录/注册按钮与用户菜单。
3. “开始创作”按钮逻辑：
   1. 未登录跳转登录。
   2. 已登录直接创建 job 并进入流程。
   3. 若用户在注册时填写了邀请码，登录后自动尝试激活并更新额度显示。
4. 在 Step1 页面按钮旁展示“进入 Step2 将消耗 1 次额度”。
5. `runStep2` 返回额度不足时弹 Coupon 输入框，成功兑换后可重试。
6. 页面头部显示剩余额度（例如 `剩余 19 次`）。

## 8. 后端改造（FastAPI）

目标文件（当前仓库）：

1. `web_api/config.py`（新增 Clerk/JWKS 配置）
2. `web_api/db.py`（新增表结构）
3. `web_api/repository.py`（新增 users/invite/coupon/ledger 读写）
4. `web_api/api/routes.py`（新增 auth/coupon/credits 接口 + job 权限校验）
5. `web_api/errors.py`（新增错误码）
6. `web_api/services/` 下新增：
   1. `auth.py`
   2. `billing.py`

关键实现原则：

1. 所有扣费都经由后端执行，前端只做展示。
2. 扣费与 step2 入队必须同事务（至少逻辑原子，避免“扣费成功但未入队”）。
3. 所有发券/扣费都记录 `credit_ledger`，便于审计与补偿。

## 9. 幂等与并发

1. Step2 扣费幂等键：`step2:{job_id}`。
2. 欢迎券发放幂等键：`welcome:{user_id}`。
3. Coupon 兑换幂等依赖唯一索引 `UNIQUE(coupon_id, user_id)`。
4. 余额更新使用事务，先校验再扣减，失败回滚。

## 10. 运维与管理

当前阶段建议先用脚本管理（不做后台管理页面）：

1. `scripts/invite_admin.py`
   1. 创建邀请码
   2. 禁用邀请码
   3. 查询使用情况

2. `scripts/coupon_admin.py`
   1. 创建 Coupon
   2. 失效 Coupon
   3. 手动补偿发券（客服场景）
   4. 创建时支持 `--source-user-id` 参数（可选）

## 11. 上线计划（分阶段）

### Phase 1（最小闭环）

1. 接入 Clerk 登录。
2. 增加本地 `users` 与 `jobs.owner_user_id`。
3. 仅做邀请码激活 + 欢迎 20 次额度发放。
4. 在 `step2/run` 扣 1 次。

### Phase 2（运营可用）

1. Coupon 兑换接口。
2. 邀请码/Coupon 管理脚本。
3. 余额与流水页面。

### Phase 3（优化）

1. 失败补偿策略（自动返还或人工补偿流程）。
2. 更细颗粒的风控（IP 限制、异常兑换告警）。

## 12. 验收标准

1. 未登录用户无法创建 job。
2. 已登录用户可进入主流程；填写并激活邀请码后可获得欢迎免费额度。
3. 新激活用户自动获得 20 次额度。
4. 进入 Step2 成功受理后，余额稳定减少 1。
5. 同一 `job_id` 多次触发 `step2/run` 不重复扣费。
6. 余额不足时返回明确错误，并可兑换 Coupon 后继续。
7. 用户无法访问他人 job。

## 13. 开放决策（建议你确认）

1. 错误码是否新增 `402`，还是统一沿用 `409`。
2. Step2 失败是否自动返还额度（当前文档建议先不自动返还）。
3. 邀请码是否允许“一个码多人使用”，或一人一码。
4. 邀请码激活失败时是否要增加“稍后重试/更换邀请码”引导文案。

## 14. Landing Page 简洁 SEO 设计（MVP）

目标：页面保持简洁，同时满足基础 SEO 可见性与可转化性。

### 14.1 页面最小元素

1. 顶部导航：`产品价值`、`使用流程`、`登录/注册`。
2. Hero 区：
   1. 一个清晰 `H1`（包含核心词，如“AI 视频剪辑”）。
   2. 一句副标题（自动删废话、自动章节、快速导出）。
   3. 主按钮“开始创作”。
3. 三步流程：上传视频 -> 编辑字幕 -> 导出成片。
4. 核心能力区：3 到 4 个卡片（精简描述，不堆功能）。
5. FAQ 区：3 到 5 个高频问题。
6. 页脚：隐私政策、服务条款、联系方式。

### 14.2 SEO 必做项（简洁版）

1. 页面唯一 `title` 与 `meta description`。
2. 每页仅一个 `H1`，与页面主主题一致。
3. 首屏关键文案可被抓取（不要只放图片文案）。
4. 配置 `canonical`，避免重复页面权重分散。
5. 提供 `robots.txt` 与 `sitemap.xml`。
6. 图片有 `alt`，按钮文案语义明确。
7. 增加结构化数据：
   1. `SoftwareApplication`
   2. `FAQPage`（若页面存在 FAQ）
8. 增加社交分享标签：`og:title`、`og:description`、`og:image`、`twitter:card`。

### 14.3 文案关键词建议（MVP）

1. 主词：`AI 视频剪辑`、`自动剪辑视频`。
2. 场景词：`口播视频精简`、`自动生成章节`、`字幕驱动剪辑`。
3. 转化词：`开始创作`、`一键创作`、`在线导出`。

说明：先围绕 1 个主词 + 2 到 3 个场景词，不追求大而全覆盖。
