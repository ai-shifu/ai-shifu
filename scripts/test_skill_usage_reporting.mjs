import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

// Executes only synthetic fixtures in an in-memory PostgreSQL database.
// An optional module path allows the test-only dependency to live outside the repo.
const modulePath = process.argv[2];
const { PGlite } = await import(
  modulePath
    ? pathToFileURL(path.resolve(modulePath)).href
    : "@electric-sql/pglite"
);
const docPath = new URL(
  "../docs/references/skill-usage-reporting.md",
  import.meta.url,
);
const db = new PGlite();
await db.exec(`CREATE TABLE session (session_id uuid, website_id uuid, distinct_id varchar(50));
CREATE TABLE website_event (event_id uuid, session_id uuid, website_id uuid, created_at timestamptz, event_name text, event_type int, hostname text, tag text);
CREATE TABLE session_link (session_id uuid, website_id uuid, distinct_id text);
CREATE TABLE event_data (website_id uuid, website_event_id uuid, data_key text, string_value text, number_value numeric);`);
const site = "00000000-0000-0000-0000-000000000001";
let serial = 100;
let fixtureEvents = 0;
const uuid = () =>
  `00000000-0000-0000-0000-${String(serial++).padStart(12, "0")}`;
const noon = (day) => `${day}T04:00:00Z`;
async function event(
  account,
  day,
  {
    agent = "codex",
    operation = "course_list",
    outcome = "success",
    web = false,
    legacy = false,
    v2 = false,
    method = operation === "course_publish" || operation === "content_save"
      ? "POST"
      : "GET",
    eventType = web || v2 ? 1 : 2,
    tag = v2 ? "skill_api_request_v2" : null,
    propertyOverrides = {},
    omitProperties = [],
    duplicateProperty = null,
    sessionId = null,
    at = noon(day),
    host = web ? "cook.test" : "server.ai-shifu",
    website = site,
    sessionWebsite = website,
    name = web || v2
      ? null
      : legacy
        ? "external_course_creation_completed"
        : "skill_api_request_v1",
  } = {},
) {
  fixtureEvents++;
  const session = sessionId ?? uuid(),
    id = uuid();
  if (!sessionId) {
    await db.query("INSERT INTO session VALUES ($1,$2,$3)", [
      session,
      sessionWebsite,
      account,
    ]);
    // Several native identity links must not fan out aggregate request counts.
    for (const identity of [account, "excluded-old-link"])
      await db.query("INSERT INTO session_link VALUES ($1,$2,$3)", [
        session,
        sessionWebsite,
        identity,
      ]);
  }
  await db.query("INSERT INTO website_event VALUES ($1,$2,$3,$4,$5,$6,$7,$8)", [
    id,
    session,
    website,
    at,
    name,
    eventType,
    host,
    tag,
  ]);
  if (name === "skill_api_request_v1" || v2) {
    const properties = {
      skill_id: "ai-shifu-course-creator",
      skill_version_major: "v2",
      duration_ms: 12,
      ...(v2 ? { method } : {}),
      caller_agent: agent,
      operation,
      outcome,
      ...propertyOverrides,
    };
    const rows = Object.entries(properties).filter(
      ([key]) => !omitProperties.includes(key),
    );
    if (duplicateProperty)
      rows.push([duplicateProperty, properties[duplicateProperty]]);
    for (const [key, value] of rows) {
      await db.query("INSERT INTO event_data VALUES ($1,$2,$3,$4,$5)", [
        website,
        id,
        key,
        typeof value === "string" ? value : null,
        typeof value === "number" ? value : null,
      ]);
    }
  }
  return session;
}
// Account A first appears during the partial rollout day and must not be recohorted.
await event("fixture-A", "2026-10-01", { at: "2026-09-30T17:30:00Z" });
await event("fixture-A", "2026-10-02");
// Account B retries and switches Agents/sessions on the same complete day.
const retrySession = await event("fixture-B", "2026-10-02", {
  at: "2026-10-01T16:00:00Z",
});
await event("fixture-B", "2026-10-02", { v2: true, sessionId: retrySession });
await event("fixture-B", "2026-10-02", { agent: "cursor", v2: true });
await event("fixture-B", "2026-10-02", {
  agent: "unknown",
  v2: true,
  outcome: "failure",
});
await event("fixture-B", "2026-10-02", { web: true });
await event("fixture-B", "2026-10-03", { agent: "cursor" });
await event("fixture-B", "2026-10-09", { web: true, eventType: 2 });
await event("fixture-C", "2026-10-02", {
  agent: "historical-unrecognized-agent",
  operation: "content_save",
});
await event("fixture-C", "2026-10-03", { web: true });
await event("fixture-C", "2026-10-09", { agent: "unknown" });
// A failure-only account is in requests but no active-day or cohort denominator.
await event("fixture-D", "2026-10-02", {
  outcome: "failure",
  operation: "course_publish",
});
await event("fixture-E", "2026-11-02", { agent: "workbuddy" });
await event("fixture-F", "2026-10-27", { agent: "grok_bot" });
await event("fixture-F", "2026-10-28", {
  agent: "grok_bot",
  outcome: "failure",
});
await event("fixture-F", "2026-10-28", { web: true });
await event("fixture-G", "2026-10-02", { web: true });
// Exact timestamp tie is broken by event ID: WorkBuddy precedes Cursor.
await event("fixture-M", "2026-10-02", {
  agent: "workbuddy",
  operation: "course_get",
});
await event("fixture-M", "2026-10-02", {
  agent: "cursor",
  operation: "course_get",
});
// Ineligible rows must not leak into counts or source union.
await event("excluded-legacy", "2026-10-02", { legacy: true });
await event("excluded-anonymous", "2026-10-02", {
  web: true,
  host: "unlisted.test",
});
await event(null, "2026-10-02", { v2: true });
await event("", "2026-10-02");
await event("excluded-operation", "2026-10-02", {
  operation: "private-freeform",
});
await event("excluded-outcome", "2026-10-02", { outcome: "private-freeform" });
await event("excluded-end", "2026-11-03", { at: "2026-11-02T16:00:00Z" });
await event("excluded-before", "2026-10-01", { at: "2026-09-30T16:59:59Z" });
await event("excluded-other-site", "2026-10-02", {
  website: "00000000-0000-0000-0000-000000000002",
});
await event("excluded-session-site", "2026-10-02", {
  sessionWebsite: "00000000-0000-0000-0000-000000000002",
});
await event("excluded-pageview-kind", "2026-10-02", {
  eventType: 1,
  host: "cook.test",
});

