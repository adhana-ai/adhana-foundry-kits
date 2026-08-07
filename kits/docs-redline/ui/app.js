// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let LEVELS = [], FLOOR = null;

// Same third-outcome discipline as docs-route's UI: escalated/abstained are not failures.
const OUTCOME = {
  flagged:   { cls: "ok",   note: "classified automatically — confidence cleared the floor" },
  escalated: { cls: "hold", note: "held for a person — the model answered, but under the floor" },
  abstained: { cls: "hold", note: "held for a person — the model declined to choose" },
  offmenu:   { cls: "bad",  note: "the reply named a level this kit does not have — a prompt fault" },
  unparsed:  { cls: "bad",  note: "the reply was not JSON — a format fault, not a judgement" },
  no_change: { cls: "hold", note: "pure code found no difference between the two versions" },
};

function decision(el, d) {
  el.textContent = "";
  if (!d) { el.textContent = "Nothing has run."; return; }
  if (d.no_key) { el.className = "decision hold"; el.textContent = d.message; return; }
  if (d.error)  { el.className = "decision bad";  el.textContent = d.error; return; }

  const o = OUTCOME[d.outcome] || OUTCOME.unparsed;
  el.className = "decision " + o.cls;
  const head = document.createElement("div");
  head.className = "dq";
  head.textContent = labelOf(d.materiality) || "— no verdict —";
  const sub = document.createElement("div");
  sub.className = "dn";
  sub.textContent = o.note;
  el.appendChild(head);
  el.appendChild(sub);

  const rows = [];
  if (d.confidence !== null && d.confidence !== undefined)
    rows.push(["confidence", d.confidence.toFixed(2) + "   (floor " + (d.floor ?? FLOOR) + ")"]);
  if (d.escalated && d.model_materiality)
    rows.push(["the model chose", labelOf(d.model_materiality) + " — overridden by the floor"]);
  if (d.why) rows.push(["why", d.why]);
  if (d.offered) rows.push(["it answered", d.offered]);
  rows.forEach(([k, v]) => {
    const r = document.createElement("div");
    r.className = "dr";
    r.innerHTML = '<span class="dk"></span><span class="dv"></span>';
    r.children[0].textContent = k;
    r.children[1].textContent = v;
    el.appendChild(r);
  });
}

const labelOf = (k) => (LEVELS.find((l) => l.key === k) || {}).label || k;

function drawLevels() {
  const box = $("levels");
  box.textContent = "";
  LEVELS.forEach((l) => {
    const d = document.createElement("div");
    d.className = "qrow";
    d.innerHTML = '<div class="qn"></div><div class="qm"></div>';
    d.children[0].textContent = l.label;
    d.children[1].textContent = l.meaning;
    box.appendChild(d);
  });
}

function drawSpan(span) {
  const el = $("span");
  if (!span) { el.className = "decision hold"; el.textContent = "No difference found between the two versions."; return; }
  el.className = "decision";
  el.textContent = "";
  const v1 = document.createElement("div"); v1.className = "dr";
  v1.innerHTML = '<span class="dk">original</span><span class="dv"></span>';
  v1.children[1].textContent = span.v1 || "(nothing — added by the correction)";
  const v2 = document.createElement("div"); v2.className = "dr";
  v2.innerHTML = '<span class="dk">corrected</span><span class="dv"></span>';
  v2.children[1].textContent = span.v2 || "(nothing — removed by the correction)";
  el.appendChild(v1); el.appendChild(v2);
}

async function loadPair(id) {
  if (!id) return;
  const t = await (await fetch("/api/pair?id=" + encodeURIComponent(id))).json();
  $("text").textContent = "== ORIGINAL (" + t.v1_id + ") ==\n" + (t.v1_text || "")
    + "\n\n== CORRECTED (" + t.v2_id + ") ==\n" + (t.v2_text || "");
  drawSpan(t.span);
  // The free baseline runs on selection, same reasoning as docs-route: it costs nothing, so
  // making someone ask for it would teach that the boring answer is the special case.
  const b = await (await fetch("/api/baseline?id=" + encodeURIComponent(id))).json();
  const el = $("base");
  el.className = "decision " + (b.materiality ? "ok" : "hold");
  el.textContent = "";
  const h = document.createElement("div"); h.className = "dq";
  h.textContent = labelOf(b.materiality) || "— no verdict —";
  const n = document.createElement("div"); n.className = "dn";
  n.textContent = b.materiality ? ("matched: " + b.rule) : "no surface signal either way — it "
    + "declines rather than guessing";
  el.appendChild(h); el.appendChild(n);
  decision($("model"), null);
  $("k-state").textContent = "nothing has run";
}

async function boot() {
  const s = await (await fetch("/api/levels")).json();
  LEVELS = s.levels; FLOOR = s.floor;
  drawLevels();
  $("k-model").textContent = s.model || "no model set";
  $("k-floor").textContent = "floor " + s.floor;
  $("key").textContent = s.has_key ? "" : "no API key — the model verdict is off, the free one is not";
  const sel = $("pair");
  s.pairs.forEach((p) => {
    const o = document.createElement("option");
    o.value = p; o.textContent = p;
    sel.appendChild(o);
  });
  sel.addEventListener("change", () => loadPair(sel.value));
  $("go").addEventListener("click", async () => {
    $("k-state").textContent = "classifying…";
    const r = await (await fetch("/api/classify", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: sel.value }),
    })).json();
    decision($("model"), r);
    drawSpan(r.span);
    $("k-state").textContent = r.outcome || (r.no_key ? "no key" : "done");
  });
  if (s.pairs.length) { sel.value = s.pairs[0]; loadPair(sel.value); }
}

boot();
