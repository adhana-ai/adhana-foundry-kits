// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let FIELDS = [];

function row(f, cell) {
  const tr = document.createElement("tr");
  const v = cell && cell.value;
  const span = cell && cell.span;
  // THE THREE STATES. A value, an explicit "not found", and (before a run) "not extracted yet".
  // They are different facts and they never share a rendering.
  const vtxt = v === undefined ? "not extracted yet" : (v === null || v === "" ? "not found" : v);
  const empty = v === undefined || v === null || v === "";
  tr.innerHTML =
    '<td class="n"></td><td class="v' + (empty ? " empty" : "") + '"></td>' +
    '<td class="s' + (span ? "" : " none") + '"></td>';
  tr.children[0].textContent = f.name;
  tr.children[1].textContent = vtxt;
  // THREE STATES HERE TOO, for the same reason as the value column. A span that was never
  // applicable (an enum answers with a canonical token the document does not contain) is not the
  // same fact as a span we looked for and could not find, and a bare dash says both.
  tr.children[2].textContent = span ? ("§ " + span.section)
    : (cell && cell.spannable === false ? "n/a — fixed value" : "—");
  return tr;
}

function draw(fields) {
  const body = $("rows");
  body.textContent = "";
  FIELDS.forEach((f) => body.appendChild(row(f, fields ? fields[f.name] : undefined)));
  // A DASH KEEPS ITS LABEL. Three bare "—" chips say nothing about what is unknown. And note
  // what they must NOT say before a run: "9 not found" would report nine refusals that never
  // happened. "Not found" is a verdict — the model was asked and declined — and nothing has been
  // asked yet. That distinction is the whole point of this kit, so the header cannot blur it.
  if (!fields) { $("k-filled").textContent = "— filled"; $("k-missing").textContent = "— not found";
                 $("k-span").textContent = "— with a span"; return; }
  const vals = FIELDS.map((f) => fields[f.name] || {});
  const filled = vals.filter((c) => c.value !== null && c.value !== undefined && c.value !== "");
  $("k-filled").textContent = filled.length + " filled";
  $("k-missing").textContent = (FIELDS.length - filled.length) + " not found";
  const spannable = vals.filter((c) => c.spannable !== false && c.value);
  $("k-span").textContent = vals.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
}

async function load() {
  const d = await (await fetch("/api/fields")).json();
  FIELDS = d.fields;
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set" : "no API_KEY — Extract will not call anything";
  draw(null);
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
  } finally { $("go").disabled = false; $("go").textContent = "Extract"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => { draw(null); show(); });
load();
