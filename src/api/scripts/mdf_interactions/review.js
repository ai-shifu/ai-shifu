"use strict";

const { runs, context, labels, focus } = JSON.parse(document.querySelector("#payload").textContent);
const byId = (id) => document.getElementById(id);
const text = (key, values = {}) => labels[key].replace(/\{(\w+)\}/g, (_, name) => values[name]);
const keys = (object) => Object.keys(object ?? {});
const groups = new Map();
const checks = new Map();
const annotations = new Map();
const storagePrefix = "mdf-interaction-review-v1/";
const automaticStatuses = keys(labels.automatic);
const manualStatuses = keys(labels.manual);
const proseJudgments = {
  prose_question: ["question_judgment", "asked"],
  prose_meaning: ["meaning_judgment", "covered"],
};
const family = (criterion) => criterion.split("[")[0];
const criterionName = (criterion) => labels.criteria[family(criterion)] ?? criterion;
const annotationKey = (entry) => JSON.stringify([
  entry.run_id, entry.case_id, entry.repeat, entry.stage, entry.criterion,
]);
const runName = (run) => run.model ?? text("replay");
const contextFor = (group) => Object.hasOwn(context, group.caseId) ? context[group.caseId] : undefined;
const titleFor = (group) => contextFor(group)?.title ?? group.caseId;
let browserStorage = true;

for (const run of runs) {
  for (const row of run.results) {
    const id = JSON.stringify([row.case_id, row.repeat]);
    if (!groups.has(id)) {
      groups.set(id, { id, caseId: row.case_id, repeat: row.repeat, rows: new Map(), checks: [] });
    }
    const group = groups.get(id);
    const caseLevel = { stage: 0, criteria: row.criteria };
    const stages = new Map([...row.steps, ...row.unreached_steps, caseLevel].map((step) => [step.stage, step]));
    group.rows.set(run.id, { row, stages });
    for (const step of stages.values()) {
      for (const [criterion, status] of Object.entries(step.criteria)) {
        const identity = { run_id: run.id, case_id: row.case_id, repeat: row.repeat, stage: step.stage, criterion };
        const key = annotationKey(identity);
        const check = { identity, key, status };
        group.checks.push(check);
        checks.set(key, check);
      }
    }
  }
}

function isAnnotation(entry) {
  return entry && typeof entry.run_id === "string" && typeof entry.case_id === "string" &&
    Number.isInteger(entry.repeat) && entry.repeat > 0 && Number.isInteger(entry.stage) && entry.stage >= 0 &&
    typeof entry.criterion === "string" && (entry.verdict === "" || manualStatuses.includes(entry.verdict)) &&
    typeof entry.note === "string" && entry.note.length <= 4000 && Boolean(entry.verdict || entry.note.trim());
}

try {
  for (const key of checks.keys()) {
    const saved = localStorage.getItem(storagePrefix + key);
    if (!saved) continue;
    let entry;
    try {
      entry = JSON.parse(saved);
    } catch {
      continue;
    }
    if (isAnnotation(entry) && annotationKey(entry) === key) annotations.set(key, entry);
  }
} catch {
  browserStorage = false;
}

function node(tag, content, className) {
  const element = document.createElement(tag);
  if (content !== undefined) element.textContent = content;
  if (className) element.className = className;
  return element;
}

function badge(label, style) {
  return node("span", label, `tag ${style ?? ""}`);
}

function plain(value) {
  if (value === undefined) return text("missing");
  if (value === null || (Array.isArray(value) && !value.length)) return text("none");
  if (value === "") return text("emptyString");
  if (typeof value === "boolean") return text(value ? "yes" : "no");
  return typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
}

function raw(value) {
  return node("pre", typeof value === "string" ? value : JSON.stringify(value, null, 2));
}

function details(title, contents, expanded = false) {
  const box = node("details", undefined, "source");
  box.open = expanded;
  box.append(node("summary", title), ...contents);
  return box;
}

function fields(entries) {
  const list = node("dl", undefined, "kv");
  for (const [label, value] of entries) {
    const field = node("div");
    const display = node("dd");
    display.append(value instanceof Node ? value : plain(value));
    field.append(node("dt", label), display);
    list.append(field);
  }
  return list;
}

function table(headers, rows, className) {
  const grid = node("table", undefined, className);
  const heading = grid.createTHead().insertRow();
  for (const label of headers) {
    const th = node("th", label);
    th.scope = "col";
    heading.append(th);
  }
  const body = grid.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    for (const cell of row) tr.insertCell().textContent = cell;
  }
  return grid;
}

