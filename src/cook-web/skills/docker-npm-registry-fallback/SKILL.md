---
name: docker-npm-registry-fallback
description: 当 cook-web Docker 构建受镜像源同步延迟影响（尤其预发布版本）时使用本技能。通过可配置 registry 保证多阶段安装一致可用。
---

# Docker npm 源兜底

## 核心规则

- 构建中显式使用 `https://registry.npmjs.org/` 作为默认 npm 源。
- `builder` 与 `runner` 阶段都要可配置 `NPM_REGISTRY` 并执行 `npm config set registry`。

## 工作流

1. 在 Dockerfile 两个阶段声明 `ARG NPM_REGISTRY`。
2. 阶段内统一执行 `npm config set registry ${NPM_REGISTRY}`。
3. 安装预发布依赖时验证不再受镜像延迟导致 404。
4. 在 CI 与本地构建场景都做一次冒烟构建。
