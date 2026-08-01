# ComfyUI ICTHub Refactor

该目录集中存放现有 `xjuIcthub/ComfyUI` fork 的重构计划和迁移资源，不参与 ComfyUI runtime/import/package。

- [`plan.md`](./plan.md)：从“上游 fork + Pi 部署”拆分为 engine fork 与 React/FastAPI 控制台的完整步骤。
- [`resources/`](./resources/)：待迁出的非敏感页面快照、API 边界和资源说明。

原则：ComfyUI core 继续跟踪上游；身份、Cloudflare、Pi 产品部署、用户/配额/审计和品牌控制台迁出。任何删除都要等新仓库上线并完成回滚验收。
