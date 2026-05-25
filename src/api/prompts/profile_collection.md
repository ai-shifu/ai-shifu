# 任务
根据课程内容，为新学员按需采集系统变量生成自然、贴合课程语境的提问文案。

# 课程信息
- 课程标题：{course_title}
- 课程简介：{course_description}
- 课程关键词：{course_keywords}

# 需要采集的系统变量
{profile_variables}

# 课程摘要
<course_summary>
{course_summary}
</course_summary>

# 生成规则
- 只为“需要采集的系统变量”生成配置，不要补充其他变量。
- 每个问题都要简短、自然，像课程老师在对话中顺手了解学员信息。
- `question` 是正式向学员展示的提问。
- `placeholder` 是输入框提示，可以比 `question` 更短。
- `skip_label` 是跳过按钮文案，保持友好克制。
- 不要要求学员提供敏感个人信息。
- 不要输出 Markdown，不要输出解释。

# 输出格式
只输出严格 JSON：

{{
  "version": 1,
  "variables": {{
    "sys_user_background": {{
      "question": "string",
      "placeholder": "string",
      "skip_label": "string"
    }}
  }}
}}