function reportStatistics() {
  const tables = [];
  for (const run of runs) {
    const counts = new Map();
    for (const check of checks.values()) {
      if (check.identity.run_id !== run.id) continue;
      const name = family(check.identity.criterion);
      if (!counts.has(name)) counts.set(name, { automatic: {}, human: {} });
      const count = counts.get(name);
      count.automatic[check.status] = (count.automatic[check.status] ?? 0) + 1;
      const verdict = annotations.get(check.key)?.verdict;
      if (verdict) count.human[verdict] = (count.human[verdict] ?? 0) + 1;
    }
    const view = node("section", undefined, "stats-scroll");
    view.append(node("h3", runName(run)));
    view.append(table(
      [text("criterion"), ...automaticStatuses.map((status) => `${text("auto")} ${labels.automatic[status]}`),
        ...manualStatuses.map((status) => `${text("human")} ${labels.manual[status]}`)],
      [...counts].map(([name, count]) => [criterionName(name),
        ...automaticStatuses.map((status) => count.automatic[status] ?? 0),
        ...manualStatuses.map((status) => count.human[status] ?? 0)]),
      "stats-table",
    ));
    tables.push(view);
  }
  byId("counts").replaceChildren(...tables);
}

function updateStorageStatus() {
  byId("storage-status").textContent = text(browserStorage ? "saved" : "unsaved", { count: annotations.size });
  byId("export").disabled = !annotations.size;
}

function setAnnotation(key, entry) {
  if (entry) annotations.set(key, entry);
  else annotations.delete(key);
  try {
    if (entry) localStorage.setItem(storagePrefix + key, JSON.stringify(entry));
    else localStorage.removeItem(storagePrefix + key);
  } catch {
    browserStorage = false;
  }
}

function pending(check) {
  const verdict = annotations.get(check.key)?.verdict;
  return verdict === "uncertain" || (check.status === "needs_review" && !verdict);
}

function matchesFilters(check) {
  const criterion = byId("criterion-filter").value;
  if (criterion && family(check.identity.criterion) !== criterion) return false;
  switch (byId("view-filter").value) {
    case "pending": return pending(check);
    case "failures": return check.status === "failed";
    case "notEvaluated": return check.status === "not_evaluated";
    case "annotated": return annotations.has(check.key);
    default: return true;
  }
}

function selectedCases() {
  const query = byId("search").value.toLowerCase().trim();
  return [...groups.values()].filter((group) => (
    `${titleFor(group)} ${group.caseId}`.toLowerCase().includes(query) && group.checks.some(matchesFilters)
  ));
}

const address = new URLSearchParams(location.hash.slice(1));
let active = groups.get(JSON.stringify([address.get("case"), Number(address.get("repeat") || 1)])) ??
  [...groups.values()].find((group) => group.caseId === focus) ?? groups.values().next().value;
let stage = address.has("stage") ? Number(address.get("stage")) : 1;

function renderCases(visibleGroups) {
  byId("case-counts").textContent = text("caseCounts", { count: visibleGroups.length });
  const buttons = visibleGroups.map((group) => {
    const button = node("button", undefined, "case-button");
    const isActive = group === active;
    button.setAttribute("aria-current", String(isActive));
    const failures = group.checks.filter((check) => check.status === "failed").length;
    const unresolved = group.checks.filter(pending).length;
    button.append(node("span", titleFor(group)), node("small", `${group.caseId} · ${text("repeat", { number: group.repeat })}`));
    if (failures || unresolved) {
      const summary = node("div", undefined, "badges");
      if (failures) summary.append(badge(`${failures} ${text("failures")}`, "failed"));
      if (unresolved) summary.append(badge(`${unresolved} ${text("pending")}`, "needs_review"));
      button.append(summary);
    }
    button.addEventListener("click", () => {
      active = group;
      stage = group.checks.find(matchesFilters)?.identity.stage ?? 1;
      render();
      byId("cases").querySelector('[aria-current="true"]')?.focus();
    });
    return button;
  });
  byId("cases").replaceChildren(...buttons);
}

function stageLabel(number) {
  return number ? text("stage", { number }) : text("caseLevel");
}

function authoredStepFor(group, number) {
  return contextFor(group)?.steps[number - 1];
}

