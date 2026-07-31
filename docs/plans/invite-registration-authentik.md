# ICThub 邀请码注册计划

## 目标

为 `comfy.icthub.top` 增加 ICThub 自有账号体系，用户必须持有效邀请码才能注册。账号、密码、邮箱验证、找回密码和会话由独立身份服务管理；ComfyUI 不保存密码，也不实现注册逻辑。

目标体验：

```text
login.icthub.top
  |
  +--> 已有账号：登录
  |
  +--> 新用户：输入邀请码并注册
                    |
                    v
auth.icthub.top（ICThub 品牌身份页）
                    |
                    v
Cloudflare Access + OIDC Instant Auth
                    |
                    v
comfy.icthub.top
```

## 非目标

当前计划不包含：

- 在 ComfyUI 核心或前端中保存账号密码；
- 无邀请码的公开注册；
- 让 Cloudflare Access 充当密码数据库；
- 将 Authentik 管理后台直接公开给所有用户；
- 在工作流、Git、镜像或日志中保存 SMTP、OIDC、数据库密钥；
- 在本阶段接入 H100 或第三方模型 API 计费体系。

## 组件职责

### Authentik

推荐使用固定版本的 Authentik 作为身份提供方，负责：

- 邀请注册流程；
- 用户名、邮箱和密码；
- 安全密码哈希；
- 邮箱验证和找回密码；
- 用户组、禁用和会话；
- OIDC Provider；
- 登录、注册、错误和恢复页面的品牌化；
- 邀请创建、过期、核销和审计。

实施时使用该固定版本官方支持的最小服务组合，不在计划阶段假定旧版本依赖或兼容层。

### Cloudflare

Cloudflare 负责：

- DNS、TLS 和 Tunnel；
- WAF、机器人防护和登录接口限速；
- 保护 `comfy.icthub.top`；
- 通过 OIDC 信任 Authentik；
- 使用单一 Authentik IdP 和 Instant Auth，避免登录方式选择页；
- 将已认证用户身份传递给 Access 策略。

Cloudflare 不负责存储用户密码。

### ComfyUI

ComfyUI 继续只负责网页工作台、工作流执行和 API 节点。它只接收通过 Cloudflare Access 的已认证访问，不理解邀请码、用户密码、Authentik 用户 ID 或 OIDC Token。

## 域名与路由

建议使用：

```text
login.icthub.top       公共品牌入口
register.icthub.top    可选的品牌邀请码输入页
                       也可以合并到 login.icthub.top

auth.icthub.top        Authentik 登录、注册、邮箱验证和找回密码
comfy.icthub.top       Cloudflare Access 保护的 ComfyUI
auth-admin.icthub.top  身份系统管理入口
```

`auth.icthub.top` 不能使用依赖同一个 Authentik 的 Access 策略保护，否则会形成认证循环。它应通过 Tunnel、WAF、速率限制和 Authentik 自身认证保护。

`auth-admin.icthub.top` 使用独立管理员保护边界，例如现有 GitHub 管理员 IdP、固定管理账号加 MFA、IP/设备限制，不能依赖普通用户注册流。

## 邀请码模型

### 基本规则

- 默认邀请码一次性使用；
- 默认有效期 24 小时，可由管理员调整；
- 邀请码只用于注册，不可作为长期登录凭据；
- 核销成功后立即失效；
- 过期、撤销、已使用的邀请码统一返回不泄露内部状态的提示；
- 邀请码不得进入 Git、公开日志、分析工具或工作流；
- 管理员只通过 Authentik 管理界面或受控管理接口生成邀请；
- 不在前端 JavaScript 中实现邀请码真实性判断，最终验证必须由 Authentik 完成。

### 邀请绑定

邀请码至少绑定：

- 过期时间；
- 单次使用标志；
- 注册后目标用户组，例如 `comfy-users`；
- 创建管理员；
- 创建时间和核销时间；
- 可选的预绑定邮箱。

高价值或定向邀请建议绑定邮箱，避免邀请链接被转发后由其他人注册。

### 注册完成条件

用户只有满足以下条件才加入 `comfy-users`：

1. 邀请有效且未核销；
2. 用户名和邮箱满足规则；
3. 密码满足 Authentik 密码策略；
4. 邮箱验证完成；
5. 邀请核销成功。

Cloudflare Access 只允许包含 `comfy-users` 组声明的 OIDC 用户访问 ComfyUI。

## 用户流程

### 新用户注册

```text
打开品牌入口
  → 选择“邀请码注册”
  → 输入邀请码
  → Authentik 验证邀请
  → 填写用户名、邮箱和密码
  → 邮箱验证
  → 自动加入 comfy-users
  → OIDC 登录
  → Cloudflare Access 建立会话
  → 进入 ComfyUI
```

