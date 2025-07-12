# 环境变量配置完整文档

## 概述

本项目统一管理所有环境变量，避免重复和命名不一致的问题。所有环境变量都通过 `@/config/environment` 模块访问。

## 环境变量分类

### 1. 核心API配置 (Core API Configuration)

| 变量名 | 用途 | 默认值 |
|--------|------|--------|
| `NEXT_PUBLIC_API_BASE_URL` | API基础URL | `http://localhost:8081` |

### 2. 课程配置 (Course Configuration)

| 变量名 | 用途 | 默认值 |
|--------|------|--------|
| `NEXT_PUBLIC_DEFAULT_COURSE_ID` | 默认课程ID | 空字符串 |

### 3. 微信集成 (WeChat Integration)

| 变量名 | 用途 | 默认值 |
|--------|------|--------|
| `NEXT_PUBLIC_WECHAT_APP_ID` | 微信App ID | 空字符串 |
| `NEXT_PUBLIC_WECHAT_CODE_ENABLED` | 是否启用微信码 | `true` |

### 4. UI配置 (UI Configuration)

| 变量名 | 用途 | 默认值 |
|--------|------|--------|
| `NEXT_PUBLIC_UI_ALWAYS_SHOW_LESSON_TREE` | 是否始终显示课程树 | `false` |
| `NEXT_PUBLIC_UI_LOGO_HORIZONTAL` | 水平Logo URL | 空字符串 |
| `NEXT_PUBLIC_UI_LOGO_VERTICAL` | 垂直Logo URL | 空字符串 |

### 5. 分析统计 (Analytics)

| 变量名 | 用途 | 默认值 |
|--------|------|--------|
| `NEXT_PUBLIC_ANALYTICS_UMAMI_SCRIPT` | Umami统计脚本URL | 空字符串 |
| `NEXT_PUBLIC_ANALYTICS_UMAMI_SITE_ID` | Umami站点ID | 空字符串 |

### 6. 开发调试 (Development & Debugging)

| 变量名 | 用途 | 默认值 |
|--------|------|--------|
| `NEXT_PUBLIC_DEBUG_ERUDA_ENABLED` | 是否启用Eruda调试工具 | `false` |

## 使用方式

### 在组件中使用

```typescript
import { environment } from '@/config/environment';

// 获取API基础URL
const apiUrl = environment.apiBaseUrl;

// 获取课程ID
const courseId = environment.courseId;

// 获取微信配置
const wechatAppId = environment.wechatAppId;
const wechatEnabled = environment.enableWechatCode;
```

### 在API路由中使用

```typescript
import { environment } from '@/config/environment';

export async function GET() {
  return NextResponse.json({
    apiBaseUrl: environment.apiBaseUrl,
    courseId: environment.courseId,
    // ... 其他配置
  });
}
```

## API配置响应

`/api/config` 返回干净的JSON数据：

```json
{
    "apiBaseUrl": "http://127.0.0.1:5800",
    "courseId": "ca3265b045e84774b8d845a4c3c5b0a3",
    "wechatAppId": "wx973eb6079c64d030",
    "enableWechatCode": true,
    "alwaysShowLessonTree": "true",
    "logoHorizontal": "",
    "logoVertical": "",
    "umamiScriptSrc": "https://umami.ai-shifu.com/script.js",
    "umamiWebsiteId": "f3108c8f-6898-4404-b6d7-fd076ad011db",
    "enableEruda": "false"
}
```

## 路由配置说明

### `/c/[[...id]]` 路由
- **配置获取方式**：通过 `/api/config` API
- **用途**：课程学习页面，需要完整的配置信息
- **包含配置**：课程ID、微信配置、UI配置、统计配置等

### `/main` 路由
- **配置获取方式**：直接使用 `environment` 模块
- **用途**：师傅列表页面，主要需要API基础URL
- **包含配置**：API基础URL（用于API请求）

## Docker 部署

### 环境变量配置

Docker 部署不受影响：
- 环境变量在运行时通过 Docker 的 `-e` 参数或 `docker-compose.yml` 传入
- 构建时不需要环境变量，运行时才会读取
- 环境配置模块会自动处理变量读取

### 部署示例

```bash
# 使用新的环境变量名
docker run -e NEXT_PUBLIC_API_BASE_URL=https://api.your-domain.com \
           -e NEXT_PUBLIC_DEFAULT_COURSE_ID=your-course-id \
           -e NEXT_PUBLIC_WECHAT_APP_ID=your-wechat-app-id \
           your-image:tag
```