function actionCard(modelSteps, authoredStep) {
  const action = authoredStep?.action ?? modelSteps.find((step) => step?.action)?.action;
  if (!action) return null;
  const box = node("section", undefined, "learner-action");
  box.append(node("h3", `${text("learnerAction")} · ${text(action)}`));
  const data = [];
  if (authoredStep?.values?.length) data.push([text("values"), authoredStep.values.join("\n")]);
  if (authoredStep?.text != null) data.push([text("inputText"), authoredStep.text]);
  if (authoredStep?.reload || modelSteps.some((step) => step?.reloaded)) data.push([text("reload"), true]);
  if (data.length) box.append(fields(data));
  return box;
}

function stageStatus(step) {
  if (!step?.outcome) return badge(text("unreached"), "not_evaluated");
  return badge(labels.outcomes[step.outcome] ?? step.outcome);
}

function showControl(control, position) {
  const box = node("section", undefined, "control");
  box.append(badge(text("controlNumber", { number: position }), ""), " ",
    badge(labels.controlTypes[control.type] ?? control.type));
  if (control.title) box.append(node("p", control.title, "question-title"));
  if (control.options.length) {
    box.append(table([text("optionLabel"), text("optionValue")], control.options));
  }
  box.append(fields([[text("binding"), control.variable], [text("placeholder"), control.placeholder]]));
  box.append(details(text("rawControls"), [raw(control.controls)]));
  return box;
}

function judgeEvidence(judgment, verdictKey) {
  const box = node("section");
  box.append(node("h4", text("judges")));
  if (judgment.previous_question) {
    box.append(fields([[text("previousQuestion"), judgment.previous_question]]));
  }
  if (judgment.reason) box.append(node("p", judgment.reason));
  const yes = verdictKey === "asked" ? "judgeYes" : "judgeMeaningYes";
  const no = verdictKey === "asked" ? "judgeNo" : "judgeMeaningNo";
  for (const vote of judgment.decisions ?? []) {
    const verdict = vote[verdictKey] === true ? yes : vote[verdictKey] === false ? no : "judgeUnsure";
    const item = node("div", undefined, "judge");
    item.append(node("code", vote.model), badge(vote.error ?? text(verdict)));
    if (vote.reason) item.append(node("p", vote.reason));
    box.append(item);
  }
  return box;
}

function criterionEvidence(criterion, step, expected, offline) {
  const name = family(criterion);
  const reached = step.outcome !== undefined;
  if (name.startsWith("question.")) {
    const attribute = name.slice("question.".length);
    const want = attribute === "asked_before" ? expected?.asked_before : expected?.question?.[attribute];
    return [want, step.question?.[attribute]];
  }
  if (name === "question_count") {
    return [expected ? expected.question_count ?? Number(expected.outcome === "interaction") : undefined, step.questions?.length];
  }
  if (proseJudgments[name]) {
    const [judgmentKey, verdictKey] = proseJudgments[name];
    return [expected?.[name], step[judgmentKey]?.[verdictKey]];
  }
  if (name === "narrated_controls") {
    return [expected?.narrated_control ? [expected.narrated_control] : [], step.narrated_controls];
  }
  if (name === "retryable_error") return [expected ? expected.retryable_error ?? false : undefined, step.retryable_error];
  if (name === "continuation_limit") return [false, step.continuation_limit_reached];
  const proseRule = { prose_contains: "atLeastOnce", prose_once: "exactlyOnce", prose_excludes: "absent" }[name];
  if (proseRule) {
    const index = Number(criterion.match(/\[(\d+)\]/)?.[1]);
    const phrases = [...expected?.[name] ?? []];
    if (name === "prose_once" && offline) phrases.push(...expected?.replay_prose_once ?? []);
    const phrase = phrases[index];
    if (phrase === undefined) return [undefined, undefined];
    const wanted = `${text(proseRule)}\n${phrase}`;
    if (!reached) return [wanted, undefined];
    const count = phrase ? step.prose.split(phrase).length - 1 : Array.from(step.prose).length + 1;
    return [wanted, text("occurrenceCount", { count })];
  }
  return [expected?.[name], step[name]];
}

