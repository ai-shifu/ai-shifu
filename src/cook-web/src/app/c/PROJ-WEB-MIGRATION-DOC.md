# ai-shifu-ui 项目迁移合并文档记录

## 开发流程和规范(晨阳整理)
1. 新建功能分支 feature/nextjs-build-web
2. 在 cook-web 目录中重构 web 目录功能暂时保留 web 目录
3. 开通 基于feature/nextjs-build-web 的 cicd 流程用于测试
4. 制定前端 js 格式化标准(配置插件统一 format 格式)
5. 完善 pre-commit run --all-files 前端规则
6. 使用 cook-web 内的登录组件 去掉 web 之前的登录流程 共享登录和注册逻辑组件
7. feature/nextjs-build-web 不定期会同步 main 分支
8. 由于上面修改会将两个 前端项目合并成一个 所以 编辑器页面的域名将不在可用 可以使用 path 方式进入编辑器例如http://web.dev.pillowai.cn/cook/
9. 非基于feature/nextis-build-web 开发的功能 如cook-web 相关的功能修改 合并 main 之前最好和 feature/nextis-build-web 进行比对 或者先合并到 feature/nextis-build-web 再合并到 main 以免出现大规模冲突
10. 等 web 端重构达到可用上线标准时 将 cook-web 文件夹重命名为 ui 目录

## 迁移操作记录
- 把 `web` 目录的功能往 `cook-web` 迁移
  * 保持 `web` 的代码处于干净状态，方便迁移过程中随时对比查看
- `web` 迁移过来的 **页面** 目前放在 `src/app/c` 目录下
- 其它类似 `assets`, `store`, `service` 等功能目录，全部加了 `c-`
  * 后续可重命名或考虑跟 `cook-web` 已有的功能目录合并
- i18n 语言文件直接合并到了 `public/locales` 对应的语言文件内
  * 统一放在名为 `c` 的字段下，可根据需要随时调整
- `web` 项目获取 `config/env` 的接口放在了 `src/app/api/config/c-env/`
- `https://github.com/ai-shifu/chatui.git#no-scroll` 内置到了 `ChatUi/ForkChatUI`
  * 官方已经基本不再维护
  * fork 后自行维护成本也较高，想要和 `ai-shifu` 保持图标和样式防止一致的话，从样式方案到图标库、组件库 都要换 - 其实就相当于重写
  * 放进项目内慢慢逐步往本项目的技术栈迁移是最灵活和可持续维护的方案 

## 后期合并操作
- 重命名 `cook-web` 为 `ui`
- 合并后两个项目相关页面的路由路径设置

## 迁移完成后项目主要三方库选择
- CSS 方案 - [Tailwind CSS](https://tailwindcss.com/)
  * `cook-web` 目前在用的
- 状态管理 - [zustand](https://github.com/pmndrs/zustand)
  * `web` 目前在用的
- UI 组件 - [shadcn/ui](https://ui.shadcn.com/)
  * `cook-web` 目前在用的
- icon 库 - [lucide](https://lucide.dev/)
  * `cook-web` 目前在用的

> 要逐步重构去掉 `ant-design`, `ant-design-mobile`, `ant-design-icon`, `ChatUI`, `ChatUI-icon`, `less`, `sass` 等依赖

## 如何开发环境配置
1. 命令行下运行如下命令
```bash
# 设置 SITE_HOST 环境变量
# 旧有逻辑，应该统一放到 env 文件里方便些
export SITE_HOST="https://cook02.dev.pillowai.cn"
```
2. 在项目根目录 `cook-web` 下创建 env 文件 `.env.development.local` 或 `.env.local`
3. 文件内填入如下字段并设置合适的值(开发环境下会用于 `/api/config/c-cenv` 接口返回的结果)
```bash
  # Next.js 环境变量的命名规则可参考文档：https://nextjs.org/docs/app/guides/environment-variables
  NEXT_PUBLIC_BASEURL=
  NEXT_PUBLIC_UMAMI_SCRIPT_SRC=
  NEXT_PUBLIC_UMAMI_WEBSITE_ID=
  NEXT_PUBLIC_COURSE_ID=
  NEXT_PUBLIC_ALWAYS_SHOW_LESSON_TREE=
  NEXT_PUBLIC_APP_ID=
  NEXT_PUBLIC_ERUDA=
  NEXT_PUBLIC_LOGO_HORIZONTAL=
  NEXT_PUBLIC_LOGO_VERTICAL=
  NEXT_PUBLIC_ENABLE_WXCODE=,
  NEXT_PUBLIC_SITE_URL=
```
4. 运行 `npm run dev`

## 关于代码格式标准化
- 目前项目内混用有 2 空格和 4 空格，推荐统一 2 空格
  * 项目内文件用 2 空格的较多
  * 前端社区内这几年大多使用 2 空格

## 其它事项
- 统一 **用户相关逻辑**，用户注册、登录、登出、权限拦截等逻辑整理成一个模块，避免分散各处
- 短期内不要升级到 `Tailwind CSS V4`，之前微信的 WebView 不兼容 V4 里面用到的新特性 
- 目前用的包管理器是 `npm`, 换 `pnpm` 会提高不少每次编译打包时 `install` 依赖包的效率，不过设置稍微复杂一点
- 目前项目配置了 `less-loader`, 似乎不需要依赖这个
