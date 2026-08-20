/* The whole UI. No framework, no build step — the same rule every kit in this repo follows.
 *
 * ⚠︎ THE UI COMPUTES NO CAUSE AND NO CITATION CHECK OF ITS OWN. It renders what the server
 * returned and nothing else — the five-way rule lives once, in src/segment.py, and the
 * citation-validity check lives once, in src/app.py's POST handler; this file only displays them.
 */
const $ = (s) => document.querySelector(s);

let EVENT = null;
let ANSWER = null;

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

async function boot() {
  const r = await fetch("/api/state").then((x) => x.json());
  const sel = $("#eid");
  (r.events || []).forEach((id) => {
    const o = document.createElement("option");
    o.value = id; o.textContent = id;
    sel.appendChild(o);
  });
  $("#key").textContent = r.has_key === false ? "no API_KEY — the page still renders" : "";
  render();
  if ((r.events || []).length) load(r.events[0]);
}

async function load(id) {
  const r = await fetch("/api/event?id=" + encodeURIComponent(id)).then((x) => x.json());
  EVENT = r;
  const ev = r.event;
  $("#varhint").textContent = ev.item_id + " @ " + ev.location_id + " · " + ev.period;
  $("#var-box").innerHTML =
    '<div class="varrow"><span>' + esc(ev.item_label) + " (" + esc(ev.item_id) + ")</span></div>" +
    '<div class="varrow"><span>system ' + ev.system_qty + " · counted " + ev.counted_qty +
    '</span><span class="vq">variance ' + (ev.variance_qty >= 0 ? "+" : "") + ev.variance_qty +
    "</span></div>";
  $("#log-box").innerHTML = r.packed.log.length
    ? r.packed.log.map((l) =>
        '<div class="logrow"><span class="li">' + l.idx + '</span><span class="lt">[' +
        esc(l.type) + "]</span><span class=\"ln\">" + esc(l.note) + "</span></div>"
      ).join("")
    : '<p class="empty">No log lines.</p>';

  ANSWER = null;
  render();
}

function render() {
  const box = $("#out");
  const nar = $("#narrative");
  if (!ANSWER) {
    box.innerHTML = '<p class="empty">No draft yet — press Draft cause.</p>';
    nar.hidden = true;
    $("#s-cause").textContent = "—";
    $("#s-cite").textContent = "—";
    $("#s-in").textContent = "—";
    $("#s-out").textContent = "—";
    return;
  }
  const a = ANSWER;
  const ans = a.answer || {};
  const cause = ans.cause || "no verdict";
  const causeClass = ans.cause === "unresolved" ? "cause unresolved" : "cause";
  const cites = ans.citations || [];
  const badCite = ans.citation_ok === false ? " bad" : "";
  box.innerHTML =
    '<div class="gaprow2"><div class="gh2"><span>' + esc(EVENT.event.event_id) +
    '</span><span class="' + causeClass + '">' + esc(cause) + "</span></div>" +
    (cites.length
      ? '<div class="cite' + badCite + '">citing line' + (cites.length > 1 ? "s " : " ") +
        cites.join(", ") +
        (ans.citation_ok === false ? '<div class="gm">not a real, cause-supporting line -- flagged</div>' : "") +
        "</div>"
      : '<div class="cite">no citation (unresolved)</div>') +
    "</div>";

  if (ans.narrative) {
    nar.hidden = false;
    nar.textContent = ans.narrative;
  } else {
    nar.hidden = true;
  }

  $("#s-cause").textContent = cause;
  $("#s-cite").textContent = cites.length ? cites.join(", ") : "—";
  $("#s-in").textContent = a.input_tokens != null ? a.input_tokens : "—";
  $("#s-out").textContent = a.output_tokens != null ? a.output_tokens : "—";
}

$("#eid").addEventListener("change", (e) => load(e.target.value));

$("#go").addEventListener("click", async () => {
  const note = $("#note");
  note.hidden = true;
  $("#go").disabled = true;
  $("#go").textContent = "Drafting…";
  try {
    const r = await fetch("/api/draft", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ event_id: $("#eid").value }),
    }).then((x) => x.json());
    if (r.note) { note.textContent = r.note; note.hidden = false; }
    if (r.answer !== undefined) { ANSWER = r; }
    render();
  } finally {
    $("#go").disabled = false;
    $("#go").textContent = "Draft cause";
  }
});

boot();
