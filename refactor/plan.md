# ComfyUI 控制台重构执行计划

## 仓库目标

现有仓库最终只保留：上游 ComfyUI engine、approved custom nodes 和不可避免的 GPU/模型兼容 patch。产品控制台使用独立 React + FastAPI 仓库。

## 决策门

推荐保留 `xjuIcthub/ComfyUI` 作为 fork，新建 `xjuIcthub/comfy-console`。如果产品仓库必须叫 `ComfyUI`，先在维护窗口将本 fork 重命名为 `ComfyUI-engine`，再创建新仓库。

## R0：基线

- 记录本地、origin、官方 upstream commit。
- 记录 Pi 当前部署 commit、service、ports、persistent directories。
- 核对本地与 origin 的 Authentik blueprint/test 一致性。
- 停止向 core 增加 ICTHub 产品代码。

## R1：资源抽取

迁出：

- `deploy/login-page`（含 `/studio` 入口）→ `auth-login`；
- `deploy/authentik` → identity operations；
- Cloudflare/Pi 主机配置 → platform operations；
- ICTHub plans → 新控制台/gpu-server docs。

当前非敏感页面快照已复制到 `resources/auth-login-legacy/`，用于回归；`login.icthub.top` 只允许精确根路径（固定 session-aware redirect）与 `/studio(/.*)?` 指向静态服务，其余路径保留 Authentik。不得把 tunnel credential、secret env 或机器私有日志复制到新仓库。

## R2：控制台 API

FastAPI 建立 user/workflow/version/job/artifact/quota/audit 模型，通过 service-authenticated API 调用 `gpu-server`。浏览器不访问 raw ComfyUI。

产品 API：submit/status/events/cancel/uploads/artifacts/workflows。内部 adapter 仅依赖受 contract test 固定的 `/prompt`、`/ws`、`/history`、upload、view、cancel，不依赖 `/internal/*`。

## R3：GPU engine

- `gpu-server` 启动私有 ComfyUI 进程并管理端口/健康/退出。
- 安装固定版本的 approved custom nodes/models。
- 只允许 workflow catalog 与 node/parameter allowlist。
- 执行输出上传 artifact service，不传播 engine 本地路径。

## R4：React 产品

复用 xju-feiyue token、56px shell、resizable panels 和可访问交互，构建 workflow/assets/queue/canvas/properties/logs。SSE/WebSocket 只连接 FastAPI。

## R5：灰度切换

- 新控制台并行域名/端口验收。
- `comfy.icthub.top` 切换到产品控制台。
- raw engine 仅 Cisco VPN/admin 可达。
- 原 Pi CPU ComfyUI 保留 7–14 天后下线。

## R6：清理 fork

- 删除已迁移 `deploy` 与平台计划，但保留指向新位置的迁移说明。
- 配置官方 upstream，同步策略和 patch inventory。
- 每次上游更新运行 engine adapter contract tests。

## 完成门

- 用户身份与 artifact 权限在产品层可验证。
- ComfyUI multi-user header 不作为可信身份。
- 浏览器无法调用 raw queue/history/interrupt。
- 上游升级与产品发布可独立进行。
- Pi 不再安装 CPU Torch/ComfyUI 执行环境。
