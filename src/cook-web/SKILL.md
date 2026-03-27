# cook-web Skills

## 分层规范

- 放到 `SKILL.md`：跨页面、跨模块长期生效的基础约束与技能索引。
- 放到 `skills/xxx/SKILL.md`：面向具体场景的触发条件、落地步骤、验收要点。
- `SKILL.md` 不承载冗长排障步骤；步骤化内容必须下沉到专题 skill。

## 项目级通用约束

- URL 参数以单一真值为准：课节定位使用 `lessonid`，听课开关使用查询参数 `listen`。
- 流式聊天以 `element_bid` 作为渲染稳定键，兼容字段在统一数据归一化入口回填。
- 同一逻辑被两个以上文件复用时，优先抽离到共享 `utils/constants/hooks`。

## Skills 索引

- `skills/chat-layout-width-detection/SKILL.md`
- `skills/interaction-user-input-defaults/SKILL.md`
- `skills/deep-link-lessonid-routing/SKILL.md`
- `skills/chat-element-streaming/SKILL.md`
- `skills/chat-actionbar-ask-placement/SKILL.md`
- `skills/listen-mode-audio-streaming/SKILL.md`
- `skills/lesson-feedback-popup-timing/SKILL.md`
- `skills/module-augmentation-guardrails/SKILL.md`
- `skills/hook-contract-refactor-safety/SKILL.md`
- `skills/audio-debug-log-cleanup/SKILL.md`
- `skills/docker-npm-registry-fallback/SKILL.md`
