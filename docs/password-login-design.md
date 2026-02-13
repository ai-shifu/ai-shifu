# 密码登录功能设计文档

## 1. 概述

为 AI-Shifu 增加密码登录能力，支持用户通过 **手机号+密码** 或 **邮箱+密码** 进行登录。

### 1.1 用户场景

| 场景 | 流程 |
|------|------|
| 新用户注册（手机） | 输入手机号 → 获取验证码 → 验证通过 → 设置密码 → 完成注册 |
| 新用户注册（邮箱） | 输入邮箱 → 获取验证码 → 验证通过 → 设置密码 → 完成注册 |
| 已有用户设置密码 | 登录状态下 → 进入账号设置 → 设置密码 |
| 密码登录 | 输入手机号/邮箱 + 密码 → 直接登录 |
| 忘记密码 | 输入手机号/邮箱 → 获取验证码 → 验证通过 → 重设密码 |
| 修改密码 | 登录状态下 → 输入旧密码 + 新密码 → 完成修改 |

## 2. 现有架构分析

### 2.1 认证 Provider 模式

项目使用工厂模式管理认证方式：

- **基类**: `src/api/flaskr/service/user/auth/base.py` → `AuthProvider`
- **工厂**: `src/api/flaskr/service/user/auth/factory.py` → `register_provider()` / `get_provider()`
- **现有 Provider**:
  - `phone` — 手机验证码登录
  - `email` — 邮箱验证码登录（前端标记为 Coming Soon）
  - `google` — Google OAuth 2.0

### 2.2 数据模型

**`user_auth_credentials` 表** (`AuthCredential` model):

| 字段 | 类型 | 说明 |
|------|------|------|
| credential_bid | VARCHAR(32) | 业务ID |
| user_bid | VARCHAR(32) | 关联用户 |
| provider_name | VARCHAR(255) | 认证提供者 (phone/email/google/**password**) |
| subject_id | VARCHAR(255) | 主体ID |
| subject_format | VARCHAR(255) | 主体格式 |
| identifier | VARCHAR(255) | 标识符（手机号/邮箱） |
| raw_profile | TEXT | 元数据 JSON |
| state | INT | 状态 (1201=未验证, 1202=已验证) |

### 2.3 前端结构

- 登录页: `src/cook-web/src/app/login/page.tsx`
- 登录方式组件: `src/cook-web/src/components/auth/`
- 环境配置: `src/cook-web/src/config/environment.ts` → `loginMethodsEnabled`
- API 层: `src/cook-web/src/api/api.ts`

## 3. 技术方案

### 3.1 数据库

**方案：利用现有 `AuthCredential` 表，密码哈希存在 `raw_profile` 字段中**

新增密码凭证记录：
```
provider_name = "password"
identifier = "手机号" 或 "邮箱"
subject_id = 手机号/邮箱（与 identifier 相同）
subject_format = "phone" 或 "email"
raw_profile = {"provider": "password", "metadata": {"password_hash": "$2b$12$..."}}
state = 1202 (已验证)
```

> 选择 `raw_profile` 而非新增字段的理由：
> - 不需要 migration 改表结构，降低风险
> - `raw_profile` 已有 JSON 序列化/反序列化工具函数（`serialize_raw_profile` / `deserialize_raw_profile`）
> - 密码哈希只有 password provider 需要，其他 provider 无需感知

### 3.2 后端新增文件

#### `src/api/flaskr/service/user/password_utils.py`

密码工具函数：
- `hash_password(plain_text: str) -> str` — bcrypt 加密，cost factor=12
- `verify_password(plain_text: str, hashed: str) -> bool` — 验证密码
- `validate_password_strength(password: str) -> tuple[bool, str]` — 密码强度校验
  - 规则：最少 8 位，必须包含字母和数字

#### `src/api/flaskr/service/user/auth/providers/password.py`

`PasswordAuthProvider` 类：
- `provider_name = "password"`
- `supports_challenge = False`
- `verify(app, request)` — 从 `AuthCredential` 查找 password 凭证，校验密码哈希

### 3.3 后端 API 接口

在 `src/api/flaskr/route/user.py` 新增 4 个接口：

| 接口 | 方法 | 认证 | 说明 |
|------|------|------|------|
| `/user/set_password` | POST | 需要 token | 已登录用户（通过验证码登录后）设置密码 |
| `/user/login_password` | POST | 无需 | 手机号/邮箱 + 密码登录 |
| `/user/reset_password` | POST | 需要 token | 通过验证码验证后重设密码 |
| `/user/change_password` | POST | 需要 token | 已登录用户修改密码（需旧密码） |

#### 接口详细设计

**POST /user/set_password**
```json
// Request (需要登录 token)
{ "password": "newPassword123" }
// Response
{ "code": 0, "msg": "success" }
```
- 用户必须已通过验证码登录（有有效 token）
- 检查该用户是否已有 password credential，有则更新，无则创建
- identifier 取用户当前的手机号或邮箱

**POST /user/login_password**
```json
// Request
{ "identifier": "13800138000", "password": "myPassword123" }
// Response
{ "code": 0, "data": { "token": "...", "user_info": {...} } }
```
- identifier 可以是手机号或邮箱
- 查找 provider_name="password" 且 identifier 匹配的凭证
- 验证密码哈希

**POST /user/reset_password**
```json
// Request (需要验证码验证后的 token)
{ "password": "newPassword123" }
// Response
{ "code": 0, "msg": "success" }
```
- 复用现有验证码流程，验证通过后拿 token 来重设密码

**POST /user/change_password**
```json
// Request (需要登录 token)
{ "old_password": "oldPass123", "new_password": "newPass456" }
// Response
{ "code": 0, "msg": "success" }
```

### 3.4 前端改动

#### 新增 `src/cook-web/src/components/auth/PasswordLogin.tsx`

组件功能：
- **登录模式**：手机号/邮箱输入框 + 密码输入框 + 登录按钮
- **注册模式**：手机号/邮箱 + 发送验证码 + 验证码输入 + 设置密码
- 模式切换：「没有账号？注册」/「已有账号？登录」
- 「忘记密码」链接 → 进入重置流程（复用验证码 → 设新密码）
- 密码显示/隐藏切换

#### 修改 `src/cook-web/src/app/login/page.tsx`

- `LoginMethod` 类型增加 `'password'`
- `renderLoginContent` 增加 password 分支渲染 `PasswordLogin` 组件

#### 修改 `src/cook-web/src/config/environment.ts`

- `loginMethodsEnabled` 支持 `'password'` 选项

#### 修改 `src/cook-web/src/api/api.ts`

新增 API 调用函数：
- `loginWithPassword(identifier, password)`
- `setPassword(password)`
- `resetPassword(password)`
- `changePassword(oldPassword, newPassword)`

### 3.5 安全措施

| 项目 | 方案 |
|------|------|
| 密码存储 | bcrypt，cost factor 12 |
| 密码强度 | ≥8 位，必须含字母+数字 |
| 防暴力破解 | 同一 identifier 连续失败 5 次，锁定 15 分钟（后续迭代） |
| 传输安全 | HTTPS（现有） |

> 注：防暴力破解（限流/锁定）作为后续迭代优化项，首版不实现。

## 4. 不涉及的改动

- ❌ 不改表结构（利用现有 `raw_profile` 字段）
- ❌ 不改现有 phone/email/google provider
- ❌ 不改现有认证中间件（token 验证机制不变）
- ❌ 首版不做登录限流/账号锁定

## 5. 依赖

- Python: `bcrypt` 包（`pip install bcrypt`，需加入 requirements.txt）
- 前端: 无新依赖
