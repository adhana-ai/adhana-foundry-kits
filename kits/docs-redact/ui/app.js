// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);

// Mirrors src/redact.py's CSS_CLASS mapping exactly — the legend and the highlighted view must
// agree on which colour a category is, and there is exactly one place that mapping is decided:
// the server, which already emits `<mark class="span CLASS">` using this table. Kept identical
// here only for the legend chips, which the server has no reason to render itself.
const CSS_CLASS = { NAME: "name", SSN: "ssn", EMAIL: "email", PHONE: "phone",
                    ADDRESS: "addr", DOB: "dob", CARD: "card" };

let CATEGORIES = [];

function buildLegend() {
  const el = $("legend");
  el.textContent = "";
  CATEGORIES.forEach((c) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    const dot = document.createElement("span");
    dot.className = "dot " + (CSS_CLASS[c.name] || c.name.toLowerCase());
    chip.appendChild(dot);
    chip.appendChild(document.createTextNode(c.name));
    el.appendChild(chip);
  });
}

function setView(view) {
  $("out-redacted").hidden = view !== "redacted";
  $("out-highlighted").hidden = view !== "highlighted";
}

async function loadCategories() {
  const d = await (await fetch("/api/categories")).json();
  CATEGORIES = d.categories;
  buildLegend();
  $("s-cats-label").textContent = "of " + d.categories.length + " categories";
  d.documents.forEach((id) => {
    const o = document.createElement("option");
    o.value = o.textContent = id;
    $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set" : "no API_KEY — Detect will not call anything";
  if (d.documents.length) await loadDoc(d.documents[0]);
}

async function loadDoc(id) {
  const r = await (await fetch("/api/doc?id=" + encodeURIComponent(id))).json();
  $("src").value = r.text || "";
  clearResult();
}

function clearResult() {
  $("out-redacted").textContent = "";
  $("out-highlighted").innerHTML = "";
  $("s-spans").textContent = "—";
  $("s-cats").textContent = "—";
  $("s-unlocated").textContent = "—";
  $("s-unlocated-wrap").classList.remove("bad");
}

async function go() {
  const text = $("src").value;
  if (!text.trim()) return;
  $("go").disabled = true; $("go").textContent = "Detecting…"; $("note").hidden = true;
  try {
    const r = await (await fetch("/api/redact", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value, text }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    if (!r.spans) { clearResult(); return; }
    // PLAIN TEXT INTO A <pre> VIA textContent, TRUSTED HTML VIA innerHTML — the server escapes
    // everything in `highlighted` before it ever leaves src/redact.py (see its docstring), so this
    // is the one place in the client allowed to use innerHTML at all.
    $("out-redacted").textContent = r.redacted;
    $("out-highlighted").innerHTML = r.highlighted;
    const cats = new Set(r.spans.map((s) => s.category));
    $("s-spans").textContent = r.spans.length;
    $("s-cats").textContent = cats.size;
    $("s-unlocated").textContent = r.unlocated;
    $("s-unlocated-wrap").classList.toggle("bad", r.unlocated > 0);
  } finally { $("go").disabled = false; $("go").textContent = "Detect & redact"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", (e) => loadDoc(e.target.value));
$("viewseg").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-view]");
  if (!btn) return;
  $("viewseg").querySelectorAll("button").forEach((b) => b.classList.remove("on"));
  btn.classList.add("on");
  setView(btn.dataset.view);
});

loadCategories();
