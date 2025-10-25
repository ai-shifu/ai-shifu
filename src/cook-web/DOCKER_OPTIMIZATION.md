# Cook Web Docker 镜像优化指南

## 优化措施

### 1. 启用 Next.js Standalone 模式

- 在 `next.config.ts` 中添加 `output: 'standalone'`
- 这会生成一个包含所有依赖的独立服务器文件
- 显著减少运行时镜像的依赖需求

### 2. 多阶段构建优化

- **deps 阶段**: 仅安装生产依赖
- **builder 阶段**: 构建应用程序
- **runner 阶段**: 最小化运行时镜像

### 3. 基础镜像选择

- 使用 `node:20.11.1-alpine` 作为基础镜像
- Alpine Linux 比标准 Ubuntu/Debian 镜像小很多

### 4. 依赖优化

- 构建阶段只安装生产依赖 (`npm ci --only=production`)
- 清理 npm 缓存
- 使用 `--frozen-lockfile` 确保依赖一致性

### 5. 文件排除优化

- 更新 `.dockerignore` 排除更多不必要的文件
- 排除测试文件、文档、配置文件等
- 减少构建上下文大小

### 6. 安全优化

- 创建非 root 用户运行应用
- 使用 `--chown` 确保文件权限正确

## 使用方法

### 构建优化镜像

```bash
# 使用优化版本 Dockerfile
docker build -f Dockerfile.optimized -t cook-web:optimized .

# 或使用构建脚本
./build-optimized.sh
```

### 预期效果

- 镜像大小减少 60-80%
- 构建时间可能略有增加（由于多阶段构建）
- 运行时性能基本不变
- 安全性提升（非 root 用户）

## 文件说明

- `Dockerfile`: 原始 Dockerfile（已优化）
- `Dockerfile.optimized`: 进一步优化的版本
- `build-optimized.sh`: 构建脚本
- `.dockerignore`: 更新的排除文件列表

## 注意事项

1. **Standalone 模式要求**: 确保 Next.js 应用支持 standalone 输出
2. **依赖检查**: 某些动态导入的模块可能需要额外配置
3. **静态资源**: 确保所有静态资源正确复制到最终镜像
4. **环境变量**: 生产环境变量需要在运行时正确设置

## 进一步优化建议

1. **使用 distroless 镜像**: 考虑使用 Google 的 distroless 镜像
2. **依赖分析**: 使用工具分析并移除未使用的依赖
3. **压缩优化**: 启用 gzip 压缩减少传输大小
4. **CDN 集成**: 将静态资源移至 CDN
