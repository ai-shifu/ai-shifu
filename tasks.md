# MarkdownFlow Viewing Mode Tasks

## Scope

- Implement viewing mode integration for `learn/run` only.
- Keep the prompt text fixed in `src/api/prompts/view.md`.
- Runtime only substitutes:
  - `{container_size}`
  - `{device_type}`
- Frontend must send actual runtime device type and actual runtime container size.
- Listen mode is the priority path for container measurement.

## Prompt Template

- [ ] Keep `src/api/prompts/view.md` as the single source of truth for the viewing-mode prompt.
- [ ] Confirm template placeholders are exactly `{container_size}` and `{device_type}`.
- [ ] Reuse `src/api/flaskr/util/prompt_loader.py` instead of hardcoding prompt text in Python.

## Backend

- [ ] Add typed request support for `viewing_mode` in `src/api/flaskr/service/learn/learn_dtos.py`.
- [ ] Add a helper in `src/api/flaskr/service/learn/viewing_mode.py` to:
  - validate `container_size`
  - validate `device_type`
  - map canonical device values to prompt-facing text
  - load `view.md`
  - format the final prompt string
- [ ] Update `src/api/flaskr/service/learn/routes.py` to parse and forward `viewing_mode`.
- [ ] Update `src/api/flaskr/service/learn/runscript_v2.py` to pass `viewing_mode` into runtime context.
- [ ] Update `RunScriptContextV2` in `src/api/flaskr/service/learn/context_v2.py` to carry `viewing_mode`.
- [ ] Extend `MdflowContextV2` in `src/api/flaskr/service/learn/context_v2.py` to accept `viewing_mode_prompt`.
- [ ] Call `set_viewing_mode_prompt(...)` through `getattr(...)` for backward compatibility when the installed MarkdownFlow version does not expose the method.
- [ ] Keep runtime behavior unchanged when `viewing_mode` is missing or MarkdownFlow lacks `set_viewing_mode_prompt(...)`.

## Frontend Measurement

- [ ] Add runtime viewing-mode state in `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/NewChatComp.tsx`.
- [ ] Collect actual viewport size from:
  - `window.visualViewport`
  - fallback: `window.innerWidth` and `window.innerHeight`
- [ ] Measure actual render container size from the live chat surface using:
  - `ResizeObserver`
  - `getBoundingClientRect()`
- [ ] Define canonical device types:
  - `mobile`
  - `tablet`
  - `desktop`
- [ ] Derive device type from current frontend runtime state, including layout and mobile environment signals.

## Listen Mode Priority

- [ ] In listen mode, use the Reveal container bound to `chatRef` as the source of truth for `container_size`.
- [ ] Confirm the measured listen container reflects the actual runtime size after Reveal layout is mounted.
- [ ] Ensure the value sent to `run` is based on the latest measured listen container, not a fixed design size.

## Read Mode Support

- [ ] In read mode, use the scrollable chat content container as the source of truth for `container_size`.
- [ ] Keep the payload shape identical between read mode and listen mode.

## Request Integration

- [ ] Extend `getRunMessage(...)` typing in `src/cook-web/src/c-api/studyV2.ts` to include `viewing_mode`.
- [ ] Update `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/useChatLogicHook.tsx` to attach the latest `viewing_mode` to all `learn/run` requests.
- [ ] Update `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/AskBlock.tsx` to send the same `viewing_mode` payload.
- [ ] Format payload values as:
  - `container_size: "${width}*${height}px"`
  - `device_type: "mobile" | "tablet" | "desktop"`

## Fallback Behavior

- [ ] If the container is not measured yet, use viewport size as a temporary fallback.
- [ ] Once container measurement becomes available, subsequent `run` requests must use container size instead of viewport size.
- [ ] Avoid blocking initial `run` requests while waiting for the first stable measurement.

## Out of Scope for This Pass

- [ ] Do not change `/preview/<outline_bid>` yet.
- [ ] Do not add database fields or migrations for viewing-mode snapshots.
- [ ] Do not change follow-up ask-provider prompts outside the MarkdownFlow runtime path.

## Tests

- [ ] Add backend tests for prompt loading and formatting from `view.md`.
- [ ] Add backend tests for missing `viewing_mode`.
- [ ] Add backend tests for compatibility fallback when `set_viewing_mode_prompt(...)` does not exist.
- [ ] Add backend tests for successful invocation when `set_viewing_mode_prompt(...)` exists.
- [ ] Add frontend tests for `getRunMessage(...)` payload shape.
- [ ] Add frontend tests that verify `useChatLogicHook` sends measured `viewing_mode`.
- [ ] Add frontend tests that verify `AskBlock` sends the same `viewing_mode`.
- [ ] Add listen-mode tests to confirm the payload uses Reveal container size.
- [ ] Add fallback tests to confirm viewport is used before container measurement is ready.

## Verification

- [ ] Run relevant backend tests.
- [ ] Run relevant frontend tests.
- [ ] Verify newly generated listen-mode content does not contain:
  - `vmin`
  - `text-sm`
  - `text-xs`
- [ ] Verify generated mobile content respects minimum text size `text-base`.
- [ ] Verify generated content remains usable in a `16:9` layout.
- [ ] Verify desktop runtime is not regressed when `viewing_mode` is absent.
