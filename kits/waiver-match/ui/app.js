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
  // ⚠︎ TWO DIFFERENT REASONS A FIELD CARRIES NO SPAN, AND ONE LABEL FOR BOTH IS A FALSE CLAIM.
  // `release_status` IS stated in the package — it is an enum, one of a fixed set, so locating
  // the word "scheduled" cites the heading rather than a value. `parties_uncovered` is not
  // stated anywhere: it is counted. Calling the first one "derived, not stated" on the page is
  // simply wrong, and it was on the first screenshot taken of this UI.
  tr.children[2].textContent = span ? ("§ " + span.section)
    : (cell && cell.spannable === false
        ? (f.type === "enum" ? "n/a — fixed value" : "n/a — derived, not stated")
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
  // first_gap_party is legitimately null on a fully covered package, so a blank here can be
  // either a real miss or a correctly-absent value — the label says "not stated" rather than
  // "not found", because what the panel knows is that the reply carried nothing, not why.
  $("k-missing").textContent = (FIELDS.length - filled.length) + " not stated";
  const spannable = vals.filter((c) => c.spannable !== false && c.value);
  $("k-span").textContent = vals.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
}

function drawComputed(count, status, flag, check) {
  $("c-count").textContent = count === null || count === undefined ? "—" : String(count);
  $("c-status").textContent = status == null ? "—" : status;
  $("c-flag").textContent = (flag === null || flag === undefined)
    ? "not computed — one of the two values the rule needs was missing"
    : (flag ? "YES — a gap on a package scheduled to go out; pull it back before release"
            : "no — nothing here to pull back this cycle");
  if (!check) { $("c-self").textContent = "—"; return; }
  const bad = ["party_agrees", "reason_agrees", "party_exists"].filter((k) => check[k] === false);
  $("c-self").textContent = bad.length
    ? ("NO — " + bad.join(", ") + " (a diagnostic, not a grade)")
    : "yes — the count, the party and the reason line up, and the package lists that party";
}

async function load() {
  const d = await (await fetch("/api/fields")).json();
  FIELDS = d.fields;
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set"
                                   : "no API_KEY — Check coverage will not call anything";
  draw(null);
  drawComputed(null, null, null, null);
  show();
}

async function show() {
  const r = await (await fetch("/api/doc?id=" + encodeURIComponent($("doc").value))).json();
  $("text").textContent = r.text || "";
}

async function go() {
  $("go").disabled = true; $("go").textContent = "Checking…"; $("note").hidden = true;
  try {
    const r = await (await fetch("/api/extract", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    draw(r.fields);
    const val = (n) => (r.fields && r.fields[n] ? r.fields[n].value : null);
    drawComputed(val("parties_uncovered"), val("release_status"), r.needs_hold, r.self_check);
  } finally { $("go").disabled = false; $("go").textContent = "Check coverage"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => {
  draw(null); drawComputed(null, null, null, null); show();
});
load();
