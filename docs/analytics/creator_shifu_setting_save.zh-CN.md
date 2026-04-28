# creator_shifu_setting_save 事件说明

## 概述

`creator_shifu_setting_save` 是一个分析跟踪事件，用于记录内容创作者保存师傅（AI 助手/教师）配置设置时的行为。

## 用途

该事件用于：
1. **跟踪用户行为**：监控创作者如何与师傅设置进行交互和配置
2. **理解使用模式**：分析哪些设置最常被修改
3. **区分保存类型**：区分手动保存和自动保存
4. **监控参与度**：跟踪创作者在内容管理系统中的活动和功能使用情况

## 事件跟踪系统

该事件使用 **Umami** 进行跟踪，这是一个注重隐私的开源网站分析工具。跟踪实现：
- 使用 `umami.track()` JavaScript API
- 非阻塞（错误被静默捕获，以防止影响用户体验）
- 仅在 Umami 脚本加载时进行跟踪
- 为已认证用户包含用户识别和会话数据

## 事件触发时机

该事件在两种情况下触发：

### 1. 手动保存 (save_type: 'manual')
- 当用户显式关闭师傅设置对话框时
- 当用户通过点击保存按钮提交表单时
- 在用户操作后立即触发

### 2. 自动保存 (save_type: 'auto')
- 当表单已被修改时（isDirty = true）
- 在 3 秒无操作延迟后触发
- 提供自动持久化，无需用户显式操作
- 确保正在编辑的创作者不会丢失数据

## 收集的事件数据

事件载荷包含以下字段：

### 师傅配置数据
| 字段 | 类型 | 说明 |
|-----|------|-----|
| `description` | string | 师傅的描述文本 |
| `shifu_bid` | string | 师傅的业务标识符（唯一 ID）|
| `keywords` | string[] | 与师傅关联的关键词/标签数组 |
| `model` | string | LLM 模型名称（如 "gpt-4"、"deepseek-chat"）|
| `name` | string | 师傅的显示名称 |
| `price` | number | 访问师傅的价格（货币单位）|
| `avatar` | string | 师傅头像图片的 URL |
| `temperature` | number | LLM 温度设置（0-2，控制随机性）|
| `system_prompt` | string | 师傅个性的自定义系统提示词 |

### 跟踪元数据
| 字段 | 类型 | 说明 |
|-----|------|-----|
| `save_type` | 'auto' \| 'manual' | 保存操作类型 |
| `user_type` | string | 用户状态：'guest'（访客）、'user'（用户）或 'member'（会员）|
| `user_id` | number | 唯一用户标识符 |
| `device` | string | 设备类型：'H5'（移动端）或 'Web'（桌面端）|
| `timeStamp` | string | 事件触发时的本地时间戳 |

## 代码位置

- **事件触发**：`/src/cook-web/src/components/shifu-setting/ShifuSetting.tsx`（第 251 行）
- **跟踪钩子**：`/src/cook-web/src/c-common/hooks/useTracking.ts`
- **跟踪工具**：`/src/cook-web/src/c-common/tools/tracking.ts`
- **分析加载器**：`/src/cook-web/src/components/analytics/UmamiLoader.tsx`

## 实现细节

```typescript
// 在成功的 API 保存后触发事件
trackEvent('creator_shifu_setting_save', {
  ...payload,           // 所有师傅配置字段
  save_type: saveType,  // 'auto' 或 'manual'
});
```

## 相关事件

其他与创作者相关的跟踪事件包括：
- `creator_shifu_preview_click`：创作者预览其师傅时
- `creator_lesson_preview_click`：创作者预览课程时
- `creator_publish_click`：创作者开始发布时
- `creator_publish_confirm`：创作者确认发布时
- `creator_shifu_create_success`：创建新师傅成功时
- `creator_shifu_create_click`：创作者开始创建师傅时

## 隐私考虑

- 除了 user_id 外，不收集个人身份信息（PII）
- 用户识别使用内部系统 ID，而非邮箱或姓名
- 系统提示词可能包含敏感配置数据，但存储在经过身份验证的分析系统中
- Umami 设计为注重隐私并符合 GDPR 规范

## 分析用例

此事件数据可用于：
1. 识别创作者中流行的 LLM 模型
2. 分析师傅内容的典型价格点
3. 了解温度设置偏好
4. 监控自动保存与手动保存的模式
5. 跟踪创作者的参与度和活跃度
6. 识别哪些字段被最频繁修改
7. 检测潜在问题（例如，频繁保存可能表明 UI 问题）

## 配置

Umami 分析通过环境变量配置：
- `UMAMI_SCRIPT_SRC`：Umami 跟踪脚本的 URL
- `UMAMI_WEBSITE_ID`：Umami 的唯一网站标识符

这些通过 Cook Web 前端环境配置系统加载。
