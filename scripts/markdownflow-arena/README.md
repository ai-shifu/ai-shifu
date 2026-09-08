# MarkdownFlow slide comparison

A manually executed script that compares the five specified models on real
published slide-generation prompts. It writes one offline `comparison.html`:
one anonymously labeled model (A–E) per column, one frozen prompt set per row, with every captured slide
page visible. Click an image to enlarge it or expand a row's prompt details.
Images are embedded, so the page opens directly from disk without a server.

Model columns use a stable shuffled order per batch. Names and exact routes are
hidden until the reader clicks the reveal button at the bottom of the page. Each
cell shows recorded generation time, model-call time, input/output/cache tokens,
and average output tokens per second, including failed work. The speed is output
tokens divided by total model-call time (including waiting and retries), not pure
decoding speed. Missing or invalid measurements display as unrecorded; partial
usage across multiple calls is not presented as a complete total.

The script calls the main application implementation for generation and rendering:

| Stage              | Existing implementation                                                                        |
| ------------------ | ---------------------------------------------------------------------------------------------- |
| Authorization      | Production course/user models and permission normalization, using consistent independent reads |
| Prompt preparation | `build_course_prompt` and `render_course_prompt_identity_variables`                            |
| Generation         | `MdflowContextV2.process` and the original `chat_llm` routing, retries, tracing, and metering  |
| Element conversion | `RunScriptPreviewContextV2` and `PreviewElementRunAdapter`                                     |
| Slide rendering    | The official `Slide` component from the pinned `markdown-flow-ui` package                      |

The tool owns sampling, isolated worker processes, checkpoints, image capture,
and the comparison page. It adds no API endpoint, application dependency, service,
scheduled job, Feishu operation, voting, or scoring. Application source and builds
remain independent of this directory.

## Setup and manual execution

Use a Python environment with `requirements.txt` installed. Backend operations
need an explicitly configured environment with course and model access; no
application server needs to start. Install browser dependencies separately:

```sh
cd scripts/markdownflow-arena
npm ci
npx playwright install chromium
```

Copy `example.json` to a private path and configure the authorized owner's phone,
fixed learner variables, and any backend transport. From the repository root:

```sh
python scripts/markdownflow-arena/markdownflow_arena.py run --config /private/path/arena.json
python scripts/markdownflow-arena/markdownflow_arena.py run --resume /private/path/arena_RUN_ID
python scripts/markdownflow-arena/markdownflow_arena.py report --run-dir /private/path/arena_RUN_ID
```

`run` defaults to twelve slide cases and starts with two smoke cases. It samples
only published generation blocks with explicit slide intent in their target or
effective inherited prompt. It skips prose, formula/diagram-only tasks, missing
variables, and blocks needing earlier conversation. It preserves the original
prompts: surrounding narration is not rewritten, but only slide elements are
rendered and compared. A model returning only text is shown as “no slides”.
Truncated or failed work stays visible as a status in its model's cell.

`report` uses only saved results, makes no backend/model/network calls, and does
not change frozen prompts or outputs. It also reads legacy mixed-batch manifests,
selecting their slide rows; `run --resume` requires the current slide-only schema.
Completed model calls survive render/report failures. Use `--retry-failed` only
when intentionally authorizing another request for a failed or uncertain result.

The HTML contains private course titles and expandable prompts. Keep it with the
private run artifacts. See the [operator guide](../../docs/references/markdownflow-model-arena.md)
for configuration, exact routes, isolation, and recovery.

## Verification

```sh
python -m pytest -q scripts/markdownflow-arena/arena_tests
cd scripts/markdownflow-arena
npm test
npm run smoke
npm run smoke:locales
```

Tests exercise the real MarkdownFlow context, preview adapter, production model
wrapper, and official browser components with controlled fixtures. Real runs
also exercise configured model routes and published course inputs. This supplies
integration coverage for those main-flow paths, while the full learner-facing
end-to-end suite remains separate.
