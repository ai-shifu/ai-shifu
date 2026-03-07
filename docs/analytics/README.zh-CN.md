# 分析事件文档

本目录包含 AI-Shifu 平台中跟踪的分析事件的文档。

## 概述

AI-Shifu 使用 [Umami](https://umami.is/)（一个注重隐私的开源网站分析工具）来跟踪用户交互并理解使用模式。所有跟踪都设计为：

- **注重隐私**：不收集个人身份信息（PII）
- **非阻塞**：跟踪错误不影响用户体验
- **可选**：仅在加载分析脚本时跟踪
- **符合 GDPR**：遵循隐私法规

## 事件类别

### 创作者事件
与内容创作和管理相关的事件：

- **[creator_shifu_setting_save](./creator_shifu_setting_save.zh-CN.md)** - 创作者保存师傅配置设置时
- `creator_shifu_preview_click` - 创作者预览其师傅时
- `creator_lesson_preview_click` - 创作者预览课程时
- `creator_publish_click` - 创作者开始发布内容时
- `creator_publish_confirm` - 创作者确认发布操作时
- `creator_shifu_create_success` - 成功创建新师傅时
- `creator_shifu_create_click` - 创作者开始创建师傅时

### 学习者事件
与学习体验相关的事件：

- `learner_login_success` - 学习者成功登录时
- `learner_lesson_start` - 学习者开始课程时
- `trial_progress` - 试用课程的进度

### 导航事件
与 UI 导航相关的事件：

- `nav_bottom_beian` - 底部导航备案链接点击
- `nav_bottom_skin` - 主题/皮肤切换器交互
- `nav_bottom_setting` - 设置导航
- `nav_top_logo` - 顶部 logo 点击
- `nav_top_expand` - 导航展开操作
- `nav_top_collapse` - 导航折叠操作
- `nav_section_switch` - 章节导航切换

### 其他事件
- `visit` - 页面访问跟踪
- `pop_pay` - 支付模态框显示
- `pop_login` - 登录模态框显示
- `pay_succeed` - 支付成功
- `reset_chapter` - 章节重置操作
- `reset_chapter_confirm` - 章节重置确认
- `user_menu` - 用户菜单交互
- `user_menu_basic_info` - 基本信息菜单访问
- `user_menu_personalized` - 个性化设置访问

## 实现

### 核心文件

- **跟踪钩子**：`/src/cook-web/src/c-common/hooks/useTracking.ts`
- **跟踪工具**：`/src/cook-web/src/c-common/tools/tracking.ts`
- **分析加载器**：`/src/cook-web/src/components/analytics/UmamiLoader.tsx`

### 使用示例

```typescript
import { useTracking } from '@/c-common/hooks/useTracking';

function MyComponent() {
  const { trackEvent } = useTracking();
  
  const handleSave = async () => {
    // 你的保存逻辑
    await saveData();
    
    // 跟踪事件
    trackEvent('my_event_name', {
      // 事件数据
      field1: 'value1',
      field2: 'value2',
    });
  };
}
```

## 事件数据结构

所有事件自动包含以下元数据：

| 字段 | 说明 |
|-----|------|
| `user_type` | 用户状态：'guest'（访客）、'user'（用户）或 'member'（会员）|
| `user_id` | 唯一用户标识符（访客为 0）|
| `device` | 设备类型：'H5'（移动端）或 'Web'（桌面端）|
| `timeStamp` | 事件触发时的本地时间戳 |

## 配置

分析通过环境变量配置：

```bash
UMAMI_SCRIPT_SRC=https://analytics.example.com/script.js
UMAMI_WEBSITE_ID=your-website-id
```

## 隐私与合规

- 用户识别仅使用内部系统 ID
- 不跟踪个人信息（邮箱、姓名等）
- 用户可以通过 user_id 识别以保持会话连续性
- 可以通过不加载 Umami 脚本来禁用所有跟踪
- 符合 GDPR 和其他隐私法规

## 添加新事件

要添加新的跟踪事件：

1. 将事件名称添加到 `/src/cook-web/src/c-common/tools/tracking.ts` 中的 `EVENT_NAMES` 常量（可选，用于常用事件）
2. 使用 `useTracking` 钩子中的 `trackEvent` 函数
3. 在此目录中记录事件
4. 在载荷中包含相关事件数据

示例：
```typescript
trackEvent('my_new_event', {
  custom_field: 'value',
  // 任何相关数据
});
```

## 最佳实践

1. **事件命名**：使用 snake_case，描述性强且具体
2. **事件数据**：只包含必要的、非敏感数据
3. **错误处理**：跟踪不应阻止用户操作
4. **文档**：记录新事件的目的和数据结构
5. **隐私**：永远不要跟踪 PII 或敏感用户数据
6. **测试**：在开发中验证事件正确触发

## 资源

- [Umami 文档](https://umami.is/docs)
- [Umami 事件跟踪 API](https://umami.is/docs/track-events)
- [GDPR 合规指南](https://umami.is/docs/gdpr)
