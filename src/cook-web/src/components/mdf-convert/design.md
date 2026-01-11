# MDF Convert Dialog 移植操作手册

> **版本**: 1.1 (无打点版本)
> **创建日期**: 2026-01-10
> **最后更新**: 2026-01-10
> **适用项目**: Next.js 15+ with next-intl, shadcn/ui

---

## 📋 目录

- [前置条件检查](#前置条件检查)
- [移植步骤](#移植步骤)
  - [步骤 1: 拷贝核心文件](#步骤-1-拷贝核心文件)
  - [步骤 2: 添加国际化配置](#步骤-2-添加国际化配置)
  - [步骤 3: 配置环境变量](#步骤-3-配置环境变量)
  - [步骤 4: 集成到 Markdown Flow 编辑器](#步骤-4-集成到-markdown-flow-编辑器) ⭐ 推荐
    - [4.1 安装 markdown-flow-ui 包](#41-安装-markdown-flow-ui-包)
    - [4.2 完整的编辑器集成示例](#42-完整的编辑器集成示例)
    - [4.3 工具栏按钮图标说明](#43-工具栏按钮图标说明)
    - [4.4 基础集成示例](#44-基础集成示例不使用-markdown-flow-编辑器)
- [测试验证](#测试验证)
- [常见问题](#常见问题)
- [技术参考](#技术参考)

---

## 🔍 前置条件检查

移植前，请确认新项目满足以下条件：

### 必需的依赖包

```bash
# 检查以下包是否已安装
npm list next-intl lucide-react sonner @radix-ui/react-dialog @radix-ui/react-scroll-area
```

✅ **已确认的环境**：

- Next.js 15+
- React 19+
- next-intl (国际化)
- shadcn/ui 组件库
- Tailwind CSS v4

### shadcn/ui 组件检查

确认以下组件已安装（检查 `src/components/ui/` 目录）：

- ✅ `dialog.tsx`
- ✅ `button.tsx`
- ✅ `textarea.tsx`
- ✅ `label.tsx`
- ✅ `scroll-area.tsx`

如果缺少任何组件，运行：

```bash
npx shadcn@latest add dialog button textarea label scroll-area
```

---

## 🚀 移植步骤

### 步骤 1: 拷贝核心文件

#### 1.1 确定路径

**当前项目路径**（源项目）：

```
/Users/heshaofu/Documents/code/myproject/AI/ai-shifu-code/markdown-flow-playground/frontend
```

**新项目路径**（目标项目）：

```
/path/to/your/new-project
```

#### 1.2 拷贝文件

**方式一：使用命令行拷贝**

```bash
# 设置路径变量（请修改为实际路径）
SOURCE_DIR="/Users/heshaofu/Documents/code/myproject/AI/ai-shifu-code/markdown-flow-playground/frontend"
TARGET_DIR="/path/to/your/new-project"

# 1. 拷贝主组件
cp "${SOURCE_DIR}/src/components/MdfConvertDialog.tsx" \
   "${TARGET_DIR}/src/components/"

# 2. 拷贝用户 ID 管理工具
cp "${SOURCE_DIR}/src/lib/user.ts" \
   "${TARGET_DIR}/src/lib/"

echo "✅ 核心文件拷贝完成！"
```

**方式二：手动拷贝**

1. **拷贝 MdfConvertDialog.tsx**
   - 源文件：`src/components/MdfConvertDialog.tsx`
   - 目标：新项目的 `src/components/MdfConvertDialog.tsx`

2. **拷贝 user.ts**
   - 源文件：`src/lib/user.ts`
   - 目标：新项目的 `src/lib/user.ts`

#### 1.3 添加 API 代码到新项目

打开新项目的 `src/lib/api.ts` 文件，添加以下代码：

<details>
<summary>📄 点击展开 - 完整的 API 代码</summary>

````typescript
// ==================== 导入依赖 ====================
import { getUserId, refreshUserIdExpiry } from './user';

// ==================== 工具函数 ====================

/**
 * 获取包含用户ID的通用请求头
 */
function getCommonHeaders(): HeadersInit {
  const userId = getUserId();
  refreshUserIdExpiry(); // 刷新用户ID的过期时间

  return {
    'Content-Type': 'application/json',
    'User-Id': userId,
  };
}

/**
 * API 错误类
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public code?: number,
    public response?: Response,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * 统一处理 API 响应
 */
async function handleApiResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new ApiError(
      `API request failed: ${response.status} ${response.statusText}`,
      response.status,
      response,
    );
  }

  const data = await response.json();

  if (data.code !== undefined && data.code !== 200) {
    throw new ApiError(data.message || 'API returned error code', data.code);
  }

  return data;
}

// ==================== MDF Convert 接口和函数 ====================

/**
 * MDF 转换请求参数
 */
export interface MdfConvertRequest {
  text: string; // 待转换的文本内容
  language?: string; // 语言：'Chinese' | 'English'
  output_mode?: 'content' | 'both'; // 输出模式
  user_id?: string; // 用户 ID（可选）
}

/**
 * MDF 转换响应数据
 */
export interface MdfConvertResponse {
  document_prompt?: string; // 文档提示词（可选）
  content_prompt: string; // 内容提示词
  request_id: string; // 请求 ID
  timestamp: string; // 时间戳
  metadata: {
    input_length: number; // 输入文本长度
    language: string; // 使用的语言
    user_id?: string; // 用户 ID
    output_mode: string; // 输出模式
  };
}

/**
 * 调用 MDF 转换 API
 *
 * @param request - 转换请求参数
 * @returns 转换结果
 * @throws {ApiError} 当 API 调用失败时抛出异常
 *
 * @example
 * ```typescript
 * const result = await convertToMdf({
 *   text: '用户输入的文本',
 *   language: 'Chinese',
 *   output_mode: 'content'
 * })
 * console.log(result.content_prompt)
 * ```
 */
export async function convertToMdf(
  request: MdfConvertRequest,
): Promise<MdfConvertResponse> {
  try {
    // 从环境变量读取 API 基础 URL
    const baseUrl =
      process.env.NEXT_PUBLIC_LLM_API_URL || 'http://localhost:8000';

    const response = await fetch(`${baseUrl}/gen/mdf-convert`, {
      method: 'POST',
      headers: getCommonHeaders(),
      body: JSON.stringify({
        text: request.text,
        language: request.language || 'Chinese',
        output_mode: request.output_mode || 'content',
        user_id: request.user_id || getUserId(),
      }),
    });

    return await handleApiResponse<MdfConvertResponse>(response);
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(
      `Network error: ${error instanceof Error ? error.message : 'Unknown error'}`,
    );
  }
}
````

</details>

**📌 注意事项**：

- 如果新项目的 `api.ts` 已经有 `getCommonHeaders()` 函数，可以复用现有的，只需确保它返回包含 `User-Id` 的请求头
- 如果已有 `ApiError` 类，检查接口是否兼容，不兼容则需要调整
- 如果已有 `handleApiResponse()` 函数，同样检查兼容性

---

### 步骤 2: 添加国际化配置

#### 2.1 定位国际化文件

找到新项目的国际化配置文件：

- 中文：通常是 `messages/zh.json` 或 `locales/zh/common.json`
- 英文：通常是 `messages/en.json` 或 `locales/en/common.json`

#### 2.2 添加中文翻译

打开中文翻译文件，添加以下内容：

```json
{
  "mdfConvert": {
    "buttonText": "转换为 MDF",
    "dialogTitle": "智能转换",
    "inputLabel": "待转换的内容",
    "inputPlaceholder": "请输入完整的文章内容，AI 将会智能转换成内容提示词",
    "convertButton": "开始转换",
    "converting": "转换中...",
    "convertSuccess": "转换成功！",
    "convertError": "转换失败",
    "documentPromptTitle": "文档提示词",
    "contentPromptTitle": "内容提示词",
    "applyButton": "应用",
    "copyButton": "复制",
    "closeButton": "关闭",
    "applySuccess": "内容已应用到创作区",
    "copySuccess": "内容已复制到剪贴板",
    "textTooShort": "请输入内容",
    "textTooLong": "文本内容过长，请控制在 10,000 字符以内",
    "networkError": "网络错误，请检查连接后重试",
    "scrollHint": "内容较长，可上下滚动查看完整内容",
    "backButton": "上一步"
  },
  "chatDialog": {
    "confirmApplyTitle": "确认应用提示词",
    "confirmApplyDescription": "应用提示词将会覆盖当前创作区的内容，是否确认？",
    "confirmApplyButton": "确认应用",
    "cancelButton": "取消"
  }
}
```

#### 2.3 添加英文翻译

打开英文翻译文件，添加以下内容：

```json
{
  "mdfConvert": {
    "buttonText": "Convert to MDF",
    "dialogTitle": "AI Conversion",
    "inputLabel": "Content to Convert",
    "inputPlaceholder": "Please enter the complete article content, AI will intelligently convert it into content prompt",
    "convertButton": "Start Converting",
    "converting": "Converting...",
    "convertSuccess": "Conversion successful!",
    "convertError": "Conversion failed",
    "documentPromptTitle": "Document Prompt",
    "contentPromptTitle": "Content Prompt",
    "applyButton": "Apply",
    "copyButton": "Copy",
    "closeButton": "Close",
    "applySuccess": "Content applied to creation area",
    "copySuccess": "Content copied to clipboard",
    "textTooShort": "Please enter content",
    "textTooLong": "Text too long, please limit to 10,000 characters",
    "networkError": "Network error, please check connection and retry",
    "scrollHint": "Content is long, scroll up and down to view complete content",
    "backButton": "Back"
  },
  "chatDialog": {
    "confirmApplyTitle": "Confirm Apply Prompts",
    "confirmApplyDescription": "Applying prompts will overwrite current content. Are you sure?",
    "confirmApplyButton": "Confirm Apply",
    "cancelButton": "Cancel"
  }
}
```

#### 2.4 验证国际化配置

```bash
# 检查 JSON 文件格式是否正确
npx prettier --check messages/*.json

# 如果格式有问题，自动修复
npx prettier --write messages/*.json
```

---

### 步骤 3: 配置环境变量

#### 3.1 创建或编辑 .env.local

在新项目根目录找到 `.env.local` 文件（如果不存在，创建它）：

```bash
# 在新项目根目录下
touch .env.local
```

#### 3.2 添加配置

打开 `.env.local`，添加以下配置：

```bash
# ==================== MDF Convert API 配置 ====================
# MDF 转换服务的后端 API 地址
# 生产环境: https://your-production-api.com
# 开发环境: http://localhost:8000
NEXT_PUBLIC_LLM_API_URL=http://localhost:8000
```

**📌 重要提示**：

- ⚠️ 请将 `http://localhost:8000` 替换为您的实际后端 API 地址
- 生产环境部署时，需要在服务器上设置对应的环境变量
- `NEXT_PUBLIC_` 前缀表示该变量会暴露给浏览器端代码

#### 3.3 重启开发服务器

环境变量修改后，需要重启开发服务器：

```bash
# 按 Ctrl+C 停止当前服务器，然后重新启动
npm run dev
```

---

### 步骤 4: 集成到 Markdown Flow 编辑器

**🎯 集成工作流程**：

```
用户点击工具栏转换按钮
        ↓
打开 MdfConvertDialog 对话框
        ↓
用户输入文本并点击"转换"
        ↓
调用后端 API 进行转换
        ↓
显示转换结果（文档提示词 + 内容提示词）
        ↓
用户点击"应用"按钮
        ↓
触发 handleApplyMdfContent 回调
        ↓
更新编辑器内容：
  - markdownFlow ← contentPrompt（内容提示词）
  - additionalPrompt ← documentPrompt（文档提示词）
        ↓
关闭对话框，编辑器显示转换后的内容
```

#### 4.1 安装 markdown-flow-ui 包

首先确保已安装 `markdown-flow-ui` 编辑器组件：

```bash
# 安装 markdown-flow-ui 编辑器
npm install markdown-flow-ui@^0.1.69
```

**📌 版本说明**：

- 推荐版本：`^0.1.69` 或更高版本
- 该版本支持 `toolbarActionsRight` 自定义工具栏按钮
- 支持 `variables` 属性用于变量管理

#### 4.2 完整的编辑器集成示例

在编辑器组件中（例如 `src/components/EditPanel.tsx` 或 `src/app/editor/page.tsx`）：

```typescript
'use client'

import { useState, useMemo } from 'react'
import { MarkdownFlowEditor, type EditMode } from 'markdown-flow-ui'
import { useTranslations, useLocale } from 'next-intl'
import { MdfConvertDialog } from '@/components/MdfConvertDialog'

interface EditorConfig {
  markdownFlow: string        // MDF 内容提示词
  additionalPrompt: string    // 文档提示词
}

export default function EditorPage() {
  const t = useTranslations()
  const locale = useLocale()

  // 编辑器配置状态
  const [config, setConfig] = useState<EditorConfig>({
    markdownFlow: '',
    additionalPrompt: ''
  })

  // 编辑模式
  const [editMode, setEditMode] = useState<EditMode>('preview')

  // MDF Convert Dialog 状态
  const [isMdfConvertOpen, setIsMdfConvertOpen] = useState(false)

  // 自定义工具栏按钮 - 添加 MDF 转换按钮
  const toolbarActionsRight = useMemo(
    () => [
      {
        key: 'mdfConvert',
        label: '',  // 空字符串表示只显示图标
        icon: (
          <svg
            aria-hidden="true"
            viewBox="0 0 1024 1024"
            className="h-5 w-5 fill-current"
          >
            <path d="M633.6 358.4l-473.6 460.8c0 12.8 6.4 19.2 12.8 19.2l51.2 51.2c6.4 6.4 12.8 6.4 19.2 12.8L704 441.6 633.6 358.4zM780.8 384c0 6.4 6.4 6.4 0 0l6.4 6.4h12.8l121.6-121.6c12.8-12.8 12.8-44.8-12.8-64l-51.2-51.2c-19.2-19.2-51.2-25.6-64-12.8l-121.6 121.6-6.4 6.4c0 6.4 0 6.4 6.4 6.4L780.8 384zM313.6 224l64 25.6c6.4 0 6.4 6.4 12.8 19.2l25.6 57.6h12.8l25.6-57.6c0-6.4 6.4-12.8 12.8-12.8l57.6-25.6v-6.4-6.4l-57.6-32c-6.4 0-12.8-6.4-12.8-12.8l-25.6-64h-12.8l-25.6 64c-6.4 6.4-6.4 12.8-19.2 12.8l-57.6 25.6-6.4 6.4 6.4 6.4zM166.4 531.2s6.4 0 0 0c6.4 0 6.4-6.4 0 0l25.6-51.2c0-6.4 6.4-12.8 12.8-12.8l44.8-19.2v-6.4l-44.8-19.2-12.8-12.8-19.2-44.8h-6.4l-19.2 44.8c0 6.4-6.4 12.8-12.8 12.8l-44.8 19.2 44.8 19.2c6.4 0 6.4 6.4 12.8 12.8l19.2 57.6c0-6.4 0 0 0 0zM934.4 774.4l-89.6-38.4c-12.8-6.4-19.2-12.8-25.6-25.6l-38.4-83.2s0-6.4-6.4-6.4H768s-6.4 0-6.4 6.4l-38.4 83.2c-6.4 12.8-12.8 19.2-19.2 25.6l-83.2 38.4h-6.4v12.8h6.4l83.2 38.4c12.8 6.4 19.2 12.8 25.6 25.6l38.4 83.2s0 6.4 6.4 6.4h6.4s6.4 0 6.4-6.4l38.4-83.2c6.4-12.8 12.8-19.2 19.2-25.6l83.2-38.4h6.4c6.4 0 6.4-6.4 0-12.8 6.4 6.4 6.4 6.4 0 0z" />
          </svg>
        ),
        tooltip: t('mdfConvert.buttonText'),  // 悬停提示文本
        onClick: () => setIsMdfConvertOpen(true),  // 点击打开转换对话框
      },
    ],
    [t],
  )

  // 处理 MDF 内容变化
  const handleContentChange = (value: string) => {
    setConfig({ ...config, markdownFlow: value })
  }

  // 处理应用 MDF 转换结果
  const handleApplyMdfContent = (documentPrompt: string, contentPrompt: string) => {
    setConfig({
      markdownFlow: contentPrompt,      // 将内容提示词设置到编辑器
      additionalPrompt: documentPrompt  // 将文档提示词设置到额外提示词区域
    })
  }

  return (
    <div className="flex flex-col h-screen">
      {/* 编辑器区域 */}
      <div className="flex-1 p-6">
        <h2 className="text-xl font-bold mb-4">Markdown Flow 编辑器</h2>

        {/* Markdown Flow 编辑器 */}
        <div className="h-[500px]">
          <MarkdownFlowEditor
            content={config.markdownFlow}
            onChange={handleContentChange}
            editMode={editMode}
            locale={locale === 'zh' ? 'zh-CN' : 'en-US'}
            toolbarActionsRight={toolbarActionsRight}  // 传入自定义工具栏按钮
          />
        </div>

        {/* 文档提示词区域（可选） */}
        {config.additionalPrompt && (
          <div className="mt-4">
            <h3 className="text-sm font-medium mb-2">文档提示词</h3>
            <textarea
              value={config.additionalPrompt}
              onChange={(e) => setConfig({ ...config, additionalPrompt: e.target.value })}
              className="w-full h-32 p-2 border rounded"
              placeholder="文档提示词..."
            />
          </div>
        )}
      </div>

      {/* MDF 转换对话框 */}
      <MdfConvertDialog
        open={isMdfConvertOpen}
        onOpenChange={setIsMdfConvertOpen}
        onApplyContent={handleApplyMdfContent}
      />
    </div>
  )
}
```

**🔑 关键集成点说明**：

1. **工具栏按钮配置** (`toolbarActionsRight`)：
   - `key`: 唯一标识符
   - `label`: 按钮文本（空字符串表示只显示图标）
   - `icon`: SVG 图标组件
   - `tooltip`: 悬停提示文本（使用国际化）
   - `onClick`: 点击事件处理函数

2. **应用转换结果** (`handleApplyMdfContent`)：
   - `documentPrompt` → 设置到 `additionalPrompt`（文档提示词区域）
   - `contentPrompt` → 设置到 `markdownFlow`（编辑器内容）

3. **对话框集成**：
   - `open`: 控制对话框显示/隐藏
   - `onOpenChange`: 对话框状态变化回调
   - `onApplyContent`: 应用转换结果的回调

#### 4.3 工具栏按钮图标说明

上述示例使用的是"魔法棒"图标，您也可以使用其他图标库，例如 `lucide-react`：

```typescript
import { Wand2 } from 'lucide-react'

const toolbarActionsRight = useMemo(
  () => [
    {
      key: 'mdfConvert',
      label: '',
      icon: <Wand2 className="h-5 w-5" />,
      tooltip: t('mdfConvert.buttonText'),
      onClick: () => setIsMdfConvertOpen(true),
    },
  ],
  [t],
)
```

#### 4.4 基础集成示例（不使用 Markdown Flow 编辑器）

在需要使用 MDF 转换功能的组件中（例如 `src/app/page.tsx` 或 `src/components/Editor.tsx`）：

```typescript
'use client'

import { useState } from 'react'
import { MdfConvertDialog } from '@/components/MdfConvertDialog'

export default function EditorPage() {
  const [isMdfConvertOpen, setIsMdfConvertOpen] = useState(false)

  // 处理应用转换结果的回调
  const handleApplyMdfContent = (documentPrompt: string, contentPrompt: string) => {
    console.log('📄 Document Prompt:', documentPrompt)
    console.log('📝 Content Prompt:', contentPrompt)

    // 在这里处理转换后的内容
    // 例如：更新编辑器内容、保存到状态等
  }

  return (
    <div>
      {/* 触发按钮 */}
      <button
        onClick={() => setIsMdfConvertOpen(true)}
        className="px-4 py-2 bg-blue-500 text-white rounded"
      >
        转换为 MDF
      </button>

      {/* MDF 转换对话框 */}
      <MdfConvertDialog
        open={isMdfConvertOpen}
        onOpenChange={setIsMdfConvertOpen}
        onApplyContent={handleApplyMdfContent}
      />
    </div>
  )
}
```

#### 4.2 与现有编辑器集成

如果您有一个编辑器组件，需要将转换结果应用到编辑器：

```typescript
'use client'

import { useState } from 'react'
import { MdfConvertDialog } from '@/components/MdfConvertDialog'

export default function MarkdownEditor() {
  const [isMdfConvertOpen, setIsMdfConvertOpen] = useState(false)
  const [editorContent, setEditorContent] = useState('')
  const [documentPrompt, setDocumentPrompt] = useState('')

  const handleApplyMdfContent = (docPrompt: string, contentPrompt: string) => {
    // 更新编辑器内容
    setEditorContent(contentPrompt)
    setDocumentPrompt(docPrompt)

    // 可选：触发保存、同步等操作
    // onContentChange?.(contentPrompt, docPrompt)
  }

  return (
    <div>
      {/* 工具栏 */}
      <div className="toolbar">
        <button onClick={() => setIsMdfConvertOpen(true)}>
          🔄 转换为 MDF
        </button>
      </div>

      {/* 编辑器区域 */}
      <textarea
        value={editorContent}
        onChange={(e) => setEditorContent(e.target.value)}
        className="w-full h-96 p-4 border"
      />

      {/* MDF 转换对话框 */}
      <MdfConvertDialog
        open={isMdfConvertOpen}
        onOpenChange={setIsMdfConvertOpen}
        onApplyContent={handleApplyMdfContent}
      />
    </div>
  )
}
```

#### 4.3 仅使用复制功能（不使用应用功能）

如果您只需要复制功能，不需要应用到编辑器：

```typescript
'use client'

import { useState } from 'react'
import { MdfConvertDialog } from '@/components/MdfConvertDialog'

export default function ConvertPage() {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div>
      <button onClick={() => setIsOpen(true)}>
        转换文本
      </button>

      {/* 不传递 onApplyContent，对话框将只显示复制按钮 */}
      <MdfConvertDialog
        open={isOpen}
        onOpenChange={setIsOpen}
      />
    </div>
  )
}
```

---

## ✅ 测试验证

### 测试清单

完成移植后，请按以下清单进行测试：

#### 1. UI 渲染测试

- [ ] 点击触发按钮，对话框能正常打开
- [ ] 对话框样式正确（宽度、高度、居中显示）
- [ ] 输入框显示正常，可以输入文本
- [ ] 字数统计显示正确（格式：`123 / 10,000`）
- [ ] 按钮样式和状态正确（启用/禁用）
- [ ] 点击关闭按钮或遮罩层，对话框能正常关闭

#### 2. 输入验证测试

- [ ] **空输入测试**：输入框为空时，转换按钮应被禁用
- [ ] **正常输入测试**：输入文本后，转换按钮应启用
- [ ] **超长输入测试**：输入超过 10,000 字符的文本，点击转换应显示错误提示
- [ ] **短文本测试**：输入少量文字（如 "测试"），应能正常转换

#### 3. API 调用测试

- [ ] **成功转换**：输入正常文本，点击转换，应显示"转换成功"提示
- [ ] **显示结果**：转换成功后，应显示转换后的内容提示词
- [ ] **加载状态**：转换过程中，按钮应显示加载动画和"转换中..."文本
- [ ] **API 错误处理**：后端服务不可用时，应显示错误提示

测试命令：

```bash
# 模拟 API 不可用（关闭后端服务器），测试错误处理
# 应该看到 Toast 错误提示
```

#### 4. 复制功能测试

- [ ] **复制成功**：点击复制按钮，应显示"内容已复制到剪贴板"提示
- [ ] **剪贴板验证**：复制后，在文本编辑器中粘贴，内容应正确
- [ ] **降级方案测试**：在不支持 `navigator.clipboard` 的浏览器中测试（可选）

测试步骤：

```
1. 转换文本得到结果
2. 点击复制按钮
3. 看到成功提示
4. 在任意文本编辑器按 Ctrl+V 或 Cmd+V
5. 验证内容是否正确
```

#### 5. 应用功能测试（如果集成）

- [ ] **确认对话框**：点击"应用"按钮，应显示确认对话框
- [ ] **确认应用**：在确认对话框点击"确认应用"，内容应应用到编辑器
- [ ] **取消应用**：在确认对话框点击"取消"，应关闭确认对话框但不应用内容
- [ ] **成功提示**：应用成功后，应显示"内容已应用到创作区"提示
- [ ] **对话框关闭**：应用成功后，主对话框应自动关闭

#### 6. 国际化测试

- [ ] **中文界面**：切换到中文，所有文本应显示中文
- [ ] **英文界面**：切换到英文，所有文本应显示英文
- [ ] **无翻译键泄露**：不应看到类似 `mdfConvert.dialogTitle` 的原始键名

测试方法：

```typescript
// 在浏览器控制台切换语言
// 方法取决于您的国际化配置
// 例如：修改 URL 参数、点击语言切换按钮等
```

### 快速测试脚本

创建一个测试页面 `src/app/test-mdf/page.tsx`：

```typescript
'use client'

import { useState } from 'react'
import { MdfConvertDialog } from '@/components/MdfConvertDialog'

export default function TestMdfPage() {
  const [isOpen, setIsOpen] = useState(false)
  const [result, setResult] = useState<{
    documentPrompt: string
    contentPrompt: string
  } | null>(null)

  const handleApply = (documentPrompt: string, contentPrompt: string) => {
    setResult({ documentPrompt, contentPrompt })
    console.log('✅ 应用成功！', { documentPrompt, contentPrompt })
  }

  return (
    <div className="p-8 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">MDF Convert 测试页面</h1>

      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
      >
        打开 MDF 转换对话框
      </button>

      {result && (
        <div className="mt-8 p-4 bg-gray-100 rounded">
          <h2 className="font-bold mb-2">转换结果：</h2>
          <div className="mb-4">
            <strong>Document Prompt:</strong>
            <pre className="mt-2 p-2 bg-white rounded text-sm overflow-auto">
              {result.documentPrompt || '(空)'}
            </pre>
          </div>
          <div>
            <strong>Content Prompt:</strong>
            <pre className="mt-2 p-2 bg-white rounded text-sm overflow-auto">
              {result.contentPrompt}
            </pre>
          </div>
        </div>
      )}

      <MdfConvertDialog
        open={isOpen}
        onOpenChange={setIsOpen}
        onApplyContent={handleApply}
      />
    </div>
  )
}
```

访问 `http://localhost:3000/test-mdf` 进行测试。

---

## ❓ 常见问题

### Q1: 对话框打开后样式错乱或显示不全

**可能原因**：

- Tailwind CSS 配置不完整
- CSS 变量未定义

**解决方案**：

```typescript
// 检查 globals.css 是否包含 shadcn/ui 的 CSS 变量
@layer base {
  :root {
    --background: 0 0% 100%;
    --foreground: 222.2 84% 4.9%;
    /* ... 其他变量 */
  }
}
```

### Q2: 国际化文本不显示，显示为翻译键

**可能原因**：

- 翻译文件路径错误
- next-intl 配置未生效
- 组件未在 `NextIntlClientProvider` 包裹范围内

**解决方案**：

```typescript
// 检查 app/layout.tsx 或 i18n.ts
import { NextIntlClientProvider } from 'next-intl'

export default async function RootLayout({ children }) {
  const messages = await getMessages()

  return (
    <html>
      <body>
        <NextIntlClientProvider messages={messages}>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  )
}
```

### Q3: API 调用失败，显示 CORS 错误

**可能原因**：

- 后端 API 未配置 CORS
- 前端请求的 URL 不正确

**解决方案**：

**方式一：配置后端 CORS**（推荐）

```python
# FastAPI 示例
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # 前端地址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**方式二：使用 Next.js 代理**

```javascript
// next.config.js
module.exports = {
  async rewrites() {
    return [
      {
        source: '/gen/:path*',
        destination: 'http://localhost:8000/gen/:path*',
      },
    ];
  },
};
```

然后修改环境变量：

```bash
NEXT_PUBLIC_LLM_API_URL=http://localhost:3000
```

### Q4: 复制功能不工作

**可能原因**：

- 浏览器不支持 `navigator.clipboard` API
- 网站未使用 HTTPS（localhost 除外）

**解决方案**：

- 确保使用 HTTPS 或 localhost
- 代码已包含降级方案（document.execCommand），应自动处理
- 检查浏览器控制台是否有权限错误

### Q5: 环境变量修改后不生效

**解决方案**：

- 重启开发服务器（Ctrl+C 然后 `npm run dev`）
- 清除 Next.js 缓存：`rm -rf .next && npm run dev`
- 检查变量名是否正确（必须以 `NEXT_PUBLIC_` 开头才能在浏览器端使用）

---

## 📚 技术参考

### 组件 Props 接口

```typescript
interface MdfConvertDialogProps {
  open: boolean; // 控制对话框显示/隐藏
  onOpenChange: (open: boolean) => void; // 对话框状态变化回调
  onApplyContent?: (
    // 应用内容回调（可选）
    documentPrompt: string, // 文档提示词
    contentPrompt: string, // 内容提示词
  ) => void;
}
```

### API 接口定义

```typescript
// 请求接口
interface MdfConvertRequest {
  text: string; // 必填：待转换的文本
  language?: string; // 可选：'Chinese' | 'English'，默认 'Chinese'
  output_mode?: string; // 可选：'content' | 'both'，默认 'content'
  user_id?: string; // 可选：用户 ID，默认自动生成
}

// 响应接口
interface MdfConvertResponse {
  document_prompt?: string; // 文档提示词（可选）
  content_prompt: string; // 内容提示词
  request_id: string; // 请求 ID（用于追踪）
  timestamp: string; // 时间戳
  metadata: {
    input_length: number; // 输入文本长度
    language: string; // 使用的语言
    user_id?: string; // 用户 ID
    output_mode: string; // 输出模式
  };
}
```

### 依赖包版本参考

```json
{
  "dependencies": {
    "react": "^19.0.0",
    "next": "^15.0.0",
    "next-intl": "^3.0.0",
    "lucide-react": "^0.454.0",
    "sonner": "^1.0.0",
    "markdown-flow-ui": "^0.1.69",
    "@radix-ui/react-dialog": "^1.0.5",
    "@radix-ui/react-scroll-area": "^1.0.5"
  }
}
```

**📦 关键依赖说明**：

| 包名                     | 版本       | 说明                                           |
| ------------------------ | ---------- | ---------------------------------------------- |
| `markdown-flow-ui`       | `^0.1.69`  | Markdown Flow 编辑器组件，支持自定义工具栏按钮 |
| `next-intl`              | `^3.0.0`   | Next.js 国际化方案                             |
| `sonner`                 | `^1.0.0`   | Toast 通知组件                                 |
| `lucide-react`           | `^0.454.0` | 图标库（可选，用于工具栏图标）                 |
| `@radix-ui/react-dialog` | `^1.0.5`   | Dialog 对话框原始组件                          |

---

## 📝 移植清单

使用此清单确保所有步骤都已完成：

### 文件拷贝

- [ ] 已拷贝 `MdfConvertDialog.tsx` 到 `src/components/`
- [ ] 已拷贝 `user.ts` 到 `src/lib/`
- [ ] 已添加 API 相关代码到 `src/lib/api.ts`

### 配置修改

- [ ] 已添加中文翻译到国际化配置文件
- [ ] 已添加英文翻译到国际化配置文件
- [ ] 已在 `.env.local` 中配置 `NEXT_PUBLIC_LLM_API_URL`
- [ ] 已重启开发服务器使环境变量生效

### 集成开发

- [ ] 已在目标页面/组件中导入 `MdfConvertDialog`
- [ ] 已实现触发按钮
- [ ] 已实现 `onApplyContent` 回调（如需要）
- [ ] 已测试对话框打开/关闭

### 测试验证

- [ ] UI 渲染测试通过
- [ ] 输入验证测试通过
- [ ] API 调用测试通过
- [ ] 复制功能测试通过
- [ ] 应用功能测试通过（如集成）
- [ ] 国际化测试通过

---

## 🎉 移植完成

恭喜您完成 MDF Convert Dialog 的移植！

如果遇到任何问题，请参考：

1. [常见问题](#常见问题) 部分
2. [技术参考](#技术参考) 部分
3. 源项目的 README 和文档

**技术支持**：

- 源项目路径：`/Users/heshaofu/Documents/code/myproject/AI/ai-shifu-code/markdown-flow-playground/frontend`
- 核心组件：`src/components/MdfConvertDialog.tsx`
- API 实现：`src/lib/api.ts` (第 270-297 行)

---

**文档版本**: v1.1 (无打点版本)
**最后更新**: 2026-01-10
**基于代码版本**: b163767 (Fix code review issues from GitHub PR feedback)
**维护者**: Claude Code