// Historical v1 carries six producer fields, including the fixed Skill ID.
// Sharing the event name and backend hostname must not admit another Skill.
for (const options of [
  { propertyOverrides: { skill_id: "other-skill" } },
  { omitProperties: ["skill_id"] },
])
  await event("excluded-v1-skill", "2026-10-02", options);

// Malformed v2 contracts must not contribute requests, account-days, or cohorts.
for (const options of [
  { tag: null },
  { tag: "skill_api_request_v3" },
  { name: "unexpected-custom-event" },
  { name: "" },
  { eventType: 2 },
  { host: "unlisted.test" },
  { host: "cook.test" },
  { method: "POST" },
  { agent: "unrecognized-agent" },
  { operation: "freeform-operation" },
  { outcome: "freeform-outcome" },
  { omitProperties: ["method"] },
  { duplicateProperty: "operation" },
  { propertyOverrides: { skill_id: "other-skill" } },
  { propertyOverrides: { skill_version_major: "2.0.0" } },
  { propertyOverrides: { duration_ms: -1 } },
  { propertyOverrides: { duration_ms: 0.5 } },
  { propertyOverrides: { duration_ms: "12" } },
  { propertyOverrides: { duration_ms: null } },
  { propertyOverrides: { duration_ms: Infinity } },
  { propertyOverrides: { duration_ms: NaN } },
  { propertyOverrides: { secret_extra: "synthetic-disallowed" } },
  { propertyOverrides: { operation: 3 } },
])
  await event("excluded-v2", "2026-10-02", { v2: true, ...options });
