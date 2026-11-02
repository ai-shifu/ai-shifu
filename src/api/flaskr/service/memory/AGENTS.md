# Backend Service: memory

This module owns learner memory: course-scoped variable values and the global
rows that mirror system profile keys (`course_values.py`), course memory
listing and deletion (`course_memory.py`), reserved reference prefixes
(`course_references.py`), the settings-page writer (`settings_writer.py`), and
the runtime facade and reader the lesson and follow-up paths use
(`facade.py`, `reader.py`, `dtos.py`).

Entry files in this directory: `api.py`, `facade.py`, `reader.py`,
`course_values.py`, `settings_writer.py`.

## Do

- Read and write account-backed fields only through `flaskr.service.profile.api`.
- Keep the storage rules of `var_variable_values` in one place: custom keys are
  scoped to the course, system keys are global, and the newest live row wins.
- Let other services import `api.py` (or `dtos.py`), not the modules behind it.

## Avoid

- Do not let `flaskr.service.profile` import this package back; profile sits
  below memory.
- Do not commit inside the facade's writes; callers own the unit of work.

## Tests

`cd src/api && pytest tests/service/memory -q`
