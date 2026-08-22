// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let FIELDS = [];

const money = (v) => (v === null || v === undefined || v === "")
  ? null : Number(v).toLocaleString(undefined, { minimumFractionDigits: 2,
                                                maximumFractionDigits: 2 }) + " USD";

function row(f, cell) {
  const tr = document.createElement("tr");
  const v = cell && cell.value;
  const span = cell && cell.span;
  const vtxt = v === undefined ? "not pre-checked yet" : (v === null || v === "" ? "not stated" : v);
  const empty = v === undefined || v === null || v === "";
  tr.innerHTML =
    '<td class="n"></td><td class="v' + (empty ? " empty" : "") + '"></td>' +
    '<td class="s' + (span ? "" : " none") + '"></td>';
  tr.children[0].textContent = f.name;
  tr.children[1].textContent = vtxt;
  // ⚑ A COMPUTED FIELD SAYS SO. permitted_amount_usd is arithmetic the model did, not a value
  // anywhere in the document — printing an em-dash beside it would read as a missing citation on
  // a correct answer, which is exactly the confusion a span column exists to prevent.
  tr.children[2].textContent = span ? ("§ " + span.section)
    : (f.computed ? "computed — not in the document"
                  : (cell && cell.spannable === false ? "n/a — fixed value" : "—"));
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
  // Six of these twenty fields are legitimately null — no amortization term on a line that is not
  // capital, no expansion where there was none, no cap terms where the lease caps nothing. So a
  // blank here can be a real miss or a correctly-absent value; the label says "not stated" rather
  // than "not found", because what the panel knows is that the reply carried nothing, not why.
  $("k-missing").textContent = (FIELDS.length - filled.length) + " not stated";
  const spannable = vals.filter((c) => c.spannable !== false && c.value);
  $("k-span").textContent = vals.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
}

function drawComputed(r) {
  const val = (n) => (r && r.fields && r.fields[n] ? r.fields[n].value : null);
  $("c-billed").textContent = money(val("billed_to_tenant_usd")) || "—";
  $("c-permitted").textContent = money(val("permitted_amount_usd")) || "—";
  $("c-ok").textContent = val("line_ok") || "—";
  $("c-status").textContent = val("statement_status") || "—";
  const flag = r ? r.needs_review : null;
  $("c-flag").textContent = (flag === null || flag === undefined)
    ? "not computed — one of the values the rule needs was missing"
    : (flag ? "YES — overbilled and already issued, the tenant needs a corrected statement"
            : "no — nothing here needs a corrected statement");
  if (!r) { $("c-recheck").textContent = "—"; return; }
  const again = r.recomputed_permitted_usd;
  if (again === null || again === undefined) {
    $("c-recheck").textContent = "could not be re-run — a value the four stages need was missing";
  } else {
    const agrees = r.recomputed_line_ok === val("line_ok");
    $("c-recheck").textContent = money(again) + " → " + (r.recomputed_line_ok || "—")
      + (agrees ? "  (agrees with the reply)"
                : "  (DISAGREES with the reply — the verdict does not follow from its own numbers)");
  }
}

async function load() {
  const d = await (await fetch("/api/fields")).json();
  FIELDS = d.fields;
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set" : "no API_KEY — Pre-check will not call anything";
  draw(null);
  drawComputed(null);
  show();
}

async function show() {
  const r = await (await fetch("/api/doc?id=" + encodeURIComponent($("doc").value))).json();
  $("text").textContent = r.text || "";
}

async function go() {
  $("go").disabled = true; $("go").textContent = "Pre-checking…"; $("note").hidden = true;
  try {
    const r = await (await fetch("/api/extract", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    draw(r.fields);
    drawComputed(r.fields ? r : null);
  } finally { $("go").disabled = false; $("go").textContent = "Pre-check"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => { draw(null); drawComputed(null); show(); });
load();
