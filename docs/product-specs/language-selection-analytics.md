---
title: Language Selection Analytics
status: implemented
owner_surface: frontend
last_reviewed: ""
canonical: true
---

# Language Selection Analytics

Transferred without changing event semantics from the delivered plan. A full
producer/consumer review date is not inferred from this document move.

- Business question: among deliberate language selections, how often is Spanish chosen, and on which entry surface? This informs whether to prioritize Spanish copy improvements and where to make language switching easier to find.
- Metric definition: weekly count of `user_language_selected` events with `selected_locale=es-ES`, divided by the weekly count of all `user_language_selected` events; segment both counts by `surface`. This is a share of deliberate selections, not a conversion rate from eligible views or a count of successfully persisted preferences.
- Event: `user_language_selected`.
- Actor and surface: any guest, learner, or teacher using the login selector (`login`), learner menu (`learner_menu`), or admin menu (`admin_menu`). Learner preview is included when its menu is shown. Internal and test traffic is not filtered by the producer; consumers must apply their existing traffic filters or state this limitation.
- Trigger: once in `LanguageSelect.onValueChange` when the user chooses a supported locale different from the selector's current value, before changing the interface language. Browser detection, account preference hydration, and a selection of the current locale are excluded.
- Count unit and deduplication: one accepted selector change. There is no persisted or session-wide deduplication; later deliberate changes count again. The current-value guard and in-flight target guard prevent same-language and rapid repeat selections from counting. A failed language change releases its in-flight guard for a retry.
- Correlation and privacy: no resource or user ID is attached. `selected_locale` is checked against the supported-locale inventory and `surface` is a fixed enum; the shared tracking path handles identity separately. No labels, text, URLs, or errors are included.
- Consumers: aggregate weekly language-selection report by selected locale and surface. No checked-in query or dashboard consumes this new event; it is additive and does not change historical event meanings.
- Verification: focused selector tests cover exact event name and payload, Spanish and other locales, all three surfaces, automatic/duplicate/unsupported selection exclusions, retry after a failed language change, and synchronous or asynchronous tracking failure without changing the selected language.

| Field             | Type   | Allowed values                               | Cardinality | Privacy class     | Why required                         |
| ----------------- | ------ | -------------------------------------------- | ----------- | ----------------- | ------------------------------------ |
| `selected_locale` | string | supported codes from `src/i18n/locales.json` | low         | non-personal enum | compare Spanish with other languages |
| `surface`         | string | `login`, `learner_menu`, `admin_menu`        | low         | non-personal enum | compare entry points                 |
