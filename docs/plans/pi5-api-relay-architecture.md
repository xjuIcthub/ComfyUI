# Pi 5 网页/API 中转架构

## 目标

在 Raspberry Pi 5 上运行 CPU 版 ComfyUI，使用 `comfy.icthub.top` 提供网页工作台和后端 API。工作流中的生成任务由第三方模型 API 完成，Pi 5 只负责：

- 提供 ComfyUI 前端和工作流执行后端；
- 提交第三方 API 任务并轮询状态；
- 下载、保存和返回生成结果；
- 保存工作流、输入、输出和用户配置。

## 非目标

当前阶段不包含：

- 在 Pi 5 上加载或推理 Flux、LTX 等本地模型；
- 让 H100 自动承担 ComfyUI 的本地节点计算；
- 将 H100 直接暴露到公网；
- 修改 ComfyUI 核心代码来实现第三方网络请求；
- 未经审核批量安装自定义节点。

## 拓扑

```text
浏览器
  |
  v
login.icthub.top 品牌入口
  |
  v
Cloudflare Access + Cloudflare Tunnel
  |
  v
Pi 5: ComfyUI CPU 后端（仅本机监听）
  |                         |
  |                         +--> 本地持久化目录
  |
  +--> 经过审核的第三方 API 自定义节点
            |
            v
       Kling / Runway / 其他供应商 API
```

未来的 H100 接入是独立边界：

```text
Pi 5 上的远程推理节点
  |
  | 私网、鉴权、明确的任务协议
  v
H100 模型服务
```

## 部署决策

### 运行方式

- 使用 Python venv 运行 ARM64 CPU 版 ComfyUI。
- PyTorch、TorchVision 和 TorchAudio 使用官方 CPU wheel，不安装 CUDA 运行时。
- 启动参数包含 `--cpu`，ComfyUI 只监听 `127.0.0.1:8188`。
- 使用根级 systemd unit 管理服务，但进程以普通部署用户运行。
- 源码固定到明确提交，首次部署使用 `git clone`，后续更新使用 `git pull --ff-only`。

### 公网入口

- 使用 Cloudflare Tunnel，不在路由器上开放 8188、80 或 443 端口。
- `login.icthub.top` 提供不处理凭据的品牌入口，登录按钮跳转到 `comfy.icthub.top`。
- `comfy.icthub.top` 只指向 Tunnel，并在入口前启用 Cloudflare Access。
- 未授权请求必须跳转到 Access 登录页，不能直接返回 ComfyUI。
- WebSocket 必须通过入口正常转发，否则队列进度和实时状态会失效。

### 持久化

至少持久化以下目录：

- `input/`
- `output/`
- `user/`
- `custom_nodes/`
- `models/`，当前预计为空，但保留标准目录结构

临时目录可以清理，不纳入长期备份。输出目录需要设置容量告警或定期清理策略。

### API 节点与密钥

- 第三方 API 功能由自定义节点提供，不放进 ComfyUI 核心层。
- 每个自定义节点在安装前检查来源、维护状态、许可证和依赖。
- API Key 不写入工作流 JSON、镜像、Git 或公开日志。
- 优先通过仅宿主机可读的环境文件或节点支持的凭据文件注入。
- 不同供应商使用不同密钥，便于单独撤销和限额。

## 资源预期

Pi 5 不做模型推理时，主要资源消耗来自 Python 后端、前端连接、自定义节点、文件下载和媒体处理。即使使用 `--cpu`，ComfyUI 仍需要 CPU 版 PyTorch 和项目依赖，但不需要 CUDA、NVIDIA Runtime 或 H100 驱动。

大文件下载、视频合成和解码仍可能占用较多 CPU、内存和磁盘 IO，因此 API 节点需要限制并发、单任务文件大小和超时时间。

## 安全边界

ComfyUI 默认假设能访问 URL 的用户是可信用户。公网部署必须额外提供：

- Cloudflare Access 身份验证；
- Tunnel 入口，避免直接暴露宿主端口；
- 受控的自定义节点清单；
- 密钥隔离和日志脱敏；
- 输入、输出目录的容量限制与备份；
- 定期更新 Python 运行环境和依赖，但每次更新先在固定版本上验证。

## 待确认事项

执行前需要明确：

1. 首批第三方 API 供应商及对应自定义节点；
2. Cloudflare Access 允许的账号或身份域；
3. API 密钥使用环境变量还是供应商节点的本地凭据文件；
4. 输出文件保留周期和备份位置；
5. 是否允许用户通过网页安装或更新自定义节点，默认建议不允许。

## 完成标准

- `comfy.icthub.top` 只能通过 Cloudflare Access 访问；
- Pi 5 上没有对局域网或公网直接暴露 8188；
- ComfyUI 重启后工作流和输出仍保留；
- 一个不依赖模型的基础工作流可以执行；
- 一个指定供应商的 API 工作流可以提交、轮询并保存结果；
- Pi 5 上没有加载本地模型，H100 没有收到任务；
- 备份、升级和回滚路径经过一次演练。
