// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let FIELDS = [];

// The two fields the model had to COMPUTE rather than copy. They are marked in the table because
// a reader looking at a field list has no way to tell an extracted value from a reconstructed one,
// and on this kit that is the whole difference between reading the tag and doing the work.
const COMPUTED = new Set(["trail_hours", "trail_cycles"]);

function row(f, cell) {
  const tr = document.createElement("tr");
  const v = cell && cell.value;
  const span = cell && cell.span;
  const vtxt = v === undefined ? "not reconciled yet" : (v === null || v === "" ? "not stated" : v);
  const empty = v === undefined || v === null || v === "";
  tr.innerHTML =
    '<td class="n"></td><td class="v' + (empty ? " empty" : "") + '"></td>' +
    '<td class="s' + (span ? "" : " none") + '"></td>';
  tr.children[0].textContent = f.name;
  if (COMPUTED.has(f.name)) {
    const b = document.createElement("span");
    b.className = "sum"; b.textContent = "summed";
    tr.children[0].appendChild(b);
  }
  tr.children[1].textContent = vtxt;
  tr.children[2].textContent = span ? ("§ " + span.section)
    : (cell && cell.spannable === false
        ? (COMPUTED.has(f.name) ? "n/a — a computed total, quoted from nowhere" : "n/a — fixed value")
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
  $("k-missing").textContent = (FIELDS.length - filled.length) + " not stated";
  // The span denominator excludes the two computed totals AND the enums — a sum appears nowhere in
  // the pack, so counting it as unspanned would punish the kit for doing the arithmetic.
  const spannable = vals.filter((c) => c.spannable !== false && c.value);
  $("k-span").textContent = vals.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
}

const STATUS_WORDS = {
  within_limits: "within limits — the trail puts it inside both published limits",
  hours_exceeded: "HOURS EXCEEDED — at or past the published hours limit",
  cycles_exceeded: "CYCLES EXCEEDED — at or past the published cycles limit",
  both_exceeded: "BOTH EXCEEDED — at or past both published limits",
  cannot_determine: "CANNOT BE DETERMINED — a period of records is missing and the accrual for it "
                    + "cannot be reconstructed",
};

function drawComputed(status, tag, disp, flag) {
  $("c-status").textContent = status == null ? "—" : (STATUS_WORDS[status] || status);
  $("c-tag").textContent = tag == null ? "—" : tag;
  $("c-disp").textContent = disp == null ? "—" : disp;
  $("c-flag").textContent = (flag === null || flag === undefined)
    ? "not computed — one of the three values the rule needs was missing"
    : (flag ? "YES — a discrepancy on a pack up for return to service; stop it before release"
            : "no — this rule found nothing to raise (which is not a release)");
  $("c-flag").className = flag ? "hot" : "";
}

async function load() {
  const d = await (await fetch("/api/fields")).json();
  FIELDS = d.fields;
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set" : "no API_KEY — Reconcile will not call anything";
  draw(null);
  drawComputed(null, null, null, null);
  show();
}

async function show() {
  const r = await (await fetch("/api/doc?id=" + encodeURIComponent($("doc").value))).json();
  $("text").textContent = r.text || "";
}

async function go() {
  $("go").disabled = true; $("go").textContent = "Reconciling…"; $("note").hidden = true;
  try {
    const r = await (await fetch("/api/extract", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    draw(r.fields);
    const val = (n) => (r.fields && r.fields[n] ? r.fields[n].value : null);
    drawComputed(val("life_status"), val("tag_agrees"), val("disposition_requested"), r.escalate);
  } finally { $("go").disabled = false; $("go").textContent = "Reconcile"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => { draw(null); drawComputed(null, null, null, null); show(); });
load();
