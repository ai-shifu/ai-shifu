# Account session analytics contract

Covers the two user-facing flows added for account session control: approving a
command-line client in the browser (`/login/device`), and reviewing or ending
sign-in sessions from the account menu.

Both are asynchronous workflows where a single signal cannot describe the
outcome: a prompt that is opened and abandoned looks identical to one that was
rejected unless the terminal states are recorded separately.

### device authorization

- Business question: when someone is asked to authorize a command-line client,
  how often do they complete it, how often do they refuse, and how often does
  the prompt go unanswered? A refusal rate that is not near zero would mean
  people are being shown requests they did not start.
- Metric definition: numerator is approval events (`device_auth_approved`);
  denominator is prompt exposure events (`device_auth_prompt_shown`) in the
  same calendar week, grouped by the shared `device_os`, `from_link`,
  `host_platform`, `skill_id`, and `skill_version` fields.
  Abandonment is the residual, `1 - (approved + denied) / shown`, and is
  meaningful only because exposure is counted separately. Without a request
  identifier, this calculation is aggregate and cannot be presented as a
  row-level join.
- Event name(s): `device_auth_prompt_shown`, `device_auth_approved`,
  `device_auth_denied`.
- Actor and surface: the signed-in user, on the `/login/device` page only.
- Trigger: exposure fires once per resolved pending request, from a
  post-commit effect. The outcomes fire only after the backend confirms the
  decision, never on the click itself.
- Population: signed-in users. A signed-out visitor is redirected to sign in
  first and emits nothing.
- Count unit: one pending authorization request.
- Deduplication: keyed on the pairing code held in a ref, so re-renders and a
  second effect pass cannot inflate the denominator. Scope is one mounted page.
- Correlation: aggregate dimensions only. The pairing code and Skill handoff
  ID are deliberately absent from every payload, so these events cannot be
  joined to a specific request.
- Consumers: the periodic Skill acquisition and journey report compares the
  authorization funnel by host platform, Skill, and version.
- Compatibility: the event names are unchanged. Skill dimensions are additive
  payload fields; ordinary device requests use `unattributed` for all three.
- Verification: `src/web/src/app/login/device/page.test.tsx` asserts the
  exposure fires exactly once, that pairing and handoff identifiers stay out
  of the payload,
  that link-opened and manually entered outcomes retain the same `from_link`
  dimension as their exposure, that outcomes fire on confirmation, and that a
  failed decision emits no outcome.

| Field           | Type    | Allowed values                                                                   | Cardinality | Privacy class | Why required                                                    |
| --------------- | ------- | -------------------------------------------------------------------------------- | ----------- | ------------- | --------------------------------------------------------------- |
| `device_os`     | string  | `android`, `chromeos`, `ios`, `linux`, `macos`, `other`, `unknown`, or `windows` | low         | non-personal  | tells whether refusals cluster on one platform                  |
| `from_link`     | boolean | true/false                                                                       | low         | non-personal  | separates prompts opened from the link from codes typed by hand |
| `host_platform` | string  | `workbuddy`, `doubao`, `lobster`, `codex`, `direct`, `unattributed`              | low         | non-personal  | compares host-platform funnels                                  |
| `skill_id`      | string  | `ai-shifu-course-creator`, `unattributed`                                        | low         | non-personal  | identifies the supported Skill funnel                           |
| `skill_version` | string  | validated Skill version or `unattributed`                                        | bounded     | non-personal  | finds version-specific drop-offs                                |

### session management

- Business question: do people use session control at all, and when they do,
  are they ending one session they recognise as wrong or clearing everything?
  The second case suggests they could not tell which session was suspicious.
- Metric definition: numerator is distinct users emitting any revoke event in
  a calendar month; denominator is distinct users emitting
  `session_list_opened` in the same month. Track the split between single and
  bulk revocations as a share of revoking users, not of events.
- Event name(s): `session_list_opened`, `session_revoked`,
  `session_revoked_others`.
- Actor and surface: the signed-in user, from the account menu on the learner
  and creator surfaces. The surface is carried on the open event.
- Trigger: open fires when the menu entry is activated; revoke events fire
  only after the backend confirms, so a failed revoke emits nothing.
- Population: signed-in users. The entry is hidden while signed out.
- Count unit: users for the adoption metric; events for the single-versus-bulk
  split.
- Deduplication: none within a session. Reopening the dialog is a genuine
  repeat of the action and should count again.
- Correlation: none. Session identifiers name a live credential's row and are
  deliberately absent from every payload.
- Consumers: none yet.
- Compatibility: additive; three new names.
- Verification:
  `src/web/src/components/Settings/SessionManagerModal.test.tsx`
  asserts that outcomes fire only on confirmed revocations, that a failed
  revocation emits nothing, and that no session identifier reaches a payload.

| Field     | Type   | Allowed values     | Cardinality | Privacy class | Why required                                                 |
| --------- | ------ | ------------------ | ----------- | ------------- | ------------------------------------------------------------ |
| `surface` | string | `learner`, `admin` | low         | non-personal  | shows which surface people manage sessions from              |
| `source`  | string | `web`, `cli`, ``   | low         | non-personal  | distinguishes ending a browser session from ending a CLI one |
