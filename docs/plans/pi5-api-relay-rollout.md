# Pi 5 部署实施清单

本文记录实施顺序和验收边界。每一阶段验收后再进入下一阶段。

## 阶段 0：冻结范围

- [x] 确认 Pi 5 只承担网页、工作流调度和第三方 API 中转。
- [x] 确认当前阶段不连接 H100。
- [x] 选定 ComfyUI 提交并记录提交号。
- [ ] 列出首批允许安装的自定义节点。
- [x] 确认 Cloudflare Access 的登录策略。
- [ ] 确认输出保留周期、磁盘上限和备份位置。

**停止条件：** API 节点来源或密钥保存方式没有确定时，不安装生产节点。

## 阶段 1：准备 Pi 5

1. 记录系统版本、ARM64 架构、内存、磁盘和服务管理方式。
2. 确认 8188、80、443 没有与现有服务冲突。
3. 建立独立源码、部署配置和持久化数据目录。
4. 为数据目录设置仅部署用户可写的权限。
5. 不安装 CUDA、NVIDIA Runtime 或 GPU 版 PyTorch。

当前目录：

```text
/home/winbeau/services/ComfyUI/          Git 源码和 Python venv
/home/winbeau/services/comfyui-deploy/  运行配置
/home/winbeau/services/comfyui-data/    持久化数据
```

**验收：** 源码来自 Git clone，数据目录不依赖临时文件系统。

## 阶段 2：准备 CPU 运行环境

1. 从固定提交准备源码，不使用浮动版本作为未验证的生产版本。
2. 使用 Python venv 隔离项目依赖。
3. 从 PyTorch 官方 CPU wheel 源安装 Torch、TorchVision 和 TorchAudio。
4. 安装 ComfyUI 原有依赖，不添加 CUDA、cuDNN、NCCL 或 Triton。
5. 验证 `torch.version.cuda` 为 `None`，设备为 `cpu`。

启动参数：

```text
--cpu --listen 127.0.0.1 --port 8188 --disable-auto-launch
```

**验收：** ComfyUI 能导入依赖并启动，`/system_stats` 返回 CPU 设备。

## 阶段 3：系统服务与本机验证

1. 将 `input`、`output`、`user`、`models` 和 `custom_nodes` 指向持久化目录。
2. 配置根级 systemd unit，进程以普通部署用户运行。
3. 启动后只从 Pi 5 本机检查 `/system_stats` 和首页。
4. 验证局域网地址不能直接访问 8188。
5. 重启服务，确认工作流和用户配置仍存在。

**验收：**

- `comfyui.service` 为 `active / enabled`；
- 只监听 `127.0.0.1:8188`；
- 返回 `2.13.0+cpu / cpu`；
- 空闲时没有模型加载和 GPU 任务。

## 阶段 4：Cloudflare 入口

1. 通过 Cloudflare 官方流程创建命名 Tunnel。
2. 将 Tunnel 凭据保存在 `/etc/cloudflared` 并限制文件权限。
3. 将 `comfy.icthub.top` 路由到 `http://127.0.0.1:8188`。
4. 在公开访问前启用 Cloudflare Access Self-hosted Application。
5. 验证未授权请求返回 Access `302`，而不是 ComfyUI `200`。
6. 确认 HTTP、WebSocket、上传和长任务连接均可用。
7. 保持路由器无 8188、80、443 入站端口转发。

**验收：**

- 未登录用户无法访问 ComfyUI；
- 已授权用户可以打开页面并收到实时队列更新；
- DNS 只指向 Cloudflare Tunnel；
- 停止 Tunnel 后，域名不可绕过 Cloudflare 直连 Pi 5。

## 阶段 5：品牌登录入口

1. 将 `deploy/login-page` 部署为仅本机监听的静态服务。
2. 将 `login.icthub.top` 路由到静态服务。
3. 品牌页不收集密码、验证码、API Key 或 Access Token。
4. “继续登录”只跳转到受 Access 保护的 `comfy.icthub.top`。
5. 验证桌面、移动端和安全返回路径。

## 阶段 6：安装首个 API 节点

1. 只安装阶段 0 批准的节点和固定版本。
2. 审核节点是否上传额外数据、写入哪些目录、如何记录日志。
3. 将依赖固化到明确的版本清单。
4. 通过本地环境文件或凭据文件注入 API Key。
5. 建立最小测试工作流，只提交一个低成本任务。
6. 验证提交、轮询、取消、失败提示、下载和保存结果。

**停止条件：** 节点要求把密钥放进工作流、存在未说明的数据上传、依赖无法固定，或失败后无限轮询时，不进入生产使用。

## 阶段 7：运维验收

- [ ] Pi 5 重启后 ComfyUI、品牌入口和 Tunnel 自动恢复。
- [ ] API Key 不出现在 Git、工作流和日志中。
- [ ] 输出目录有容量监控或清理任务。
- [ ] 持久化目录已完成一次备份和恢复。
- [ ] Git 更新可以回退到上一提交。
- [ ] 自定义节点更新需要人工审核，不自动跟随上游。
- [ ] Cloudflare Access 和供应商 API Key 都有撤销流程。

## 回滚

按由外到内的顺序回滚：

1. 禁用 `login.icthub.top` 和 `comfy.icthub.top` 的 Tunnel 路由；
2. 停止 Cloudflare Tunnel；
3. 停止品牌入口和 ComfyUI 服务；
4. 将 Git 工作树回退到上一已验证提交并恢复上一份配置；
5. 保留持久化目录，不在回滚时删除输入、输出和工作流；
6. 如果问题来自自定义节点，先移除该节点，再恢复服务。

## 变更记录模板

每次部署记录：

```text
日期：
ComfyUI 提交：
Python / PyTorch 版本：
自定义节点及版本：
配置变更：
验证结果：
回滚提交：
执行人：
```