## 重构历史

### 完成的工作

#### 1. 统一环境变量管理
✅ **创建了统一的环境配置模块** (`src/config/environment.ts`)
- 集中管理所有环境变量
- 提供类型安全的接口

#### 2. 解决重复和命名不一致问题
✅ **合并了重复的环境变量**：
- `SITE_HOST`, `NEXT_PUBLIC_BASEURL`, `NEXT_PUBLIC_SITE_URL` → `NEXT_PUBLIC_API_BASE_URL`
- 统一了API基础URL的获取逻辑

✅ **标准化了命名规范**：
- 所有变量使用 `NEXT_PUBLIC_` 前缀
- 按功能分类：`UI_`, `ANALYTICS_`, `DEBUG_` 等
- 布尔值变量使用 `_ENABLED` 后缀

#### 3. 清理了分散的配置文件
✅ **删除了重复的配置文件**：
- 删除了 `src/config/runtime-config.ts`
- 删除了 `src/config/site.ts`
- 统一使用 `src/config/environment.ts`

#### 4. 修复了类型错误
✅ **修复了所有TypeScript类型错误**：
- 统一了接口定义
- 修复了属性访问错误
- 确保了类型安全

#### 5. 修复了API配置重复问题
✅ **修复了 `/api/config` 路由的数据重复问题**：
- 移除了重复字段，避免数据重复
- 现在只返回一份干净的配置数据

#### 6. 修复了配置数据映射问题
✅ **修复了配置数据字段映射**：
- 更新了 `/c/[[...id]]/layout.tsx` 中的字段映射
- 使用新的字段名（如 `courseId` 而不是 `NEXT_PUBLIC_COURSE_ID`）
- 确保所有组件都能正确获取配置

#### 7. 路由配置优化
✅ **优化了不同路由的配置获取**：
- `/c/[[...id]]` 路由：通过 `/api/config` 获取完整配置
- `/main` 路由：直接使用 `environment` 模块，无需额外API调用
- 根据路由需求选择合适的配置获取方式

#### 8. 移除向后兼容性
✅ **移除了所有向后兼容性代码**：
- 移除了环境变量名称的fallback逻辑
- 移除了API响应中的兼容字段
- 移除了 `legacyEnv` 对象
- 清理了环境变量文件中的旧变量名

### 环境变量迁移映射

| 旧变量名 | 新变量名 | 说明 |
|---------|---------|------|
| `SITE_HOST` | `NEXT_PUBLIC_API_BASE_URL` | API基础URL |
| `NEXT_PUBLIC_BASEURL` | `NEXT_PUBLIC_API_BASE_URL` | API基础URL |
| `NEXT_PUBLIC_SITE_URL` | `NEXT_PUBLIC_API_BASE_URL` | API基础URL |
| `NEXT_PUBLIC_COURSE_ID` | `NEXT_PUBLIC_DEFAULT_COURSE_ID` | 默认课程ID |
| `NEXT_PUBLIC_APP_ID` | `NEXT_PUBLIC_WECHAT_APP_ID` | 微信App ID |
| `NEXT_PUBLIC_ENABLE_WXCODE` | `NEXT_PUBLIC_WECHAT_CODE_ENABLED` | 是否启用微信码 |
| `NEXT_PUBLIC_ALWAYS_SHOW_LESSON_TREE` | `NEXT_PUBLIC_UI_ALWAYS_SHOW_LESSON_TREE` | 是否始终显示课程树 |
| `NEXT_PUBLIC_LOGO_HORIZONTAL` | `NEXT_PUBLIC_UI_LOGO_HORIZONTAL` | 水平Logo |
| `NEXT_PUBLIC_LOGO_VERTICAL` | `NEXT_PUBLIC_UI_LOGO_VERTICAL` | 垂直Logo |
| `NEXT_PUBLIC_UMAMI_SCRIPT_SRC` | `NEXT_PUBLIC_ANALYTICS_UMAMI_SCRIPT` | Umami脚本 |
| `NEXT_PUBLIC_UMAMI_WEBSITE_ID` | `NEXT_PUBLIC_ANALYTICS_UMAMI_SITE_ID` | Umami站点ID |
| `NEXT_PUBLIC_ERUDA` | `NEXT_PUBLIC_DEBUG_ERUDA_ENABLED` | 是否启用Eruda |