// CLI markers and old stages never become Web activity, even on a Web host.
for (const name of [
  "skill_api_request_v1",
  "skill_api_request_v2",
  "external_course_creation_started",
  "external_course_creation_completed",
  "external_course_creation_failed",
  "external_course_publish_started",
  "external_course_publish_completed",
  "external_course_publish_failed",
])
  await event("excluded-web-marker", "2026-10-02", {
    web: true,
    eventType: 2,
    name,
  });
// A historical marker on another host is neither an eligible request nor Web traffic.
await event("excluded-v1-host", "2026-10-02", { host: "unlisted.test" });

const sqlBlock = fs
  .readFileSync(docPath, "utf8")
  .match(/```sql\n([\s\S]+?)\n```/);
assert(
  sqlBlock,
  "reporting documentation must contain its canonical SQL query",
);
const sqlTemplate = sqlBlock[1];
const base = {
  website_id: site,
  rollout_utc: "2026-09-30T17:00:00Z",
  complete_before_utc: "2026-11-02T16:00:00Z",
  report_start_day: "2026-10-02",
  web_hosts: "{cook.test}",
};
async function report(overrides = {}) {
  const inputs = { ...base, ...overrides };
  const sql = sqlTemplate.replace(
    /:'([a-z_]+)'/g,
    (_, key) => `'${inputs[key].replaceAll("'", "''")}'`,
  );
  const result = await db.query(sql);
  const output = Object.fromEntries(
    result.rows.map((row) => [row.report, row.rows]),
  );
  assert(
    !/fixture-|excluded-/.test(JSON.stringify(output)),
    "raw account identifiers must never be returned",
  );
  return output;
}
const full = await report();
const activity = (day, agent = "all", data = full) =>
  data.account_activity.find(
    (row) => row.day === day && row.caller_agent === agent,
  );
const cohort = (day, agent = "all", data = full) =>
  data.observed_cohorts.find(
    (row) => row.cohort_day === day && row.caller_agent === agent,
  );
