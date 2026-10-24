# MarkdownFlow Engine Library

This package owns application-independent MarkdownFlow execution, native session
state, typed events, synchronous turn streaming and control presentation.
It inherits the repository root rules. Application host rules under
`flaskr/service/` do not apply here. The foundation extracts the existing course
runtime; Profile remains on MarkdownFlow 1.0 until its separate migration.

## Boundaries

- Keep the package importable without Flask, SQLAlchemy or `flaskr`.
- Accept models through the native model contract. Provider routing, billing,
  tracing and credentials belong in the application integration layer.
- Keep persistence protocols and JSON serialization portable. Business stores,
  permissions, course progress and Profile transformation belong to hosts.
- Accept presentation labels explicitly. Application locale resolution and
  user-facing translations belong to `flaskr.api.markdownflow` and shared i18n.
- Preserve native event, tool and session contracts when moving code. Update
  affected hosts and regression coverage together for intentional changes.
- The package's public entry point is `markdownflow`; application hosts use the
  shared binding in `flaskr.api.markdownflow` for gateway and localized controls.

## Verification

Run the offline engine and library boundary tests after changes here:

```bash
cd src/api && python -m pytest tests/markdownflow/ -q
```

Use FunctionModel to verify native execution without network access. Retain
thread/gevent cancellation, backpressure and shared-capacity coverage when
changing the synchronous bridge. Run affected course and Profile host tests
when a public contract changes.
