# Frontend workflow navigation

Read the nearest `AGENTS.md` for project rules. This entry point routes tasks
by scenario; detailed procedures belong in focused skills. The complete
[skill catalog](skills/README.md) is derived from each skill's metadata.

| Scenario                                                            | Start here                                                                                                                                                                                                                                     |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Chat streaming, typewriter or timeout                               | [Element streaming](skills/chat-element-streaming/SKILL.md)                                                                                                                                                                                    |
| Preview typewriter or speaker helpers                               | [Preview gate](skills/chat-element-streaming/SKILL.md#preview-typewriter-and-speaker-helpers)                                                                                                                                                  |
| Learner preview header, banner or content offsets                   | [Preview header layout](skills/listen-mode-slide-mobile-integration/SKILL.md#learner-preview-header-layout)                                                                                                                                    |
| Follow-up entry, messages or mode-dependent visibility              | [Ask placement and shared state](skills/chat-actionbar-ask-placement/SKILL.md)                                                                                                                                                                 |
| Learning-mode initialization, URL overrides or restored preferences | [Initialization and storage](skills/listen-mode-audio-streaming/SKILL.md#learning-mode-initialization-and-restored-preferences)                                                                                                                |
| Narration, buffering or audio backfill                              | [Listen-mode audio](skills/listen-mode-audio-streaming/SKILL.md)                                                                                                                                                                               |
| Mobile slide layout or fullscreen overlays                          | [Mobile integration](skills/listen-mode-slide-mobile-integration/SKILL.md), [fullscreen portals](skills/fullscreen-dialog-portal/SKILL.md)                                                                                                     |
| Admin filters, tables or pagination                                 | [Filter layout](skills/admin-filter-layout/SKILL.md), [table system](skills/admin-table-visual-system/SKILL.md)                                                                                                                                |
| Interaction defaults or repeatable system actions                   | [Input defaults](skills/interaction-user-input-defaults/SKILL.md), [system buttons](skills/chat-system-interaction-button-overrides/SKILL.md)                                                                                                  |
| Lesson deep links or responsive mode                                | [Lesson routing](skills/deep-link-lessonid-routing/SKILL.md), [width detection](skills/chat-layout-width-detection/SKILL.md)                                                                                                                   |
| Shared hooks, library types or controlled values                    | [Hook contracts](skills/hook-contract-refactor-safety/SKILL.md), [module augmentation](skills/module-augmentation-guardrails/SKILL.md), [controlled sync](skills/markdownflow-controlled-sync/SKILL.md)                                        |
| Error boundaries, build runtime or loading feedback                 | [Error fallback](skills/app-error-boundary-display/SKILL.md), [Node runtime](skills/next-build-node-runtime/SKILL.md), [loading dots](skills/shared-loading-dots/SKILL.md), [async confirmation](skills/async-confirm-dialog-loading/SKILL.md) |

For billing terminology and display rules, use the owning
[billing design](../../docs/billing-subscription-design.md) and shared components.
For a preview/debug business failure before the first content element, use the
existing `usePreviewChat` error path to replace the loading placeholder with the
backend message. Preserve the structured business code on the rendered error
item and let `LessonPreview` choose a directed action; do not branch on message
text. `src/components/lesson-preview/usePreviewChat.test.ts` covers the loading
replacement and retained business code.

Add a focused skill only for a recurring workflow. Its `SKILL.md` must declare
`name` and a concrete trigger in `description`; keep reference details there,
then update the catalog in the same change. Until the separate documentation-
harness generator change lands, these catalogs are maintained manually.