const onOct2 = full.operations.filter((row) => row.day === "2026-10-02");
assert.equal(
  onOct2.reduce((sum, row) => sum + row.requests, 0),
  11,
);
assert.equal(
  onOct2.find(
    (row) =>
      row.operation === "course_list" &&
      row.outcome === "success" &&
      row.caller_agent === "codex",
  ).requests,
  5,
);
assert.equal(
  onOct2.find(
    (row) =>
      row.operation === "course_list" &&
      row.outcome === "success" &&
      row.caller_agent === "codex",
  ).accounts,
  2,
);
const totals = full.request_totals.find(
  (row) => row.day === "2026-10-02" && row.caller_agent === "all",
);
assert.deepEqual(totals, {
  day: "2026-10-02",
  caller_agent: "all",
  requests: 11,
  successful_requests: 9,
  accounts: 5,
  sessions: 10,
  v2_pageviews: 4,
});
assert.equal(
  onOct2.reduce((sum, row) => sum + row.successful_requests, 0),
  9,
);
assert.equal(
  onOct2.reduce((sum, row) => sum + row.v2_pageviews, 0),
  4,
);
assert(
  full.request_totals
    .filter((row) => row.day === "2026-10-02" && row.caller_agent !== "all")
    .reduce((sum, row) => sum + row.accounts, 0) > totals.accounts,
  "Agent account totals overlap; only the all row deduplicates accounts",
);
assert.equal(activity("2026-10-02").skill_dau, 4);
assert.equal(activity("2026-10-02").combined_dau, 5);
assert.equal(activity("2026-10-02", "codex").skill_dau, 2);
assert.equal(activity("2026-10-02", "cursor").skill_dau, 2);
assert.equal(activity("2026-10-02", "unknown").skill_dau, 1);
assert.equal(activity("2026-10-07").skill_rolling_7, null);
assert.equal(activity("2026-10-08").skill_rolling_7, 4);
assert.equal(activity("2026-10-08").combined_rolling_7, 5);
assert.equal(activity("2026-10-30").skill_rolling_30, null);
assert.equal(activity("2026-10-31").skill_rolling_30, 5);
assert.equal(activity("2026-10-31").combined_rolling_30, 6);
assert.equal(activity("2026-11-02").skill_dau, 1);
assert.equal(activity("2026-11-02").skill_rolling_7, 2);
assert.equal(activity("2026-11-02").skill_rolling_30, 3);
assert.equal(activity("2026-11-02").combined_rolling_30, 4);
const mature = cohort("2026-10-02");
assert.equal(mature.observed_new_skill_accounts, 3);
assert.equal(mature.d1_eligible_accounts, 3);
assert.equal(mature.d7_eligible_accounts, 3);
assert.equal(mature.skill_d1_accounts, 1);
assert.equal(mature.skill_d7_accounts, 1);
assert.equal(mature.any_d1_accounts, 2);
assert.equal(mature.any_d7_accounts, 2);
assert(Math.abs(Number(mature.skill_d1_rate) - 1 / 3) < 1e-12);
assert(Math.abs(Number(mature.any_d7_rate) - 2 / 3) < 1e-12);
assert.equal(cohort("2026-10-02", "workbuddy").observed_new_skill_accounts, 1);
assert.equal(cohort("2026-10-02", "cursor"), undefined);
assert.equal(cohort("2026-10-27").d1_eligible_accounts, 1);
assert.equal(cohort("2026-10-27").skill_d1_accounts, 0);
assert.equal(cohort("2026-10-27").any_d1_accounts, 1);
assert.equal(cohort("2026-10-27").d7_eligible_accounts, null);
for (const key of [
  "d1_eligible_accounts",
  "d7_eligible_accounts",
  "skill_d1_accounts",
  "skill_d7_accounts",
  "any_d1_accounts",
  "any_d7_accounts",
  "skill_d1_rate",
  "skill_d7_rate",
  "any_d1_rate",
  "any_d7_rate",
])
  assert.equal(cohort("2026-11-02")[key], null);
assert(
  !full.operations.some(
    (row) => row.day === "2026-10-01" || row.day === "2026-11-03",
  ),
);
assert(!full.observed_cohorts.some((row) => row.cohort_day === "2026-10-01"));
const late = await report({ report_start_day: "2026-10-03" });
assert.equal(cohort("2026-10-03", "all", late), undefined);
assert.equal(activity("2026-10-08", "all", late).skill_rolling_7, 4);
for (const overrides of [
  { complete_before_utc: "2026-11-02T15:59:59Z" },
  { complete_before_utc: "2026-09-30T16:00:00Z" },
  { web_hosts: "{cook.test,server.ai-shifu}" },
  { report_start_day: "2026-12-01" },
]) {
  const empty = await report(overrides);
  for (const rows of Object.values(empty)) assert.deepEqual(rows, []);
}
// Keep the SQL consumer's method pairs aligned with the backend producer.
const producerPath = new URL(
  "../src/api/flaskr/service/common/skill_request_analytics.py",
  import.meta.url,
);
const operationMethods = [
  ...fs
    .readFileSync(producerPath, "utf8")
    .matchAll(/\("[a-z_]+", "([A-Z]+)"\): "([a-z_]+)"/g),
].map(([, method, operation]) => ({ method, operation }));
assert.equal(operationMethods.length, 23);
for (const { method, operation } of operationMethods) {
  await event("fixture-method-contract", "2026-11-01", {
    v2: true,
    method,
    operation,
  });
  await event("excluded-method-contract", "2026-11-01", {
    v2: true,
    operation,
    method: method === "GET" ? "POST" : "GET",
  });
}
const withMethods = await report();
assert.deepEqual(
  withMethods.request_totals.find(
    (row) => row.day === "2026-11-01" && row.caller_agent === "all",
  ),
  {
    day: "2026-11-01",
    caller_agent: "all",
    requests: 23,
    successful_requests: 23,
    accounts: 1,
    sessions: 23,
    v2_pageviews: 23,
  },
);
assert.equal(activity("2026-11-01", "all", withMethods).skill_dau, 1);
// Canonical detect_agent.md v0.1.5 IDs and historical labels stay as stored.
const canonicalAgents = [
  "antigravity",
  "augment-cli",
  "claude-code",
  "cline",
  "codex",
  "cowork",
  "crush",
  "cue",
  "cursor",
  "cursor-cli",
  "devin",
  "doubao-work",
  "gemini-cli",
  "github-copilot",
  "goose",
  "grok-bot",
  "grok-build",
  "hermes-agent",
  "hi",
  "junie",
  "kilo-code",
  "kimi",
  "kiro",
  "manus",
  "muse",
  "openclaw",
  "opencode",
  "pi",
  "qwenwork",
  "replit",
  "sandbase-harness",
  "trae",
  "vtcode",
  "workbuddy",
  "zed",
];
const legacyAgents = [
  "codex",
  "claude_code",
  "cursor",
  "hermes",
  "openclaw",
  "workbuddy",
  "qoderwork",
  "grok_bot",
  "unknown",
];
assert.equal(canonicalAgents.length, 35);
for (const agent of [...canonicalAgents, "unknown"])
  await event("fixture-method-contract", "2026-11-01", { v2: true, agent });
