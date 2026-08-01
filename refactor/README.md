# ComfyUI ICTHub Refactor

该目录集中存放现有 `xjuIcthub/ComfyUI` 的简化重构计划和迁移资源，不参与 ComfyUI runtime/import/package。

- [`plan.md`](./plan.md)：直接复用原生 ComfyUI、Pi CPU 控制面与远程 GPU custom node 的实施步骤。
- [`resources/`](./resources/)：待迁出的非敏感认证页面快照与来源说明。

已确定不新建 `comfy-console`，不开发重复的 React/FastAPI 产品层。ComfyUI 原生 UI/API 继续服务 `comfy.icthub.top`；实验室算力通过 custom node 调用 `gpu-server`。
