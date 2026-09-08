# MarkdownFlow model arena

A manually executed evaluation script. Nothing in the application imports,
starts, schedules, or installs this tool. Its Python entry point, browser
renderer, npm dependencies, translations, and tests live in this directory.
It adds no API endpoint, database migration, background job, application package
dependency, or production model-call hook.

The evaluation deliberately exercises the existing course permission rules,
exact published rows, prompt composition, `MdflowContextV2`,
`PreviewElementRunAdapter`, `chat_llm`, and the official `markdown-flow-ui`
reading/slide components. These are dependencies of the script, rather than a
second implementation of the learning flow. The script freezes the comparison
inputs and owns only sampling, orchestration, capture, publication, and scoring.

| Stage                | Existing code exercised                                                                                  |
| -------------------- | -------------------------------------------------------------------------------------------------------- |
| Source authorization | Production course/user models and authoring permission normalization, using independent consistent reads |
| Prompt preparation   | `build_course_prompt` and `render_course_prompt_identity_variables`                                      |
| Generation           | `MdflowContextV2.process` and the original `chat_llm` provider/retry/metering path                       |
| Element conversion   | `RunScriptPreviewContextV2` and `PreviewElementRunAdapter`                                               |
| Visual output        | Official `ContentRender` and `Slide` components from the pinned UI package                               |

Install the renderer dependencies here, independently of Cook Web:

```sh
cd scripts/markdownflow-arena
npm ci
npx playwright install chromium
```

Use a Python environment with the repository's backend requirements, or install
`requirements.txt` into a dedicated virtual environment. Backend operations must
run in an explicitly configured environment with course and provider access.
No server needs to be started. From the repository root:

```sh
python scripts/markdownflow-arena/markdownflow_arena.py run --config /private/path/arena.json
python scripts/markdownflow-arena/markdownflow_arena.py run --resume /private/path/arena_RUN_ID
python scripts/markdownflow-arena/markdownflow_arena.py summarize --run-id arena_RUN_ID --run-root /private/path
```

Copy `example.json` to a private location before configuring a batch. Full
instructions and the Feishu contract are in the
[operator guide](../../docs/references/markdownflow-model-arena.md).
The [renderer guide](renderer/README.md) describes complete-page capture,
offline image caching, fonts, and browser limits.

Every model call runs in a separate worker process. The script temporarily
observes the production wrapper's existing provider iterator to retain finish
reasons and usage, including terminal chunks without text. The observer delegates
unchanged to the real functions and restores them on completion, failure, or
generator close. It never patches a running application service. Normal routing,
retry, tracing, and metering behavior still comes from `chat_llm`.

Run the tests manually, using a Python environment with pytest installed:

```sh
python -m pytest -q scripts/markdownflow-arena/arena_tests
cd scripts/markdownflow-arena
npm test
npm run smoke
npm run smoke:locales
```

These tests use the real MarkdownFlow context, element adapter, production
model wrapper, and browser components with controlled inputs. The provider
stream and database fixtures are synthetic; tests do not make paid requests.
Real runs complement this coverage with current permissions, configured model
routes, and full course outputs. An evaluation result is not a substitute for
all learner-facing end-to-end tests.
