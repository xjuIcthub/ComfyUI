# 部署计划索引

本目录记录 `comfy.icthub.top` 和 `login.icthub.top` 的部署方案与执行状态。

- [Pi 5 网页/API 中转 TODO](pi5-api-relay-todo.md)
- [Pi 5 网页/API 中转架构](pi5-api-relay-architecture.md)
- [Pi 5 部署实施清单](pi5-api-relay-rollout.md)
- [邀请码注册与 Authentik 身份系统计划](invite-registration-authentik.md)
- [H100 混合推理接入计划](h100-hybrid-integration.md)

当前状态：

- Pi 5 通过 Python venv 和根级 systemd 运行 CPU 版 ComfyUI。
- `comfy.icthub.top` 已通过 Cloudflare Tunnel 和 Access 提供受保护访问。
- 邀请码注册与 Authentik 身份系统的可部署实现已完成；SMTP 尚未准备，生产注册默认关闭并等待邮件、Cloudflare 和备份恢复验收。
- Pi 5 不承担本地模型推理，当前阶段不让 H100 参与计算。
- 不修改 ComfyUI 核心代码；第三方模型通过经过审核的自定义节点接入。
