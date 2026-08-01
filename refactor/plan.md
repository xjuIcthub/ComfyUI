# ComfyUI 直接复用执行计划

## 决策

保留 `xjuIcthub/ComfyUI` 作为唯一 ComfyUI 仓库和实际产品入口：

- 不创建 `comfy-console`；
- 不重命名为 `ComfyUI-engine`；
- 不新增 React 工作流 UI；
- 不新增 ComfyUI 产品 FastAPI BFF；
- `comfy.icthub.top` 继续直接进入原生 ComfyUI。

## 目标拓扑

```text
Cloudflare Access + Authentik
  -> Pi 5 ComfyUI CPU UI/API
       -> ICTHub remote-compute custom node
            -> Cisco VPN
            -> gpu-server
                 -> GPU worker / LTX-2
```

## R0：稳定当前仓库

- 保留上游 core、原生 frontend package 和 API。
- 记录官方 upstream、当前 fork patch 和 Pi 部署 commit。
- Pi 使用 `--cpu --listen 127.0.0.1 --port 8188`。
- 大模型、CUDA 和 GPU worker 不进入 Pi。

## R1：迁出认证资源

- `deploy/login-page`（含 login root redirect、注册和 `/studio`）迁入 `auth-login`。
- Authentik compose/blueprint/manage CLI/email/backup 进入身份运维边界。
- 当前非敏感快照保留在 `resources/auth-login-legacy/`。
- 新位置完成验收和回滚前不删除旧部署。

## R2：remote-compute custom node

建议目录：

```text
custom_nodes/icthub_remote_compute/
  nodes.py
  client.py
  contracts.py
  tests/
```

第一批节点：

- GPU capability/status；
- remote LTX text/image-to-video；
- remote job wait/cancel；
- remote artifact load/save。

节点调用 `gpu-server`，使用 artifact ID 和幂等 job ID，不传播服务器绝对路径，不把 service token 写入 workflow。

## R3：并发与事件

- 网络请求和长任务不能阻塞 ComfyUI aiohttp event loop。
- job 状态通过轮询或受控 SSE bridge 转换为节点执行状态。
- VPN/worker 断开后返回明确可操作错误。
- cancel_requested 与实际 cancelled 分离。
- workflow 重试使用同一 idempotency key，避免重复 GPU 执行。

## R4：工作流复用

- 直接复用 ComfyUI 官方 workflow JSON 和 LTX 模板。
- 建立团队支持的 workflow catalog 文档，而不是新做产品数据库。
- 固定 custom node、模型 profile 和参数兼容矩阵。
- 只暴露已配置能力，避免用户提交无法执行的模型。

## R5：部署与验收

- 保持现有 `comfy.icthub.top -> 127.0.0.1:8188`。
- 安装 custom node 的锁定 release。
- secret 由 `/etc/icthub/comfy-remote.env` 或 systemd credential 提供。
- 真实运行一个 LTX Fast I2V 和取消/失败场景。
- 验证 Pi reboot、VPN loss、gpu-server restart、artifact 回传。

## 已接受限制

原生 ComfyUI + Cloudflare Access 是共享可信工作台，不提供完整产品级租户隔离、配额、计费和审计。当前用户规模下先接受；未来确有需求时再增加薄插件/网关，不提前维护第二套产品。

## 完成门

- 原生 UI/API 无重复实现。
- Pi 只做 CPU 工作流和入口。
- GPU 调度只在 gpu-server。
- service token 不进入浏览器、workflow 或 Git。
- 认证资源从 core 生命周期逐步拆出。
- 上游同步不被产品前端重构阻塞。
