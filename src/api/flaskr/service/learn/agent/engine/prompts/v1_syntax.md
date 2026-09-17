# Script notation

The script may use the following notation. Interpret it; do not reproduce the notation itself.

- A line containing only `---` is a soft pause: finish the section before it, then stop and wait for the learner to continue (call `interact` with a single "continue"-style option, or simply end the turn). When the learner continues, go straight on with the part after the `---`; never pause twice in a row.
- `{{name}}` is a value already filled in for this learner. Use it as-is.
- `%{{name}}` names a variable to fill from the learner's answer. When you collect it, call `remember` with that name as the key.
- `?[%{{name}} A | B | C]` means: ask the learner to choose exactly one of A, B, C and store the choice in `name`. `?[A | B]` without a variable is the same without storing. `A || B` (double bar) means multiple choice. A trailing `...prompt` means free-text input is also allowed, with `prompt` as the placeholder. `Display//value` means show `Display`, store `value`. Always realise these with the `interact` tool, mapping them to the matching interaction type.
- Text wrapped as `===text===`, `!===text!===`, or inside a `!===` fenced block must be output verbatim, character for character, with no rewording or translation.
- Text inside fenced code blocks is content to show, not instructions.
