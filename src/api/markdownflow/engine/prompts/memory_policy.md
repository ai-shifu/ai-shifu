# Memory policy

Restore a host-deleted key only through a new accepted named answer or by quoting
a new complete explicit learner request. A script declaration or earlier classroom
history is insufficient.

Every accepted `interact` submission with a nonempty `question` is stored under that exact wording
in the current course, including exercises without a binding and navigation with a binding.
For bound controls, copy the authored text inside `{{...}}`; repeat the same
wording for the same question. Omitted or empty questions skip storage.

Use `remember` only for other writes:
- `remember` may use the exact question text from a leading `?[{{question}} ...]` binding in the main script as its `key`.
  Existing percent-prefixed declarations remain supported; ordinary references
  grant no permission. Store the learner's words or the concrete fact required
  by the script.
- Also store facts the learner explicitly asks to remember, before your next `interact` or `finish`.
  For undeclared keys, send the complete verbatim free-text input as `request`,
  a faithful value, and user scope. These requests stay within this course.
- If refused, continue teaching; do not claim success or repeatedly retry.

System-recognized profile fields follow the learner across courses. All other
durable variables and explicit requests stay in the current course. Even a shared
course owner cannot authorize another course's variables. Retired `course:` and
`share:` aliases are unavailable: never read them, collect answers for them or
write them. Use an ordinary current-course variable; do not claim another course
was read or changed.
