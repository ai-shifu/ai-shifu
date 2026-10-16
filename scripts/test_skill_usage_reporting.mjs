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
CREATE TABLE website_event (event_id uuid, session_id uuid, website_id uuid, created_at timestamptz, event_name text, event_type int, hostname text);
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
    eventType = web ? 1 : 2,
    at = noon(day),
    host = web ? "cook.test" : "server.ai-shifu",
    website = site,
    sessionWebsite = website,
    name = web
      ? null
      : legacy
        ? "external_course_creation_completed"
        : "skill_api_request_v1",
  } = {},
) {
  fixtureEvents++;
  const session = uuid(),
    id = uuid();
  await db.query("INSERT INTO session VALUES ($1,$2,$3)", [
    session,
    sessionWebsite,
    account,
  ]);
  await db.query("INSERT INTO website_event VALUES ($1,$2,$3,$4,$5,$6,$7)", [
    id,
    session,
    website,
    at,
    name,
    eventType,
    host,
  ]);
  if (name === "skill_api_request_v1")
    for (const [key, value] of Object.entries({
      caller_agent: agent,
      operation,
      outcome,
    })) {
      await db.query("INSERT INTO event_data VALUES ($1,$2,$3,$4,NULL)", [
        website,
        id,
        key,
        value,
      ]);
    }
}
// Account A first appears during the partial rollout day and must not be recohorted.
await event("fixture-A", "2026-10-01", { at: "2026-09-30T17:30:00Z" });
await event("fixture-A", "2026-10-02");
// Account B retries and switches Agents/sessions on the same complete day.
await event("fixture-B", "2026-10-02", { at: "2026-10-01T16:00:00Z" });
await event("fixture-B", "2026-10-02");
await event("fixture-B", "2026-10-02", { agent: "cursor" });
await event("fixture-B", "2026-10-02", {
  agent: "unknown",
  outcome: "failure",
});
await event("fixture-B", "2026-10-02", { web: true });
await event("fixture-B", "2026-10-03", { agent: "cursor" });
await event("fixture-B", "2026-10-09", { web: true, eventType: 2 });
await event("fixture-C", "2026-10-02", {
  agent: "unknown",
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
await event(null, "2026-10-02");
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
  9,
);
assert.equal(
  onOct2.find(
    (row) =>
      row.operation === "course_list" &&
      row.outcome === "success" &&
      row.caller_agent === "codex",
  ).requests,
  3,
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
console.log(
  JSON.stringify({
    postgresql: "PGlite",
    result: "passed",
    fixture_events: fixtureEvents,
    oct2_requests: 9,
    oct2_skill_dau: 4,
    oct2_combined_dau: 5,
    mature_cohort: 3,
    skill_d1: 1,
    skill_d7: 1,
    any_d1: 2,
    any_d7: 2,
    oct31_rolling30: 5,
    nov2_rolling30: 3,
    raw_account_ids_returned: false,
  }),
);
await db.close();