前端邀请码页面只负责收集并转交邀请码，不直接查询数据库。优先使用 Authentik 官方邀请 Enrollment Flow；如果需要独立品牌页，只做安全跳转和格式检查。

### 已有用户登录

```text
login.icthub.top
  → comfy.icthub.top
  → Cloudflare Access Instant Auth
  → Authentik 品牌登录页
  → ComfyUI
```

Access 会话有效时可直接进入 ComfyUI。Access 与 Authentik 会话期限统一采用已确认的 30 天策略；管理员入口使用更短会话并保留独立撤销能力。

### 找回密码

- 只通过已验证邮箱发起；
- 重置链接短时有效且一次性使用；
- 完成重置后撤销旧会话；
- 邮件和页面不泄露邮箱是否存在；
- 管理员不能查看用户明文密码。

## 品牌页面改造

当前 `deploy/login-page` 调整为两个主要动作：

- `登录工作台`：访问 `comfy.icthub.top`，由 Access Instant Auth 转到 Authentik；
- `邀请码注册`：进入 Authentik 邀请注册流或 `register.icthub.top`。

品牌页面继续遵守：

- 不保存密码和邀请码；
- 不调用 ComfyUI API 判断登录状态；
- 不嵌入 OIDC Client Secret；
- 不在本地存储中保存身份 Token；
- 不伪造或复制 Authentik 的认证表单。

Authentik 登录和注册页使用相同 Logo、颜色、文案和法律链接，保证从品牌入口到身份页视觉一致。

## 邮件与密钥

注册体系需要 SMTP 用于邮箱验证和密码重置。实施前确认邮件服务，并将凭据保存在根用户可控的部署环境文件中。

至少需要保护：

- 数据库密码；
- Authentik Secret Key；
- OIDC Client Secret；
- SMTP 凭据；
- Cloudflare Tunnel 凭据；
- 管理员恢复代码。

要求：

- 文件权限不高于 `0640`，目录不高于 `0750`；
- 不提交 Git；
- 不写入 Compose 文件、systemd unit、工作流或前端资源；
- 日志输出前脱敏；
- 每类凭据有单独轮换和撤销流程。

## 数据与备份

建议目录：

```text
/home/winbeau/services/authentik-deploy/  版本化部署配置，不含密钥
/home/winbeau/services/authentik-data/    数据库、媒体和自定义模板
/etc/icthub-auth/                         根级环境文件和凭据
```

必须备份：

- Authentik 数据库；
- 品牌模板和媒体；
- 流程、Provider、Application 和策略配置；
- 必要的加密密钥；
- 管理员恢复信息。

备份文件需要加密，并完成一次在隔离环境中的恢复演练。只有数据库而没有对应 Secret Key 的备份不视为可恢复备份。

## 安全控制

- 注册入口只允许邀请码流程，不显示普通公开注册入口；
- Cloudflare 对登录、注册、密码重置路径实施速率限制；
- 启用 Authentik 登录失败限制和会话撤销；
- 管理员账号强制 MFA；
- 普通用户 MFA 作为后续可选增强；
- OIDC Redirect URI 使用精确地址，不使用通配符；
- OIDC Client Secret 只保存在 Cloudflare 和 Authentik 服务端；
- Access 策略按 `comfy-users` 组放行，不使用 `Bypass`；
- 注册、登录和管理员操作保留必要审计记录；
- 不在审计日志中记录密码、完整邀请码或邮箱验证 Token；
- 管理入口与普通用户入口分离。

## 已确认策略与实现状态

策略已于 2026-07-31 确认：

- Authentik 固定为 `2026.5.5`，PostgreSQL 固定为 `16.11-alpine`；
- 邀请默认 24 小时、单次使用，并全部强制绑定指定邮箱；
- Access 与注册后的 Authentik 会话采用 30 天；
- 普通用户 MFA 可选；
- `auth-admin.icthub.top` 使用现有 GitHub IdP 独立保护，并要求 Authentik 管理员 MFA；
- SMTP 服务暂未准备，生产邀请码注册保持默认关闭。

仓库实现位于：

```text
deploy/authentik/    固定版本 Compose、Blueprint、品牌资源、邮件模板、运维与验收工具
deploy/login-page/   登录/注册品牌入口、安全静态服务、Tunnel 与 systemd 配置
```

SMTP 未准备属于生产上线阻塞项。当前可以部署 Authentik、完成本地初始化、管理员 MFA、Cloudflare OIDC 和备份恢复准备，但只有在 SMTP 投递、邮箱验证、找回密码和旧会话撤销全部验收后，才能通过根级运行配置开放注册。

## 七个实施任务

### Task 1：冻结身份系统版本和账号策略

