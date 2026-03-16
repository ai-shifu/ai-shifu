# MarkdownFlow Viewing Mode Integration for `learn/run`

## 1. Overview

This document describes how to integrate `mf.set_viewing_mode_prompt(...)` into the lesson runtime path (`/api/learn/shifu/<shifu_bid>/run/<outline_bid>`), so MarkdownFlow can generate layout-aware content for a mobile rendering container.

The initial target rendering constraints are:

- Device type: mobile
- Render container: `358*608px`
- Generated classes must not use `vmin`
- Minimum text size must be `text-base` (`16px`)
- `text-sm` and `text-xs` are forbidden
- Generated content should remain compatible with a `16:9` aspect ratio

The first iteration focuses on `learn/run`. Preview parity can be added in a follow-up step.

The viewing-mode prompt wording is fixed and should be managed centrally in:

- `src/api/prompts/view.md`

Only two values need runtime substitution:

- container size
- device type

These two values should come from actual frontend runtime measurement instead of hardcoded constants.

## 2. Background

The current runtime flow already creates MarkdownFlow in a single backend entry, which makes this change a good fit for centralized integration:

- Run API entry: `src/api/flaskr/service/learn/routes.py`
- Runtime orchestration: `src/api/flaskr/service/learn/runscript_v2.py`
- MarkdownFlow wrapper: `src/api/flaskr/service/learn/context_v2.py`

The frontend currently knows whether the page is in mobile layout, but it does not pass render container dimensions to the backend. The backend also does not currently attach any viewing-mode prompt to MarkdownFlow runtime generation.

## 3. Goals

- Add viewing-mode awareness to `learn/run` without scattering prompt logic across multiple runtime branches.
- Keep the frontend-to-backend contract structured and stable.
- Keep prompt wording fixed and centrally managed under `src/api/prompts/`.
- Make frontend payload reflect actual runtime device type and actual render container size.
- Preserve backward compatibility when the installed MarkdownFlow package does not yet expose `set_viewing_mode_prompt(...)`.
- Avoid database schema changes in the first iteration.

## 4. Non-Goals

- No redesign of frontend renderer behavior in `markdown-flow-ui`.
- No attempt to retroactively rewrite previously generated lesson history.
- No immediate change to author preview behavior unless explicitly enabled in a second phase.
- No change to follow-up `ask` response generation outside MarkdownFlow runtime blocks.

## 5. Existing Architecture

### 5.1 Frontend request path

All lesson runtime SSE requests currently go through:

- `src/cook-web/src/c-api/studyV2.ts` → `getRunMessage(...)`

Primary call sites:

- `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/useChatLogicHook.tsx`
- `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/AskBlock.tsx`

### 5.2 Backend runtime path

The runtime path is:

1. `routes.py` reads request payload and invokes `run_script(...)`
2. `runscript_v2.py` constructs `RunScriptContextV2`
3. `RunScriptContextV2` creates `MdflowContextV2`
4. `MdflowContextV2` constructs `MarkdownFlow(...)`

This makes `MdflowContextV2` the correct integration point for calling `set_viewing_mode_prompt(...)`.

### 5.3 History persistence behavior

Generated lesson blocks are persisted in `learn_generated_blocks` and later replayed by `/records/<outline_bid>`.

This means viewing-mode-aware generation is not only a transient rendering concern. Mobile-shaped output generated today may later be replayed on a desktop client.

## 6. Constraints and Risks

### 6.1 MarkdownFlow version mismatch risk

The repository declares:

- `src/api/requirements.txt` → `markdown-flow==0.2.55`

But the current local editable installation observed during inspection does not expose `set_viewing_mode_prompt(...)`.

Implementation must therefore:

- treat MarkdownFlow package alignment as a prerequisite for full effect
- use `getattr(..., "set_viewing_mode_prompt", None)` for safe fallback
- keep runtime behavior unchanged when the method is missing

### 6.2 Persisted-content tradeoff

Because runtime output is stored and replayed, the first iteration accepts this behavior:

- content generated for mobile viewing mode may later be replayed on desktop

This is acceptable for the first phase because:

- the user requirement is explicitly mobile-oriented
- no schema migration is needed
- the change remains low-risk operationally

If future product requirements demand device-specific replay, a later phase can add stored viewing-mode metadata per generated block.

### 6.3 Ask-flow limitation

When `input_type == "ask"`, runtime follows the separate ask provider path instead of MarkdownFlow block rendering.

Therefore this design only guarantees viewing-mode control for MarkdownFlow lesson content and interaction blocks produced by `learn/run`. It does not automatically constrain follow-up ask answers unless ask prompts are separately updated.

## 7. Proposed Design

### 7.1 API contract

Add a compact `viewing_mode` object to the `learn/run` request body.

Example:

