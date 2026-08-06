// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let QUEUES = [], FLOOR = null;

// ⚑ THE FOUR OUTCOMES, EACH WITH ITS OWN WORDS. `escalated` is not a failure and `abstained` is
// not an error — collapsing either into "wrong" is how a router gets demoed as accurate while
// quietly handing a third of its traffic to a person. The colours come from the same set; nothing
// here is red except the two states that really are faults.
const OUTCOME = {
  routed:    { cls: "ok",   note: "routed automatically — confidence cleared the floor" },
  escalated: { cls: "hold", note: "held for a person — the model answered, but under the floor" },
  abstained: { cls: "hold", note: "held for a person — the model declined to choose" },
  offmenu:   { cls: "bad",  note: "the reply named a queue this kit does not have — a prompt fault" },
  unparsed:  { cls: "bad",  note: "the reply was not JSON — a format fault, not a judgement" },
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
  head.textContent = d.label || "— no queue —";
  const sub = document.createElement("div");
  sub.className = "dn";
  sub.textContent = o.note;
  el.appendChild(head);
  el.appendChild(sub);

  // ⚠︎ WHAT THE MODEL SAID AND WHAT THE SYSTEM DID, SIDE BY SIDE AND NEVER MERGED. When the floor
  // overrides a confident-looking answer, both facts have to survive: the model's queue is a
  // measurement of the model, and the routed queue is a measurement of the system.
  const rows = [];
  if (d.confidence !== null && d.confidence !== undefined)
    rows.push(["confidence", d.confidence.toFixed(2) + "   (floor " + (d.floor ?? FLOOR) + ")"]);
  if (d.escalated && d.model_queue)
    rows.push(["the model chose", labelOf(d.model_queue) + " — overridden by the floor"]);
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

const labelOf = (k) => (QUEUES.find((q) => q.key === k) || {}).label || k;

function drawQueues() {
  const box = $("queues");
  box.textContent = "";
  QUEUES.forEach((q) => {
    const d = document.createElement("div");
    d.className = "qrow";
    d.innerHTML = '<div class="qn"></div><div class="qm"></div>';
    d.children[0].textContent = q.label;
    d.children[1].textContent = q.meaning;
    box.appendChild(d);
  });
}

async function loadDoc(id) {
  if (!id) return;
  const t = await (await fetch("/api/doc?id=" + encodeURIComponent(id))).json();
  $("text").textContent = t.text || "";
  // The free router runs on selection, not on a click. It costs nothing, so making someone ask
  // for it would only teach that the boring answer is the special case.
  const b = await (await fetch("/api/baseline?id=" + encodeURIComponent(id))).json();
  const el = $("base");
  el.className = "decision " + (b.queue ? "ok" : "hold");
  el.textContent = "";
  const h = document.createElement("div"); h.className = "dq";
  h.textContent = b.label || "— no queue —";
  const n = document.createElement("div"); n.className = "dn";
  n.textContent = b.queue ? ("matched: " + b.rule) : "no keyword matched — it declines rather "
    + "than guessing, so it cannot borrow the null baseline's score";
  el.appendChild(h); el.appendChild(n);
  decision($("model"), null);
  $("k-state").textContent = "nothing has run";
}

async function boot() {
  const s = await (await fetch("/api/queues")).json();
  QUEUES = s.queues; FLOOR = s.floor;
  drawQueues();
  $("k-model").textContent = s.model || "no model set";
  $("k-floor").textContent = "floor " + s.floor;
  $("key").textContent = s.has_key ? "" : "no API key — the model router is off, the free one is not";
  const sel = $("doc");
  s.documents.forEach((d) => {
    const o = document.createElement("option");
    o.value = d; o.textContent = d;
    sel.appendChild(o);
  });
  sel.addEventListener("change", () => loadDoc(sel.value));
  $("go").addEventListener("click", async () => {
    $("k-state").textContent = "routing…";
    const r = await (await fetch("/api/route", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: sel.value }),
    })).json();
    decision($("model"), r);
    $("k-state").textContent = r.outcome || (r.no_key ? "no key" : "done");
  });
  if (s.documents.length) { sel.value = s.documents[0]; loadDoc(sel.value); }
}

boot();
