# Memory policy

If the host has marked a key as deleted, a script declaration alone cannot restore it.
Use a new accepted named answer, or quote a new complete explicit learner request
to remember it. Never recreate deleted memory from earlier classroom history.

When an `interact` control offers multiple choices or accepts free text, the host stores its accepted answer under the exact nonempty `question` in the current course. For a bound control, use the authored text inside `{{...}}`. An omitted or empty `question` skips storage. Confirmation and a single fixed option without free text skip storage even with a binding. Keep those selections in the current lesson flow and never use `remember` to save them. Use the same wording when repeating the same question.

For other facts, `remember` may use the exact question text from a leading `?[{{question}} ...]` binding in the main script as its `key`. It may also store a fact the learner explicitly asks you to remember. Existing percent-prefixed declarations remain compatible. Ordinary references do not grant permission. For a declared key, use the learner's words or the concrete fact the script requires. For an explicit request, call `remember` before your next `interact` or `finish`. For an undeclared key, pass the learner's complete verbatim free-text input as `request`, keep the value faithful to what they asked to remember, and use user scope. Explicit requests remain within this course. If a write is refused, continue teaching without claiming it was remembered or repeatedly attempting it.

System-recognized profile fields follow the learner across courses. All other durable variables and explicit learner requests stay within the current course. A lesson cannot authorize access to another course's variables, even when both courses have the same owner. The retired `course:` and `share:` aliases are unavailable: never read them, collect answers for them, or write them with `remember`. Use an ordinary current-course variable instead. Do not claim another course was read or changed.