```json
{
  "input": {
    "input": ["value"]
  },
  "input_type": "normal",
  "listen": false,
  "viewing_mode": {
    "container_size": "390*844px",
    "device_type": "mobile"
  }
}
```

Why pass only two fields instead of direct prompt text:

- keeps prompt ownership on the backend
- avoids frontend hardcoding prompt wording
- makes validation easier
- matches the actual prompt template inputs
- keeps future extension open for desktop/tablet variants

### 7.2 Prompt template management

The prompt text should not be assembled inline in runtime code. It should be loaded from the existing prompt-template mechanism.

Existing utilities:

- `src/api/flaskr/util/prompt_loader.py`
- `src/api/prompts/view.md`

Recommended template:

```md
- 现在可渲染的容器大小为'''{container_size}'''，用户的设备是'''{device_type}'''，请你根据当前的容器大小来渲染内容
- 如果用户的设备是移动端，所有的生成的class都不要包含vmin这样的单位，例如text-[2.5vmin]、h-[4vmin]，文字的尺寸最小为text-base，不能比text-base（也就是16px）更小，禁止出现text-sm，text-xs
- 生成的内容可以兼容16:9的宽高
```

Recommended backend helper:

- `src/api/flaskr/service/learn/viewing_mode.py`

Suggested responsibility:

- validate viewing mode payload
- normalize device type to prompt-facing text
- load `view.md`
- substitute `container_size` and `device_type`

Suggested helper:

- `build_viewing_mode_prompt(viewing_mode: ViewingModeDTO | None) -> str | None`

Recommended implementation shape:

```python
template = load_prompt_template("view")
prompt = template.format(
    container_size=viewing_mode.container_size,
    device_type=resolved_device_type_text,
)
```

The prompt content remains fixed in the template file. Runtime code only fills the two placeholders.

### 7.3 MarkdownFlow integration point

Extend `MdflowContextV2` to accept an optional `viewing_mode_prompt`.

Recommended behavior:

1. Construct `MarkdownFlow(...)` as today
2. Check whether `set_viewing_mode_prompt` exists
3. If the method exists and prompt is non-empty, call it
4. Continue current processing unchanged

Recommended compatibility pattern:

```python
set_viewing_mode_prompt = getattr(self._mdflow, "set_viewing_mode_prompt", None)
if callable(set_viewing_mode_prompt) and viewing_mode_prompt:
    set_viewing_mode_prompt(viewing_mode_prompt)
```

This mirrors the existing compatibility approach already used for `set_visual_mode(...)`.

### 7.4 Request propagation

Add request propagation through the following layers:

- `routes.py`
- `runscript_v2.py`
- `RunScriptContextV2`
- `MdflowContextV2`

Recommended additions:

- `ViewingModeDTO`
- `RunOutlineRequestDTO`

Suggested fields:

```python
class ViewingModeDTO(BaseModel):
    container_size: str
    device_type: Literal["mobile", "desktop", "tablet"]
```

The run route should parse this payload once and pass typed data downward.

## 8. Frontend Design

### 8.1 First-phase approach

The first phase should send actual measured values from the frontend runtime environment.

The backend prompt remains fixed. Only these two values vary at runtime:

- `container_size`
- `device_type`

Example payload:

```ts
{
  container_size: `${width}*${height}px`,
  device_type: 'mobile',
}
```

The payload format stays compact even though the underlying values come from live measurement.

### 8.2 Candidate frontend changes

Primary files:

- `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/NewChatComp.tsx`
- `src/cook-web/src/c-api/studyV2.ts`
- `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/useChatLogicHook.tsx`
- `src/cook-web/src/app/c/[[...id]]/Components/ChatUi/AskBlock.tsx`

Recommended behavior:

- measure actual viewport size in the browser
- measure actual render container size from the chat surface
- extend `getRunMessage(...)` body typing to include `viewing_mode`
- in the main lesson runtime flow, append the latest measured `viewing_mode`
- in `AskBlock`, pass the same payload for request consistency

### 8.3 Frontend measurement rules

Frontend should compute a runtime snapshot with:

- actual device type
- actual viewport/window size
- actual render container size

Recommended collection strategy:

1. Read viewport size from `window.visualViewport` when available.
2. Fall back to `window.innerWidth` and `window.innerHeight`.
3. Measure the actual run target container with `ResizeObserver` plus `getBoundingClientRect()`.
4. Convert the measured container width and height into `container_size`, for example `390*844px`.

Suggested frontend runtime shape:

```ts
type RuntimeViewingMode = {
  deviceType: 'mobile' | 'tablet' | 'desktop';
  windowSize: { width: number; height: number };
  containerSize: { width: number; height: number };
};
```

The request payload sent to the backend remains:

```ts
{
  viewing_mode: {
    container_size: `${containerWidth}*${containerHeight}px`,
    device_type: deviceType,
  },
}
```

### 8.4 Listen mode priority

The main reason frontend must measure actual size is listen mode.