function humanForm(check, position, marker) {
  const wrap = node("div", undefined, "human-form");
  const verdict = node("select", undefined, "verdict-select");
  const note = node("textarea");
  const labelId = `${check.identity.run_id}-${check.identity.stage}-${position}`;
  verdict.id = `${labelId}-verdict`;
  note.id = `${labelId}-note`;
  note.maxLength = 4000;
  note.placeholder = text("notePlaceholder");
  verdict.append(new Option(text("chooseVerdict"), ""), ...manualStatuses.map((status) => new Option(labels.manual[status], status)));
  const entry = annotations.get(check.key);
  verdict.value = entry?.verdict ?? "";
  note.value = entry?.note ?? "";
  const verdictLabel = node("label", text("reviewChoices"));
  verdictLabel.htmlFor = verdict.id;
  const noteLabel = node("label", text("note"));
  noteLabel.htmlFor = note.id;
  wrap.append(verdictLabel, verdict, noteLabel, note);
  const save = () => {
    const newEntry = verdict.value || note.value.trim()
      ? { ...check.identity, verdict: verdict.value, note: note.value }
      : null;
    setAnnotation(check.key, newEntry);
    marker.hidden = !newEntry;
    marker.className = `tag ${verdict.value}`;
    marker.textContent = `${text("human")} ${labels.manual[verdict.value] ?? text("chooseVerdict")}`;
    byId("notice").hidden = true;
    updateStorageStatus();
    renderCases(selectedCases());
    if (byId("statistics").open) reportStatistics();
  };
  verdict.addEventListener("change", save);
  note.addEventListener("input", save);
  return wrap;
}

function criterionList(group, run, step, expected) {
  const section = node("section");
  section.append(node("h3", text("criterion")));
  const items = group.checks.filter((check) => check.identity.run_id === run.id && check.identity.stage === stage);
  const priority = ["needs_review", "failed", "passed", "not_evaluated"];
  items.sort((a, b) => priority.indexOf(a.status) - priority.indexOf(b.status));
  for (const [index, check] of items.entries()) {
    const name = check.identity.criterion;
    const item = node("details", undefined, "criterion");
    item.dataset.criterion = name;
    const summary = node("summary", criterionName(name));
    const manual = annotations.get(check.key);
    const humanTag = badge(`${text("human")} ${labels.manual[manual?.verdict] ?? text("chooseVerdict")}`, manual?.verdict);
    humanTag.hidden = !manual;
    summary.append(badge(labels.automatic[check.status] ?? check.status, check.status), humanTag);
    item.open = check.status === "failed" || pending(check) ||
      (Boolean(byId("criterion-filter").value) && matchesFilters(check));
    item.append(summary, node("code", name, "criterion-key"));
    if (stage) {
      const [wanted, actual] = criterionEvidence(name, step, expected, run.mode === "offline");
      item.append(fields([[text("expected"), wanted], [text("actual"), actual]]));
      const [judgmentKey, verdictKey] = proseJudgments[name] ?? [];
      if (step[judgmentKey]) item.append(judgeEvidence(step[judgmentKey], verdictKey));
    }
    section.append(item);
    item.append(humanForm(check, index, humanTag));
  }
  return section;
}

function traceCards(step) {
  const cards = [];
  const turnList = step.turns?.map((turn, index) => {
    const title = text("engineTurn", { number: index + 1, outcome: labels.outcomes[turn.outcome] ?? turn.outcome });
    const evidence = [[text("prose"), turn.prose]];
    if (turn.prose !== turn.engine_prose) evidence.push([text("beforeFilter"), turn.engine_prose]);
    return details(title, [fields(evidence)]);
  });
  cards.push(turnList ? details(text("engineTurns"), turnList) : fields([[text("legacyTurns"), step.turn_outcomes]]));
  if (!step.model_calls) {
    cards.push(node("p", text("legacyCalls"), "muted"));
    return cards;
  }
  if (step.model_calls.length) {
    const calls = step.model_calls.map((call) => {
      const report = node("div", undefined, "traces");
      for (const retry of call.retry_feedback ?? []) {
        report.append(details(text("retryFeedback") + (retry.tool ? ` · ${retry.tool}` : ""), [raw(retry.message)], true));
      }
      for (const part of call.parts ?? []) {
        const label = part.tool ? text("toolArguments", { tool: part.tool }) : text("modelText");
        report.append(details(label, [raw(part.tool ? part.arguments : part.text)]));
      }
      if (call.error) report.append(fields([[text("errors"), call.error]]));
      return details(text("modelCall", { number: call.number }), [report]);
    });
    cards.push(details(text("modelCalls"), calls));
  }
  return cards;
}

