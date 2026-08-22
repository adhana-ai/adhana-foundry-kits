// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let FIELDS = [];

// ⚠︎ A ZERO IS AN ANSWER, NOT AN ABSENCE. Every quantity in this corpus is stated, INCLUDING the
// ones that are 0 — a line with no unrated usage says "0", it does not omit the section. So every
// emptiness test here is written against null/undefined/"" explicitly rather than against
// falsiness: `if (!value)` would print "not stated" over a measured zero and drop it out of the
// span denominator, which is the one reading this whole kit is built to get right.
const missing = (v) => v === null || v === undefined || v === "";

function row(f, cell) {
  const tr = document.createElement("tr");
  const v = cell && cell.value;
  const span = cell && cell.span;
  const vtxt = v === undefined ? "not extracted yet" : (missing(v) ? "not stated" : v);
  tr.innerHTML =
    '<td class="n"></td><td class="v' + (missing(v) ? " empty" : "") + '"></td>' +
    '<td class="s' + (span ? "" : " none") + '"></td>';
  tr.children[0].textContent = f.name;
  tr.children[1].textContent = vtxt;
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
  const filled = vals.filter((c) => !missing(c.value));
  $("k-filled").textContent = filled.length + " filled";
  $("k-missing").textContent = (FIELDS.length - filled.length) + " not stated";
  const spannable = vals.filter((c) => c.spannable !== false && !missing(c.value));
  $("k-span").textContent = vals.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
}

function drawComputed(cause, status, flag) {
  $("c-cause").textContent = cause == null ? "—" : cause;
  $("c-status").textContent = status == null ? "—" : status;
  $("c-flag").textContent = (flag === null || flag === undefined)
    ? "not computed — one of the two values the rule needs was missing"
    : (flag ? "YES — over-billed on an invoice already issued, raise a credit"
            : "no — nothing here owes the customer money");
}

async function load() {
  const d = await (await fetch("/api/fields")).json();
  FIELDS = d.fields;
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set" : "no API_KEY — Extract will not call anything";
  draw(null);
  drawComputed(null, null, null);
  show();
}

async function show() {
  const r = await (await fetch("/api/doc?id=" + encodeURIComponent($("doc").value))).json();
  $("text").textContent = r.text || "";
}

async function go() {
  $("go").disabled = true; $("go").textContent = "Extracting…"; $("note").hidden = true;
  try {
    const r = await (await fetch("/api/extract", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    draw(r.fields);
    const val = (n) => (r.fields && r.fields[n] ? r.fields[n].value : null);
    drawComputed(val("variance_cause"), val("invoice_status"), r.needs_credit);
  } finally { $("go").disabled = false; $("go").textContent = "Extract"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => { draw(null); drawComputed(null, null, null); show(); });
load();
