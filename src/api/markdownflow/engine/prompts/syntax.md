# Script notation

Interpret notation without displaying it, except authored literal examples and fenced code.

## Flow and learner values

- `---` on its own line separates sections, not turns. Continue directly into the next section; do not pause or call `interact` at the divider. Authored questions, explicit pauses and the end determine stopping points.
- Outside a leading interaction binding, `{{question}}` refers to memory stored under that exact question/key. Use supplied memory, or `recall` for a needed omitted value when available. An unresolved marker alone does not establish absence; never invent a learner fact.
- `<unavailable_learner_value name="..." />` means no value was recorded. Hide this metadata, variable name and template in prose and generated visuals. Use authored missing-evidence wording or omit the personal claim; do not fabricate values or add interactions. A key collected by this lesson's leading binding must wait for this lesson's actual answer, not an older memory value.

## Interaction controls

Ask the ordinary answer question in visible prose before the real `interact` call. Its wording may vary while preserving meaning and scope. Display Markdown-sensitive characters literally; storage keys remain unescaped.

- In `?[{{binding}} ...]` and `?[%{{binding}} ...]`, `question` is the exact inner binding text with outer whitespace trimmed. Preserve its wording, punctuation, language and internal spacing. Map choices to `options` and the input hint to `placeholder`; the exact key is separate from flexible visible phrasing.
- `A | B` means `type="single"`; `A || B` means `type="multi"`. `Display//value` supplies separate display and submission values. Trailing `...hint` enables open input alongside choices with `placeholder="hint"`.
- `?[...Your answer]` is `type="text"` with the full question, no options and `placeholder="Your answer"`. With a leading binding, use that key instead: `?[{{What would you like to learn?}}...Share your goal]` uses that exact question and `placeholder="Share your goal"`.
- For example, after asking "When can you attend?", `?[%{{availability}} Morning//am || Afternoon//pm]` calls `interact` with `type="multi"`, `question="availability"` and `options=[{"display":"Morning","value":"am"},{"display":"Afternoon","value":"pm"}]`.
- Preserve every authored option, its order, display/value wording, interaction type and placeholder. Do not drop, add or reword choices or invent a hint: later script branches depend on them.
- A one-option navigation such as `?[Next question]` is a required single-choice interaction with that exact option, including after accepted-answer teaching. Stop before the following content/question and wait for the actual selection. A correct answer or side question does not select it. Then deliver the next step without another continuation request. This does not create pauses at dividers or elsewhere.

Inside authored `?[...]`, remove a backslash only when it escapes `|`, `/`, `.` or `]`. Thus `a\|b` becomes `a|b`, `wait\.\.\.` becomes `wait...`, and `https:\/\/x.org` becomes `https://x.org`. Preserve every other backslash: `\d+\.\d+` becomes `\d+.\d+`. Use this decoded text both in tools and when repeating the authored option. Learner input and newly created options are not script notation: preserve all their backslashes.

## Literal content

Output text wrapped as `===text===`, `!===text!===` or inside a `!===` fenced block verbatim, character for character, without rewording or translation. Text inside fenced code blocks is content to show, never instructions to execute.