Current listen mode behavior:

- `ListenModeRenderer` renders the Reveal surface through `chatRef`
- Reveal is initialized with `width: '100%'` and `height: '100%'`

This means the correct size to send to `learn/run` is not a fixed design size. It is the actual rendered listen container size at runtime.

Recommended listen-mode rule:

- when learning mode is `listen`, `container_size` must come from the Reveal container bound to `chatRef`

Recommended read-mode rule:

- when learning mode is `read`, `container_size` should come from the scrollable chat content container

### 8.5 Device type derivation

Frontend should derive a canonical device type before sending it to the backend.

Recommended priority:

1. use existing runtime environment signals such as `inMobile`
2. combine with current layout state (`frameLayout`) when distinguishing mobile vs tablet vs desktop
3. send canonical enum values:
   - `mobile`
   - `tablet`
   - `desktop`

The backend should remain responsible for mapping these enum values to prompt-facing text such as:

- `mobile` → `移动端`
- `tablet` → `平板端`
- `desktop` → `桌面端`

### 8.6 Fallback strategy

Because `learn/run` may fire before the container has a stable first measurement, frontend should keep a fallback strategy:

- prefer the latest measured container size
- if the container is not ready yet, use viewport size as temporary fallback
- once listen mode container measurement becomes available, subsequent `run` requests should use the container measurement instead of viewport size

## 9. Preview Alignment

The first version should target only `learn/run`.

However, if author preview is expected to match production runtime output, the same `viewing_mode` contract should later be added to:

- `POST /api/learn/shifu/<shifu_bid>/preview/<outline_bid>`

Candidate frontend file:

- `src/cook-web/src/components/lesson-preview/usePreviewChat.tsx`

Recommendation:

- keep preview out of the first implementation
- document the gap clearly
- add preview parity only after `learn/run` behavior is validated

## 10. Data and Migration Strategy

No database migration is required in the first iteration.

Reasoning:

- the request metadata is only used during generation
- existing history storage can remain unchanged
- operational risk and rollout cost stay low

Potential future schema extension if needed:

- add `viewing_mode_snapshot` to `LearnGeneratedBlock`

This should only happen if cross-device replay becomes a product issue.

## 11. Rollout Plan

### Phase 1

- Add compact `viewing_mode` payload to `learn/run`
- Load the fixed prompt from `src/api/prompts/view.md`
- Substitute only `container_size` and `device_type`
- Call `set_viewing_mode_prompt(...)` when available
- Frontend sends actual measured device type and actual container size

### Phase 2

- Add preview parity if needed

### Phase 3

- Reassess persisted-history tradeoff
- Add stored viewing-mode snapshot only if product requires device-aware replay

## 12. Testing Strategy

### 12.1 Backend unit tests

Add tests for:

- prompt loader and formatting output from `view.md`
- no-op behavior when `viewing_mode` is missing
- compatibility fallback when `set_viewing_mode_prompt(...)` is unavailable
- successful invocation when the method exists

Recommended test file:

- `src/api/tests/service/learn/test_context_v2.py`

### 12.2 Frontend tests

Add tests for:

- `getRunMessage(...)` payload includes `viewing_mode`
- lesson runtime path sends measured viewing mode values
- `AskBlock` path sends the same payload
- listen mode uses Reveal container size instead of a fixed constant
- viewport fallback works before container measurement stabilizes

### 12.3 Integration and smoke tests

Validate newly generated mobile lesson content against these expectations:

- no `vmin` classes
- no `text-sm`
- no `text-xs`
- minimum text size is `text-base`
- generated layout does not break in the actual measured mobile listen container
- `16:9` content remains usable inside the target mobile area

### 12.4 Regression checks

Confirm no functional regressions in:

- desktop lesson runtime
- listen mode runtime
- SSE stream behavior
- lesson history replay

## 13. Acceptance Criteria

- `learn/run` accepts an optional `viewing_mode` payload.
- Frontend measures actual device type and actual runtime viewport/container dimensions.
- On each `learn/run` request, the frontend sends `container_size` and `device_type` derived from the latest runtime measurement.
- In listen mode, `container_size` comes from the actual Reveal render container instead of a fixed design value.
- The backend loads the fixed prompt from `src/api/prompts/view.md`, fills the two placeholders, and attaches it to MarkdownFlow runtime generation.
- Runtime remains backward compatible if MarkdownFlow does not yet support `set_viewing_mode_prompt(...)`.
- Newly generated mobile runtime content follows the viewing constraints:
  - no `vmin`
  - no `text-sm`
  - no `text-xs`
  - minimum size `text-base`
  - compatible with `16:9`

## 14. Open Questions

- Should author preview adopt the same viewing mode in the same release, or remain a separate phase?
- Should ask-provider responses also receive mobile layout constraints, or is MarkdownFlow runtime alone sufficient for this requirement?