function modelPanel(group, run, authored) {
  const box = node("article", undefined, "model-panel");
  const head = node("header", undefined, "model-heading");
  const item = group.rows.get(run.id);
  const step = item?.stages.get(stage);
  const row = item?.row;
  head.append(node("p", `${text(run.mode === "live" ? "live" : "replay")} · ${run.id.slice(0, 8)}`, "muted"), node("h3", runName(run)));
  if (row) {
    const tone = row.status.endsWith("failure") ? "failed" : row.status === "first_attempt_pass" ? "passed" : row.status;
    head.append(badge(labels.statuses[row.status], tone));
    if (stage) head.append(" ", stageStatus(step));
  }
  box.append(head);
  if (!step) {
    box.append(node("p", text(row ? "unreached" : "missingRun"), "muted"));
    return box;
  }
  const expected = step.expected ?? (run.mode === "offline" ? authored?.replay_expected : null) ?? authored?.expected;
  if (step.outcome) {
    const prose = node("div", undefined, "prose");
    // The generator renders sanitized Markdown. Model HTML is represented as escaped text.
    if (step.prose.trim()) prose.innerHTML = step.rendered_prose;
    else prose.textContent = text("none");
    const lesson = node("section");
    lesson.append(node("h3", text("prose")), prose, details(text("rawProse"), [raw(step.prose)]));
    box.append(lesson);
    const controls = node("section");
    controls.append(node("h3", text("controls")));
    if (!step.questions.length) controls.append(node("p", text("none"), "muted"));
    step.questions.forEach((control, index) => controls.append(showControl(control, index + 1)));
    box.append(controls);
    if (step.narrated_controls.length) {
      box.append(details(text("narrated"), step.narrated_controls.map(raw), true));
    }
  }
  if (step.outcome) {
    box.append(fields([
      [text("available"), step.pending], [text("retries"), step.retries],
      [text("continuations"), step.automatic_continuations], [text("errors"), step.errors.join("\n") || null],
    ]));
  }
  box.append(criterionList(group, run, step, expected));
  if (step.outcome) {
    const prior = step.memory_before ?? (stage === 1 ? contextFor(group)?.memory : item.stages.get(stage - 1)?.memory);
    box.append(details(text("memory"), [fields([
      [text("memoryBefore"), prior === undefined ? undefined : raw(prior)],
      [text("memoryAfter"), raw(step.memory)],
      [text("memoryUpdates"), raw(step.memory_updates)],
    ])], Boolean(step.memory_updates.length)));
    box.append(...traceCards(step));
  }
  if (stage) {
    const { rendered_prose, ...rawStep } = step;
    box.append(details(text("rawStep"), [raw(rawStep)]));
  }
  const { results, ...configuration } = run;
  const { steps, ...caseSummary } = row;
  box.append(details(text("reportDetails"), [raw(configuration)]), details(text("caseEvidence"), [raw(caseSummary)]));
  return box;
}

function render({ preferMatchingStage = false } = {}) {
  const visibleGroups = selectedCases();
  if (!visibleGroups.includes(active)) active = visibleGroups[0];
  renderCases(visibleGroups);
  if (!active) {
    byId("case-view").replaceChildren(node("p", text("emptyCases"), "muted"));
    return;
  }
  const caseContext = contextFor(active);
  const matchedStages = new Set(active.checks.filter(matchesFilters).map((check) => check.identity.stage));
  const stages = [...new Set(active.checks.map((check) => check.identity.stage))].sort((a, b) => a - b);
  if (!stages.includes(stage) || (preferMatchingStage && !matchedStages.has(stage))) {
    stage = matchedStages.values().next().value ?? stages[0];
  }
  const nextAddress = new URLSearchParams({ case: active.caseId, repeat: active.repeat, stage });
  history.replaceState(null, "", `#${nextAddress}`);

  const heading = node("header", undefined, "case-heading");
  heading.append(node("h2", titleFor(active)));
  heading.append(node("p", `${active.caseId} · ${text("repeat", { number: active.repeat })}`, "muted case-meta"));
  if (caseContext) {
    const sources = [["teachingPrompt", caseContext.teaching_prompt], ["coursePrompt", caseContext.course_prompt], ["initialMemory", caseContext.memory]];
    for (const [label, value] of sources) {
      if (value !== null) heading.append(details(text(label), [raw(value)]));
    }
  } else {
    heading.append(node("p", text("noContext"), "warn"));
  }
  const nav = node("nav", undefined, "stages");
  nav.setAttribute("aria-label", text("stages"));
  for (const number of stages) {
    const button = node("button", stageLabel(number));
    button.setAttribute("aria-current", String(stage === number));
    const unresolved = active.checks.filter((check) => check.identity.stage === number && pending(check)).length;
    if (unresolved) button.append(" ", badge(`${unresolved} ${text("pending")}`, "needs_review"));
    button.addEventListener("click", () => {
      stage = number;
      render();
      byId("case-view").querySelector('.stages [aria-current="true"]')?.focus();
    });
    nav.append(button);
  }
  const authored = authoredStepFor(active, stage);
  const action = actionCard([...active.rows.values()].map((row) => row.stages.get(stage)), authored);
  const panels = node("div", undefined, "models");
  for (const run of runs) panels.append(modelPanel(active, run, authored));
  const parts = [heading, nav];
  if (action) parts.push(action);
  parts.push(panels);
  byId("case-view").replaceChildren(...parts);
}

