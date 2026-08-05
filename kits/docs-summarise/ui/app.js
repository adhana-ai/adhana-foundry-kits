// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let SECTIONS = [];

function card(s, got) {
  const d = document.createElement("div");
  d.className = "card";
  // THE THREE STATES, AND NONE OF THEM IS "WRONG". Before a run: not written yet. After: prose,
  // or an explicit refusal the prompt asked for in words. There is no red state here on purpose —
  // a brief has no gold string to fail against, and the verdict is a person's.
  let txt, cls;
  if (!got)                        { txt = "not written yet";  cls = "empty"; }
  else if (got.state === "absent") { txt = "not stated in this document — the model declined";
                                     cls = "absent"; d.classList.add("is-absent"); }
  else if (got.state === "missing"){ txt = "no such section in the reply — a parsing fault, not a "
                                         + "judgement"; cls = "absent"; }
  else                             { txt = got.text || ""; cls = ""; }

  d.innerHTML = '<div class="ct"><span class="cn"></span><span class="cw"></span></div>'
              + '<div class="cb ' + cls + '"></div><div class="cg"></div>';
  d.children[0].children[0].textContent = s.name;
  d.children[0].children[1].textContent = "weight " + s.weight;
  d.children[1].textContent = txt;
  // ⚠︎ NEVER A ZERO BEFORE SOMEBODY GAVE ONE. A grade of 0 is a judgement; an ungraded section is
  // the absence of one, and this page cannot produce either — grading happens in
  // `python -m evals.grade`, which is where the reviewer-minutes are spent and counted.
  d.children[2].textContent = "grade — not graded here. Run: python -m evals.grade";
  return d;
}

function draw(sections) {
  const box = $("cards");
  box.textContent = "";
  SECTIONS.forEach((s) => box.appendChild(card(s, sections ? sections[s.key] : null)));
  if (!sections) { $("k-state").textContent = "nothing has run"; return; }
  const written = SECTIONS.filter((s) => (sections[s.key] || {}).state === "written").length;
  $("k-state").textContent = written + " of " + SECTIONS.length + " sections written";
}

// What the packer actually sent. Drawn only after a run, and loudest when something was dropped:
// this is the number that says whether a poor brief is the model's fault or the budget's.
function drawPack(p, coverage) {
  const el = $("packbar");
  if (!p) { el.hidden = true; return; }
  el.hidden = false;
  const dropped = (p.dropped || []).length;
  el.className = "packbar" + (dropped ? " warn" : "");
  el.textContent = dropped
    ? (p.sent.length + " of " + (p.sent.length + dropped) + " document sections were sent (~"
       + p.est_tokens_sent + " tokens). NOT sent: " + p.dropped.join(", ")
       + ". The brief was written without them.")
    : ("the whole document was sent — " + p.sent.length + " sections, ~" + p.est_tokens_sent
       + " tokens" + (coverage < 1 ? " (segment coverage " + coverage + ")" : ""));
}

async function load() {
  const d = await (await fetch("/api/rubric")).json();
  SECTIONS = d.sections;
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set" : "no API_KEY — Summarise will not call anything";
  draw(null);
  show();
}

async function show() {
  const r = await (await fetch("/api/doc?id=" + encodeURIComponent($("doc").value))).json();
  $("text").textContent = r.text || "";
}

async function go() {
  $("go").disabled = true; $("go").textContent = "Summarising…"; $("note").hidden = true;
  try {
    const r = await (await fetch("/api/summarise", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    draw(r.sections);
    drawPack(r.pack, r.segment_coverage);
  } finally { $("go").disabled = false; $("go").textContent = "Summarise"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => { draw(null); drawPack(null); show(); });
load();
