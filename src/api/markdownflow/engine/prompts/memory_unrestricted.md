# Memory policy

Each accepted `interact` submission with a nonempty `question` is stored under that exact wording.
A leading `?[{{question}} ...]` binding uses the text inside the braces; later
`{{question}}` references must match it. Use `remember` for other facts the script
asks you to record or when the learner states a preference or request that should
shape the rest of the session.
