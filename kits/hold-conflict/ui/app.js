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
  const filled = vals.filter((c) => c.value !== null && c.value !== undefined && c.value !== "");
  $("k-filled").textContent = filled.length + " filled";
  // overlapping_expires is legitimately null when no overlapping series is on file, and
  // binding_hold_id is legitimately null when nothing freezes the series — so a blank here can be
  // either a real miss or a correctly-absent value. The label says "not stated" rather than "not
  // found", because what the panel knows is that the reply carried nothing, not why.
  $("k-missing").textContent = (FIELDS.length - filled.length) + " not stated";
  const spannable = vals.filter((c) => c.spannable !== false && c.value);
  $("k-span").textContent = vals.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
}

function drawComputed(hold, eligible, queue, flag) {
  $("c-hold").textContent = hold == null
    ? (eligible == null ? "—" : "none — no active hold's scope covers this series")
    : (hold + " — an active hold covers this series");
  $("c-elig").textContent = eligible == null ? "—"
    : (eligible === "yes" ? "yes — may be put to a records officer for release"
                          : "no — something still freezes this series");
  $("c-queue").textContent = queue == null ? "—" : queue;
  $("c-flag").textContent = (flag === null || flag === undefined)
    ? "not computed — one of the two values the rule needs was missing"
    : (flag ? "YES — frozen and already in the destruction queue, pull it out"
            : "no — nothing here needs a follow-up");
}

async function load() {
  const d = await (await fetch("/api/fields")).json();
  FIELDS = d.fields;
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set" : "no API_KEY — Extract will not call anything";
  $("k-asof").textContent = "reviewed as of " + d.as_of;
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
    drawComputed(val("binding_hold_id"), val("disposition_eligible"), val("queue_status"),
                 r.needs_review);
  } finally { $("go").disabled = false; $("go").textContent = "Extract"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => { draw(null); drawComputed(null, null, null, null); show(); });
load();
