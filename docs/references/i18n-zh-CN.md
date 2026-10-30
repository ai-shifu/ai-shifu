---
title: Simplified Chinese product terminology
status: current
owner_surface: shared
last_reviewed: 2026-10-30
canonical: true
---

# Simplified Chinese product terminology

- 中文用户界面和中文文档中，不要使用“创作者”泛指产品角色。
- 泛指课程编写用户、老师账号、计费账号、钱包、订阅、通知和运营账号列表中的用户时，使用“老师”。
- 指定课程的所有者使用“课程负责人”；在已有课程上下文中，更自然时可以简称“负责人”。
- 英文和法文遵循同样的角色区分：通用角色使用 `teacher` / `enseignant`；指定课程的所有者仍可使用 `creator` / `créateur`。
- 技术契约保持不变：除非专门的兼容性迁移明确要求，不重命名 key、符号、路由、数据库字段、`creator_bid`、`Creator Bid` 或已有的 `creator*` 标识符。

相关流程见[国际化指南](i18n.md)。

## 记忆、问题与回答

功能整体称为“记忆”，其中的内容以“问题和回答”组织。根据当前操作表达含义，
个人资料、显示操作和课程范围继续使用各自场景中的自然说法。

| 场景 | 用语 |
| --- | --- |
| 功能总称 | 记忆 |
| 内容结构 | 问题、回答，对应现有 key、value |
| 课程创作、问题填写与校验 | 问题，例如“请填写问题”“这个问题已存在” |
| 老师的学习模拟面板 | 记忆；填写模拟回答 |
| 个人资料 | 使用昵称、背景与偏好、授课语言等具体标签；填写提示使用“填写{label}” |
| 学习模拟中的显示操作 | 隐藏此项、隐藏未使用项、显示全部；隐藏不表示删除已保存的信息 |
| 学员查看或删除本课程内保存的信息 | 课程记忆、删除这条课程记忆 |

“课程记忆”是按课程范围限定的名称，可能包括已保存的回答和学员主动要求记住的信息。
问题和回答是内容的展示结构，不证明曾经发生过对应的提问与作答。没有可靠来源证据时，
不要把每条记忆都描述为学员原始作答，也不要为其补造问题、来源或作答次数。

产品表达不改变技术契约：问题可以使用完整问句作为现有 key，回答沿用现有 value。
同一课程内相同 key 继续共用当前值；更改 key 后按不同条目处理，不自动关联旧回答。
实际展示的提问文字与绑定 key 仍按现有流程处理，不把历史 key 自动改写成问句。
API、数据库、缓存、翻译 key、运行时提示词和埋点中的技术标识保持原样。
环境变量、通知模板变量等技术语境继续使用其原有术语。

## 乌尔都语术语对照

以下保留国际化审查使用的中文原词与乌尔都语译文。

| Chinese source meaning | Urdu | Context |
| --- | --- | --- |
| 老师 | استاد | Generic teacher role |
| 课程负责人 | کورس کے ذمہ دار | Owner of a specific course |
| 游客 | مہمان صارف | Guest account, not a tourist |
| 积分套餐 / 积分包 | کریڈٹ پلان / کریڈٹ پیک | Subscription plan versus top-up pack |
| 日套餐 | روزانہ پلان | Daily plan, not a meal |
| 周期积分 | ہر بلنگ مدت کے کریڈٹس | Credits granted for each billing period |
| 邀请人 / 被邀请人 | دعوت دینے والا / مدعو شخص | Inviter versus invitee |
| 登录设备 | لاگ ان شدہ آلات | Session/device list, not a login action |
| 注销账户 / 结束会话 | اکاؤنٹ حذف کریں / سیشن ختم کریں | Account deletion versus session revocation |
| 词元 | ٹوکن | Billing tokens, not words |
