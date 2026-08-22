// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let FIELDS = [];
let META = {};

// The four component states get colour, because the whole page turns on telling two of them apart.
const STATE_CLASS = {
  present_complete: "st-ok",
  present_not_measurable: "st-nm",
  absent: "st-ab",
  not_required: "st-nr",
};

function row(f, cell) {
  const tr = document.createElement("tr");
  const v = cell && cell.value;
  const span = cell && cell.span;
  const vtxt = v === undefined ? "not checked yet" : (v === null || v === "" ? "not stated" : v);
  const empty = v === undefined || v === null || v === "";
  tr.innerHTML =
    '<td class="n"></td><td class="v' + (empty ? " empty" : "") + '"></td>' +
    '<td class="s' + (span ? "" : " none") + '"></td>';
  tr.children[0].textContent = f.name;
  tr.children[1].textContent = vtxt;
  if (!empty && STATE_CLASS[v]) tr.children[1].classList.add(STATE_CLASS[v]);
  tr.children[2].textContent = span ? ("§ " + span.section)
    : (cell && cell.spannable === false ? "n/a — fixed value" : "—");
  return tr;
}

function draw(fields) {
  const body = $("rows");
  body.textContent = "";
  FIELDS.forEach((f) => body.appendChild(row(f, fields ? fields[f.name] : undefined)));
  if (!fields) { $("k-filled").textContent = "— filled"; $("k-missing").textContent = "— not stated";
                 $("k-span").textContent = "— with a span"; return; }
  const vals = FIELDS.map((f) => fields[f.name] || {});
  const filled = vals.filter((c) => c.value !== null && c.value !== undefined && c.value !== "");
  $("k-filled").textContent = filled.length + " filled";
  // pupil_age is legitimately null on some plans — the plan may simply not state it. The label says
  // "not stated" rather than "not found", because what the panel knows is that the reply carried
  // nothing, not why.
  $("k-missing").textContent = (FIELDS.length - filled.length) + " not stated";
  const spannable = vals.filter((c) => c.spannable !== false && c.value);
  $("k-span").textContent = vals.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
}

const OUTCOME_TEXT = {
  complete: "COMPLETE — every component the rulebook requires is present and measurable",
  components_missing: "COMPONENTS MISSING — a required component is not in this plan at all",
  not_measurable: "NOT MEASURABLE — every component is there, and one cannot be measured against",
  undetermined: "UNDETERMINED — the plan does not carry what the check needs",
};

function drawDecided(outcome, reason, missing, unmeasurable, status, flag) {
  const v = $("c-outcome");
  v.textContent = outcome == null ? "—" : (OUTCOME_TEXT[outcome] || outcome);
  v.className = outcome == null ? "" : ("vd vd-" + outcome);
  $("c-reason").textContent = reason || "—";
  // ⚠︎ TWO DIFFERENT BLANKS, AND SAYING SO IS THE POINT. Before a check has run there is no list
  // because nothing has been asked; after one, an empty list means the rulebook found none of that
  // kind — which on this panel is the good news and must not read as a missing answer.
  const list = (arr, none) => (outcome == null ? "—" : (arr && arr.length ? arr.join(", ") : none));
  $("c-missing").textContent = list(missing, "none — every required component is in the plan");
  $("c-unmeas").textContent = list(unmeasurable,
    "none — every required component states what the rulebook asks for");
  $("c-unmeas").className = (outcome != null && unmeasurable && unmeasurable.length) ? "st-nm" : "";
  $("c-status").textContent = status == null ? "—" : status;
  $("c-flag").textContent = (flag === null || flag === undefined)
    ? "not computed — one of the two values the rule needs was missing"
    : (flag ? "YES — not complete and already in effect. This is the plan to open first."
            : "no — nothing here needs a row on today's worklist");
  $("c-flag").className = flag ? "hold" : "";
}

function block(box, heading, rows) {
  const d = document.createElement("div");
  d.className = "mxb";
  const t = document.createElement("div"); t.className = "mxh"; t.textContent = heading;
  d.appendChild(t);
  rows.forEach(([a, b]) => {
    const r = document.createElement("div"); r.className = "mxr";
    const k = document.createElement("span"); k.className = "mxk"; k.textContent = a;
    const val = document.createElement("span"); val.textContent = b;
    r.appendChild(k); r.appendChild(val); d.appendChild(r);
  });
  box.appendChild(d);
}

function stateTable() {
  const box = $("states");
  box.textContent = "";
  (META.states || []).forEach((key) => {
    const m = (META.state_meanings || {})[key] || {};
    block(box, key, [["means", m.means || ""], ["wrong here costs", m.costs || ""]]);
  });
  const p = document.createElement("p");
  p.className = "mxn";
  p.textContent = "A component state describes the plan's own section. The plan OUTCOME is a "
    + "different vocabulary, computed from all seven states in pure code: "
    + Object.keys(META.outcome_meanings || {}).map((k) => k + " — "
        + META.outcome_meanings[k]).join("  ·  ");
  box.appendChild(p);
}

function rulebookTable(m) {
  const box = $("rulebook");
  box.textContent = "";
  block(box, "Conditional rule", [["transition age", String(m.transition_age)
    + " — " + m.transition_age_note]]);
  (m.rules || []).forEach((r) => {
    block(box, r.id + "  " + r.label, [
      ["section", r.section],
      ["applies", r.applies_note || "to every plan"],
      ["requires", r.requirement],
      ["elements", r.elements.join("; ")],
      ["not measurable when", r.unmeasurable_when],
      ["why it matters", r.why_it_matters],
    ]);
  });
  block(box, "A placeholder body is absent, not present",
    [["treated as placeholders", (m.placeholder_bodies || []).join(", ")]]);
  const p = document.createElement("p");
  p.className = "mxn";
  p.textContent = m.note;
  box.appendChild(p);
}

async function load() {
  const d = await (await fetch("/api/fields")).json();
  FIELDS = d.fields;
  META = d;
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set" : "no API_KEY — Check will not call anything";
  draw(null);
  drawDecided(null, null, null, null, null, null);
  stateTable();
  rulebookTable(await (await fetch("/api/rulebook")).json());
  show();
}

async function show() {
  const r = await (await fetch("/api/doc?id=" + encodeURIComponent($("doc").value))).json();
  $("text").textContent = r.text || "";
}

async function go() {
  $("go").disabled = true; $("go").textContent = "Checking…"; $("note").hidden = true;
  try {
    const r = await (await fetch("/api/check", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    draw(r.fields);
    const val = (n) => (r.fields && r.fields[n] ? r.fields[n].value : null);
    drawDecided(val("plan_outcome"), r.reason, r.missing, r.unmeasurable,
                val("plan_status"), r.on_worklist);
  } finally { $("go").disabled = false; $("go").textContent = "Check"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => {
  draw(null); drawDecided(null, null, null, null, null, null); show();
});
load();
