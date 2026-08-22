// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let FIELDS = [];

function row(f, cell) {
  const tr = document.createElement("tr");
  const v = cell && cell.value;
  const span = cell && cell.span;
  const vtxt = v === undefined ? "not extracted yet" : (v === null || v === "" ? "not stated" : v);
  const empty = v === undefined || v === null || v === "";
  tr.innerHTML =
    '<td class="n"></td><td class="v' + (empty ? " empty" : "") + '"></td>' +
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
  // ⚠︎ `stated` IS NOT `c.value` AS A TRUTH TEST, AND THIS KIT IS WHERE THAT BIT. A cancelled or
  // no-show booking has room_revenue_usd of EXACTLY 0, which is falsy in JavaScript — so the
  // first version of this panel counted 8 spans over a denominator of 7 and printed "8 of 7 with
  // a span" on the very first live screenshot. No structural gate can see that; opening the page
  // can. Every count below asks whether a value was STATED, never whether it is truthy.
  const stated = (c) => c.value !== null && c.value !== undefined && c.value !== "";
  const filled = vals.filter(stated);
  $("k-filled").textContent = filled.length + " filled";
  // Exactly one of room_revenue_refunded_usd / penalty_charged_usd is legitimately null on every
  // record — a stay has no penalty, a cancellation has no refund — so a blank here can be either
  // a real miss or a correctly-absent value. The label says "not stated" rather than "not found",
  // because what the panel knows is that the reply carried nothing, not why.
  $("k-missing").textContent = (FIELDS.length - filled.length) + " not stated";
  const spannable = vals.filter((c) => c.spannable !== false && stated(c));
  $("k-span").textContent = vals.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
}

function money(v) {
  return (v === null || v === undefined) ? null : Number(v).toFixed(2) + " USD";
}

function drawComputed(owed, valid, status, flag) {
  $("c-owed").textContent = owed == null
    ? "— the rule could not be run on what came back" : money(owed);
  $("c-valid").textContent = valid == null ? "—" : valid;
  $("c-sig").textContent = status == null ? "—" : status;
  $("c-flag").textContent = (flag === null || flag === undefined)
    ? "not computed — one of the two values the rule needs was missing"
    : (flag ? "YES — not owed as claimed and the invoice is already paid, raise a recovery claim"
            : "no — nothing here needs a recovery claim");
}

async function load() {
  const d = await (await fetch("/api/fields")).json();
  FIELDS = d.fields;
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set" : "no API_KEY — Extract will not call anything";
  draw(null);
  drawComputed(null, null, null, null);
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
    drawComputed(r.recomputed_owed_usd, val("claim_valid"), val("invoice_status"),
                 r.needs_recovery);
  } finally { $("go").disabled = false; $("go").textContent = "Extract"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => {
  draw(null); drawComputed(null, null, null, null); show();
});
load();
