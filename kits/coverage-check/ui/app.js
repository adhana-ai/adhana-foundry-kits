// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let FIELDS = [];

function row(f, cell) {
  const tr = document.createElement("tr");
  const v = cell && cell.value;
  const span = cell && cell.span;
  const vtxt = v === undefined ? "not adjudicated yet" : (v === null || v === "" ? "not stated" : v);
  const empty = v === undefined || v === null || v === "";
  tr.innerHTML =
    '<td class="n"></td><td class="v' + (empty ? " empty" : "") + '"></td>' +
    '<td class="s' + (span ? "" : " none") + '"></td>';
  tr.children[0].textContent = f.name;
  tr.children[1].textContent = vtxt;
  // Two different reasons a cell has no span, and they are not the same fact. A computed field
  // is not written anywhere in the record, so a span for it would cite a number the document does
  // not contain; an enum is a fixed vocabulary, so a literal match proves nothing about where the
  // answer came from. "n/a" for both would hide which one this is.
  tr.children[2].textContent = span ? ("§ " + span.section)
    : (cell && cell.spannable === false
        ? (f.name === "months_in_service" ? "n/a — computed, not quoted" : "n/a — fixed vocabulary")
        : "—");
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
  // Nothing in this corpus is legitimately absent, so a blank here is a real miss — but the label
  // still says "not stated" rather than "not found", because what the panel knows is that the
  // reply carried nothing, not why.
  $("k-missing").textContent = (FIELDS.length - filled.length) + " not stated";
  const spannable = vals.filter((c) => c.spannable !== false && c.value);
  $("k-span").textContent = vals.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
}

function tag(el, text, cls) {
  el.textContent = "";
  if (text == null) { el.textContent = "—"; return; }
  const s = document.createElement("span");
  s.className = "tag" + (cls ? " " + cls : "");
  s.textContent = text;
  el.appendChild(s);
}

// The two-sided row the kit exists for: the coded cause on the form, and what the technician
// actually described. When they disagree, the narrative is the one that decides — so the
// disagreement is called out rather than left for the reader to spot.
const CODED_FOR = { defect: "defect", collision_damage: "damage",
                    unauthorized_modification: "modification", missed_maintenance: "maintenance" };

function drawComputed(r) {
  const val = (n) => (r && r.fields && r.fields[n] ? r.fields[n].value : null);
  const coded = val("cause_code"), found = val("narrative_finding");
  tag($("c-coded"), coded);
  $("c-found").textContent = "";
  if (found == null) { $("c-found").textContent = "—"; }
  else {
    const wrap = document.createElement("span");
    wrap.className = "split";
    const s = document.createElement("span");
    s.className = "tag" + (coded && CODED_FOR[found] !== coded ? " dis" : "");
    s.textContent = found;
    wrap.appendChild(s);
    if (coded && CODED_FOR[found] !== coded) {
      const n = document.createElement("span");
      n.className = "lab";
      n.textContent = "disagrees with the coded cause — the narrative decides";
      wrap.appendChild(n);
    }
    $("c-found").appendChild(wrap);
  }
  const months = val("months_in_service");
  const recomputed = r ? r.recomputed_months : null;
  if (months == null) { $("c-months").textContent = "—"; }
  else if (recomputed != null && recomputed !== months) {
    $("c-months").textContent = months + "  — the two dates in this reply give " + recomputed;
  } else {
    $("c-months").textContent = String(months);
  }
  const cov = val("covered");
  tag($("c-cov"), cov, cov === "yes" ? "yes" : (cov === "no" ? "no" : null));
  tag($("c-status"), val("claim_status"));
  const flag = r ? r.needs_review : null;
  $("c-flag").textContent = (flag === null || flag === undefined)
    ? (r ? "not computed — one of the two values the rule needs was missing" : "—")
    : (flag ? "YES — not covered and already paid, open a recovery"
            : "no — nothing here needs a recovery review");
}

async function load() {
  const d = await (await fetch("/api/fields")).json();
  FIELDS = d.fields;
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set" : "no API_KEY — Adjudicate will not call anything";
  draw(null);
  drawComputed(null);
  show();
}

async function show() {
  const r = await (await fetch("/api/doc?id=" + encodeURIComponent($("doc").value))).json();
  $("text").textContent = r.text || "";
}

async function go() {
  $("go").disabled = true; $("go").textContent = "Adjudicating…"; $("note").hidden = true;
  try {
    const r = await (await fetch("/api/extract", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    draw(r.fields);
    drawComputed(r);
  } finally { $("go").disabled = false; $("go").textContent = "Adjudicate"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => { draw(null); drawComputed(null); show(); });
load();