for (const agent of legacyAgents)
  for (const v2 of [false, true])
    await event("fixture-method-contract", "2026-11-01", { v2, agent });
for (const agent of ["unlisted-agent", "codex_cli", "grok"])
  await event("excluded-catalog-agent", "2026-11-01", { v2: true, agent });
await event("fixture-method-contract", "2026-11-01", { web: true });
const withCatalog = await report();
const catalogRows = withCatalog.request_totals.filter(
  (row) => row.day === "2026-11-01",
);
assert.deepEqual(
  catalogRows.find((row) => row.caller_agent === "all"),
  {
    day: "2026-11-01",
    caller_agent: "all",
    requests: 77,
    successful_requests: 77,
    accounts: 1,
    sessions: 77,
    v2_pageviews: 68,
  },
);
assert.equal(catalogRows.length, 41);
for (const agent of [...canonicalAgents, ...legacyAgents]) {
  const row = catalogRows.find((row) => row.caller_agent === agent);
  assert(row, `stored Agent ID must remain queryable: ${agent}`);
  assert.equal(row.accounts, 1);
}
for (const [historical, canonical] of [
  ["qoderwork", "qwenwork"],
  ["hermes", "hermes-agent"],
  ["claude_code", "claude-code"],
  ["grok_bot", "grok-bot"],
]) {
  assert.equal(
    catalogRows.find((row) => row.caller_agent === historical).requests,
    2,
  );
  assert.equal(
    catalogRows.find((row) => row.caller_agent === canonical).requests,
    1,
  );
}
assert.equal(activity("2026-11-01", "all", withCatalog).skill_dau, 1);
assert.equal(activity("2026-11-01", "all", withCatalog).combined_dau, 1);
assert.equal(
  catalogRows
    .filter((row) => row.caller_agent !== "all")
    .reduce((sum, row) => sum + row.accounts, 0),
  40,
  "canonical and historical Agent labels overlap; aggregate accounts by ID",
);
console.log(
  JSON.stringify({
    postgresql: "PGlite",
    result: "passed",
    fixture_events: fixtureEvents,
    oct2_requests: 11,
    oct2_successful_requests: 9,
    oct2_sessions: 10,
    oct2_v2_pageviews: 4,
    oct2_skill_dau: 4,
    oct2_combined_dau: 5,
    mature_cohort: 3,
    skill_d1: 1,
    skill_d7: 1,
    any_d1: 2,
    any_d7: 2,
    oct31_rolling30: 5,
    nov2_rolling30: 3,
    canonical_agent_ids: 35,
    stored_agent_labels: 40,
    catalog_requests: 77,
    catalog_accounts: 1,
    raw_account_ids_returned: false,
  }),
);
await db.close();