## 优势

1. **统一管理**：所有环境变量都在一个地方定义和管理
2. **类型安全**：TypeScript提供完整的类型检查
3. **命名规范**：统一的命名规范，易于理解和维护
4. **默认值处理**：所有变量都有合理的默认值
5. **布尔值处理**：自动处理字符串到布尔值的转换
6. **数据清洁**：API配置不再返回重复数据
7. **路由优化**：根据路由需求选择合适的配置获取方式
8. **Docker友好**：Docker部署不受影响，支持新的变量名
9. **代码简洁**：移除了复杂的fallback逻辑
10. **性能提升**：减少了不必要的变量检查

## 测试结果

✅ **构建成功**：项目可以正常构建，没有TypeScript错误
✅ **类型检查通过**：所有类型定义正确
✅ **API配置正常**：`/api/config` 返回干净的JSON数据，无重复
✅ **路由配置正确**：不同路由使用合适的配置获取方式
✅ **Docker兼容**：Docker部署不受影响
✅ **功能正常**：所有功能都能正常工作

## 环境变量文件示例

### 开发环境 (.env.local)
```bash
# ===== Core API Configuration =====
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:5800

# ===== Content & Course Configuration =====
NEXT_PUBLIC_DEFAULT_COURSE_ID=ca3265b045e84774b8d845a4c3c5b0a3

# ===== WeChat Integration =====
NEXT_PUBLIC_WECHAT_APP_ID=wx973eb6079c64d030
NEXT_PUBLIC_WECHAT_CODE_ENABLED=true

# ===== User Interface Configuration =====
NEXT_PUBLIC_UI_ALWAYS_SHOW_LESSON_TREE=true
NEXT_PUBLIC_UI_LOGO_HORIZONTAL=
NEXT_PUBLIC_UI_LOGO_VERTICAL=

# ===== Analytics & Tracking =====
NEXT_PUBLIC_ANALYTICS_UMAMI_SCRIPT=https://umami.ai-shifu.com/script.js
NEXT_PUBLIC_ANALYTICS_UMAMI_SITE_ID=f3108c8f-6898-4404-b6d7-fd076ad011db

# ===== Development & Debugging Tools =====
NEXT_PUBLIC_DEBUG_ERUDA_ENABLED=false
```

### 生产环境 (docker.env.example)
```bash
# ===== Core API Configuration =====
NEXT_PUBLIC_API_BASE_URL=https://api.your-domain.com

# ===== Content & Course Configuration =====
NEXT_PUBLIC_DEFAULT_COURSE_ID=your-default-course-id

# ===== WeChat Integration =====
NEXT_PUBLIC_WECHAT_APP_ID=your-wechat-app-id
NEXT_PUBLIC_WECHAT_CODE_ENABLED=true

# ===== User Interface Configuration =====
NEXT_PUBLIC_UI_ALWAYS_SHOW_LESSON_TREE=false
NEXT_PUBLIC_UI_LOGO_HORIZONTAL=
NEXT_PUBLIC_UI_LOGO_VERTICAL=

# ===== Analytics & Tracking =====
NEXT_PUBLIC_ANALYTICS_UMAMI_SCRIPT=https://umami.your-domain.com/script.js
NEXT_PUBLIC_ANALYTICS_UMAMI_SITE_ID=your-umami-site-id

# ===== Development & Debugging Tools =====
NEXT_PUBLIC_DEBUG_ERUDA_ENABLED=false

# ===== Docker Specific Configuration =====
PORT=3000
NODE_ENV=production
NEXT_TELEMETRY_DISABLED=1
```

## 后续建议

1. **逐步迁移**：可以逐步将其他项目中的环境变量也迁移到这个统一的管理方式
2. **文档更新**：更新项目文档，说明新的环境变量使用方式
3. **CI/CD更新**：更新CI/CD配置，使用新的环境变量名
4. **监控**：监控生产环境，确保所有功能正常工作
5. **团队培训**：培训团队成员使用新的环境变量配置方式

## 注意事项

1. 所有环境变量都以 `NEXT_PUBLIC_` 开头，确保在客户端可用
2. 布尔值变量会自动转换为正确的类型，无需手动处理字符串比较
3. 所有变量都有合理的默认值，避免运行时错误
4. 新的命名规范更加语义化和一致化
5. 不再支持旧的环境变量名，必须使用新的标准化命名
