# Resources

## `auth-login-legacy/`

从当前 `deploy/login-page/` 复制的非敏感快照，用于迁移到 `xjuIcthub/auth-login` 时进行视觉、安全 header、token 表单和回滚对照。

不要从该目录部署生产：

- 生产只允许 `login.icthub.top` 精确根路径的固定 redirect 与 `/studio(/.*)?` 到静态服务，其余 login path 必须直达 Authentik；
- `runtime-config.js` 默认关闭注册，但生产开关应来自 root 管理文件；
- `studio.html/studio.css` 与注册页是旧暗色实现，新仓库已改为统一 ICTHub token；
- 该快照不包含 Cloudflare/Authentik/SMTP secrets。

源文件仍以 `deploy/login-page/` 为当前线上基线，直到域名切换验收完成。
