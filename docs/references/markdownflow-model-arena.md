# Local MarkdownFlow slide comparisons

The manually executed tool lives in `scripts/markdownflow-arena/`. It directly
uses production prompt composition, MarkdownFlow processing, preview element
adaptation, `chat_llm`, and the official `Slide` component. No application source,
routes, package dependencies, or startup paths are modified.

## Inputs and authorization

Copy the tool's `example.json` to a private directory and set `owner_phone`.
Snapshot reads resolve the same canonical account as normal phone login, apply
prompt-view permissions, and follow exact rows referenced by the published
structure. Draft content and publish-only grants are excluded. Prompt inheritance
uses the nearest effective published lesson/parent/course prompt.

Only slide-generation tasks are sampled: target instructions or effective
inherited instructions must request slides. Conditional slide-format guidance
alone, generic HTML, diagrams, formulas, and prose do not qualify. Selection is a
conservative text heuristic, recorded in the private snapshot and sample list;
it does not rewrite course instructions. Missing variables, static blocks, and
blocks requiring earlier conversation are skipped with reasons. Sampling uses a
fixed seed and covers different courses before reusing one. Insufficient eligible
cases fail clearly rather than filling the batch with other task types.

The default is twelve cases with a two-case smoke stage. The exact five model IDs
are `gemini-3.8-flash`, `doubao-seed-2-0-lite-260428`,
`deepseek-v4-flash-0731`, `qwen3.8-flash`, and `glm-5.3-flash`. Production catalog resolution must
match each exactly, retaining provider prefixes and version suffixes; missing or
ambiguous matches fail. Vendor letter casing may differ (for example, the
configured route `qwen/ZHIPU/GLM-5.3-Flash`); suffix comparison ignores letter
case while preserving the complete configured ID and version. Each model receives the same frozen document, target
block, inherited prompt, variables, locale, and context. Initial runtime message
hashes are checked across successful model calls.

## Running the script

Install the tool's Python requirements in an operator environment and run
`npm ci` and `npx playwright install chromium` in `scripts/markdownflow-arena/`.
The script's npm lock, browser dependencies, and display copy are self-contained.

From the repository root:

```sh
python scripts/markdownflow-arena/markdownflow_arena.py run --config /private/path/arena.json
python scripts/markdownflow-arena/markdownflow_arena.py run --resume /private/path/arena_RUN_ID
python scripts/markdownflow-arena/markdownflow_arena.py report --run-dir /private/path/arena_RUN_ID
```

`--smoke-only` stops after two cases. `--run-root` selects the private artifact
root. Default backend execution uses the repository's existing runtime
configuration without starting an HTTP server. For an operator-managed backend
environment, `backend_command` is an argument array transporting a JSON worker
request on stdin and returning its response on stdout. Every call starts a
separate worker process. Install the same script revision alongside the backend
source, requirements, `prompts/`, and application `i18n/` resources.

The tool observes provider metadata with process-local spies around the original
provider iterator. Spies delegate unchanged and restore the original functions on
completion, failure, or generator close. Normal retry, tracing, and metering still
run through `chat_llm`; no production callback extension is installed.

`renderer_command` optionally selects Node/Chromium and an offline image cache;
see the [renderer guide](../../scripts/markdownflow-arena/renderer/README.md).
`renderer_asset_hosts` is an explicit allowlist for source course assets. Model
output does not authorize additional remote hosts. Workers and renderers have
bounded configurable timeouts. Credentials stay in the operator environment.

## Local output and recovery

`comparison.html` embeds every verified slide PNG. Each model has a stable, shuffled A–E column. Names and exact routes appear
only after clicking the reveal button at the bottom; each prompt set occupies one row with all slide pages,
expandable source instructions, and click-to-enlarge images. Failed, truncated,
not-yet-generated, and text-only outputs have explicit cells. The report uses no
remote assets, forms, votes, external publication, or model preference scores.
Generated slide markup is rendered by the official component before capture;
untrusted prompts are escaped in the report and images are verified against
local recorded hashes. PDFs remain available in private render directories.

Schema version 2 freezes slide-only runs. `run --resume` rechecks current prompt
access and exact model routes, reuses completed generation, and retries local
rendering/report work separately. A generation or rendering smoke failure stops further model spending
and produces a partial page for inspection. A completed text-only answer is
shown as missing slides and does not block the remaining comparison cases. `--retry-failed` explicitly allows
repeating uncertain or failed paid requests, preserving earlier attempts.

`report` requires no backend access: it rebuilds a page from already-owned local
artifacts and does not claim to revalidate current course permissions. It also
accepts schema version 1 to display the slide subset of existing mixed batches;
legacy Feishu IDs and vote records are ignored and never read remotely. Legacy
mixed batches cannot resume generation as slide-only runs. Existing external
resources are not modified or deleted by this tool.

The snapshot, manifest, raw model output, and HTML contain private course data;
files use owner-only permissions and remain outside Git. Keep the HTML private
just like its source snapshots. To recover a report failure, fix missing or
modified local images and rerun `report`; model generation is never involved.

## Validation

Focused tests cover canonical-account permissions, published-version isolation,
prompt inheritance, slide-only sampling, identical model inputs, process-local
observer restoration, isolated execution, no-paid-retry recovery, complete offline
reports, escaped prompts, and modified-image rejection. Browser checks cover the
five-column layout, complete image decoding, prompt expansion, and zooming.
Main application integration coverage is retained; this does not replace every
learner-facing end-to-end test.

The performance panel in every cell uses saved call metadata, including failed
and truncated requests. It shows generation elapsed time, summed model-call
latency, input/output tokens, cache-hit tokens, and output tokens divided by
summed model-call seconds. This rate includes waiting and retries, so it is not
pure decoding throughput. Missing values remain unrecorded; a multi-call total
requires valid data from every call. No additional model requests are made.
