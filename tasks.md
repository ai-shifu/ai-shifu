# 密码登录功能 - 任务清单

设计文档：[docs/password-login-design.md](docs/password-login-design.md)

## 后端

- [ ] **T1** 添加 `bcrypt` 到 `requirements.txt`
- [ ] **T2** 新建 `src/api/flaskr/service/user/password_utils.py` — 密码哈希、验证、强度校验工具函数
- [ ] **T3** 新建 `src/api/flaskr/service/user/auth/providers/password.py` — PasswordAuthProvider 实现
- [ ] **T4** 在 provider `__init__.py` 中导入 password provider 触发注册
- [ ] **T5** 在 `src/api/flaskr/route/user.py` 新增 `POST /user/login_password` 接口
- [ ] **T6** 在 `src/api/flaskr/route/user.py` 新增 `POST /user/set_password` 接口
- [ ] **T7** 在 `src/api/flaskr/route/user.py` 新增 `POST /user/reset_password` 接口
- [ ] **T8** 在 `src/api/flaskr/route/user.py` 新增 `POST /user/change_password` 接口

## 前端

- [ ] **T9** 在 `src/cook-web/src/api/api.ts` 新增密码相关 API 调用函数
- [ ] **T10** 新建 `src/cook-web/src/components/auth/PasswordLogin.tsx` — 密码登录/注册组件
- [ ] **T11** 修改 `src/cook-web/src/app/login/page.tsx` — 集成 password 登录方式
- [ ] **T12** 修改 `src/cook-web/src/config/environment.ts` — loginMethodsEnabled 支持 password

## 提交规范

每完成一个 T* 任务，做一次原子化 git commit：
- 格式：`feat(auth): T{N} - {简要描述}`
- 示例：`feat(auth): T1 - add bcrypt dependency`