- 固定 Authentik 版本；
- 确认用户名、邮箱和密码规则；
- 确认邀请码有效期、单次使用和邮箱绑定策略；
- 确认 Access 与 Authentik 会话期限；
- 确认 SMTP 服务。

**完成标准：** 账号与邀请策略不存在未决安全项。

### Task 2：部署身份服务

- 使用官方支持的固定版本部署 Authentik 及必要数据库组件；
- 服务只监听回环或隔离容器网络；
- 建立根级服务、持久化目录和健康检查；
- 验证重启恢复。

**完成标准：** `auth.icthub.top` 只能通过 Cloudflare Tunnel 到达。

### Task 3：配置品牌登录与恢复流程

- 配置 ICThub Logo、颜色和文案；
- 配置登录、邮箱验证、密码重置和错误页；
- 配置邮件模板；
- 配置管理员 MFA。

**完成标准：** 用户不会看到默认未品牌化身份页，恢复流程可用。

### Task 4：配置邀请码 Enrollment Flow

- 创建只接受有效邀请的注册 Flow；
- 邀请默认单次使用、24 小时过期；
- 注册完成后加入 `comfy-users`；
- 完成邮箱验证后才允许访问；
- 验证过期、重复使用、撤销和错误邮箱场景。

**完成标准：** 无邀请无法创建可访问 ComfyUI 的账号。

### Task 5：接入 Cloudflare Access OIDC

- 在 Authentik 创建 Cloudflare Access OIDC Provider；
- 在 Cloudflare 添加单一 Authentik Login Method；
- 启用 Instant Auth；
- Access Policy 只允许 `comfy-users`；
- 删除 One-time PIN 和所有 Bypass 策略；
- 验证登录、注销和会话过期。

**完成标准：** 用户只看到 ICThub 品牌身份页，未认证请求不能访问 ComfyUI。

### Task 6：更新品牌入口

- 增加“登录工作台”和“邀请码注册”入口；
- 注册入口转到 Authentik 邀请 Flow；
- 不在浏览器保存邀请码或身份 Token；
- 验证桌面和移动端；
- 验证安全返回路径。

**完成标准：** 品牌入口不承担认证，只负责安全导航。

### Task 7：生产验收与运维

- 演练邀请创建、核销、过期和撤销；
- 演练注册、邮箱验证、登录、注销和找回密码；
- 演练用户禁用和全会话撤销；
- 完成数据库与密钥备份恢复；
- 验证 Cloudflare 限速和 Access 组策略；
- 记录升级和回滚步骤。

**完成标准：** 身份、邀请、备份、撤销和回滚全部通过验收。

## 停止条件

出现以下任一情况时停止上线：

- 无邀请码可以进入注册 Flow；
- 邀请可被重复核销；
- 未验证邮箱可加入 `comfy-users`；
- Access 存在 `Bypass` 或只按邮箱域名宽泛放行；
- OIDC Client Secret、数据库密码或 SMTP 密钥进入 Git/日志；
- 管理员入口没有 MFA 或独立保护；
- 数据库备份无法配合 Secret Key 恢复；
- 密码重置会泄露账号是否存在；
- Authentik 不可用时 ComfyUI 仍能被未认证访问。

## 回滚

1. 停止发放新邀请；
2. 暂停 Authentik Enrollment Flow；
3. 保留 Cloudflare Access 对 ComfyUI 的保护；
4. 如 OIDC 故障，临时恢复仅管理员可用的原 GitHub IdP，不启用公开 Bypass；
5. 回退 Authentik 和数据库到上一已验证版本；
6. 恢复数据库、品牌模板和必要密钥；
7. 验证管理员登录后再恢复普通用户访问。

## 上线完成标准

- 只有有效邀请码能创建账号；
- 邀请默认一次性且有明确过期时间；
- 用户完成邮箱验证后才进入 `comfy-users`；
- `comfy.icthub.top` 只接受 Authentik OIDC 身份并启用 Instant Auth；
- 登录、注册和找回密码页面保持 ICThub 品牌；
- ComfyUI 不保存密码、邀请码和 OIDC Secret；
- 管理员入口强制 MFA；
- 备份恢复、邀请撤销、用户禁用和会话撤销均经过演练。

## 上线前剩余阻塞项

1. 选择 SMTP 服务并验证 `icthub.top` 发件域名；
2. 完成一封实际测试邮件的投递与收件确认；
3. 验证邮箱验证和找回密码邮件模板；
4. 验证密码重置不泄露账号存在性，并撤销旧会话；
5. 完成 Cloudflare Access、WAF 限速和 OIDC 组声明的生产验收；
6. 完成一次隔离环境中的加密备份恢复演练。

其余策略已经冻结：邀请 24 小时且单次使用、全部绑定邮箱、30 天会话、普通用户 MFA 可选、管理员使用现有 GitHub IdP 边界并在 Authentik 强制 MFA。