function updateFilter() {
  const visible = selectedCases();
  if (!visible.includes(active)) active = visible[0];
  stage = active?.checks.find(matchesFilters)?.identity.stage ?? 1;
  render();
}

function say(message, warning = false) {
  const notice = byId("notice");
  notice.hidden = false;
  notice.classList.toggle("warn", warning);
  notice.textContent = message;
}

function exportAnnotations() {
  const payload = { schema_version: 1, annotations: [...annotations.values()] };
  const file = new Blob([JSON.stringify(payload, null, 2) + "\n"], { type: "application/json" });
  const link = node("a");
  link.href = URL.createObjectURL(file);
  link.download = "interaction-review-annotations.json";
  link.click();
  const url = link.href;
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  say(text("exported", { count: annotations.size }));
}

async function importAnnotations(event) {
  const [file] = event.target.files;
  event.target.value = "";
  if (!file) return;
  try {
    const payload = JSON.parse(await file.text());
    if (payload.schema_version !== 1 || !Array.isArray(payload.annotations) || !payload.annotations.every(isAnnotation)) {
      throw new Error("Invalid annotations");
    }
    const entries = new Map(payload.annotations.map((entry) => [annotationKey(entry), entry]));
    if (entries.size !== payload.annotations.length) throw new Error("Duplicate annotations");
    const totals = { count: 0, conflicts: 0, unmatched: 0 };
    for (const [key, entry] of entries) {
      const check = checks.get(key);
      const existing = annotations.get(key);
      if (!check) totals.unmatched += 1;
      else if (!existing) {
        setAnnotation(key, { ...check.identity, verdict: entry.verdict, note: entry.note });
        totals.count += 1;
      } else if (entry.verdict !== existing.verdict || entry.note !== existing.note) totals.conflicts += 1;
    }
    say(text("imported", totals), Boolean(totals.conflicts || totals.unmatched));
    updateStorageStatus();
    if (byId("statistics").open) reportStatistics();
    render({ preferMatchingStage: true });
  } catch {
    say(text("invalidImport"), true);
  }
}

document.title = text("title");
for (const element of document.querySelectorAll("[data-label]")) element.textContent = text(element.dataset.label);
const caseCount = new Set([...groups.values()].map((group) => group.caseId)).size;
byId("report-counts").textContent = text("reportCounts", { runs: runs.length, cases: caseCount });
byId("search").placeholder = text("search");
byId("import-file").setAttribute("aria-label", text("fileInput"));
byId("view-filter").append(...["all", "pending", "failures", "notEvaluated", "annotated"].map((value) => new Option(text(value), value)));
const criteria = [...new Set([...checks.values()].map((check) => family(check.identity.criterion)))].sort();
byId("criterion-filter").append(new Option(text("allCriteria"), ""),
  ...criteria.map((name) => new Option(`${criterionName(name)} · ${name}`, name)));
byId("search").addEventListener("input", updateFilter);
byId("view-filter").addEventListener("change", updateFilter);
byId("criterion-filter").addEventListener("change", updateFilter);
byId("statistics").addEventListener("toggle", () => {
  if (byId("statistics").open) reportStatistics();
});
byId("import").addEventListener("click", () => byId("import-file").click());
byId("import-file").addEventListener("change", importAnnotations);
byId("export").addEventListener("click", exportAnnotations);
updateStorageStatus();
render();
