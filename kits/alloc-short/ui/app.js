/* The whole UI. No framework, no build step — the same rule every kit in this repo follows.
 *
 * ⚠︎ THE UI COMPUTES NO ALLOCATION AND NO FLAG LIST. It renders what the server returned and
 * nothing else — which events are flagged and every unit count live once, in src/allocate.py,
 * and this file only displays them.
 */
const $ = (s) => document.querySelector(s);

let SESSION = null;
let ANSWER = null;

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

async function boot() {
  const r = await fetch("/api/state").then((x) => x.json());
  const sel = $("#sid");
  (r.sessions || []).forEach((id) => {
    const o = document.createElement("option");
    o.value = id; o.textContent = id;
    sel.appendChild(o);
  });
  $("#key").textContent = r.has_key === false ? "no API_KEY — the page still renders" : "";
  render();
  if ((r.sessions || []).length) load(r.sessions[0]);
}

async function load(id) {
  const r = await fetch("/api/session?id=" + encodeURIComponent(id)).then((x) => x.json());
  SESSION = r;
  const events = r.packed.events;
  $("#evhint").textContent = events.length + " of " + r.all_events.length + " events this session";
  $("#ev-box").innerHTML = events.length
    ? events.map((e) => {
        const stores = e.per_store.map((p) =>
          p.store_id + " " + p.allocated_units + "/" + p.ask_units).join(", ");
        const flags = [];
        if (!e.promo_protected) flags.push("promo not fully protected");
        if (!e.customer_protected) flags.push("customer commitments not fully protected");
        if (e.floor_breach_stores && e.floor_breach_stores.length)
          flags.push("equity floor breached: " + e.floor_breach_stores.join(", "));
        return '<div class="gaprow"><div class="gh"><span>' + esc(e.event_id) + " — " + esc(e.sku) +
          '</span><span>' + e.available_units + " / " + e.total_ask + " units</span></div>" +
          '<div class="gv">' + esc(stores) + "</div>" +
          (flags.length ? '<div class="gm">' + esc(flags.join(" · ")) + "</div>" : "") +
          "</div>";
      }).join("")
    : '<p class="empty">No flagged events this session.</p>';
  $("#notes-box").innerHTML = (r.packed.notes || []).map((n) =>
    '<div class="noterow">' + esc(n) + "</div>").join("");

  ANSWER = null;
  render();
}

function render() {
  const box = $("#out");
  const nar = $("#narrative");
  if (!ANSWER) {
    box.innerHTML = '<p class="empty">No draft yet — press Draft review brief.</p>';
    nar.hidden = true;
    $("#s-flagged").textContent = SESSION ? SESSION.pack_meta.events_packed : "—";
    $("#s-answered").textContent = "—";
    $("#s-in").textContent = "—";
    $("#s-out").textContent = "—";
    return;
  }
  const a = ANSWER;
  const events = (a.answer && a.answer.events) || [];
  box.innerHTML = events.length
    ? events.map((e) => {
        const causeClass = e.cause === "unknown" ? "cause unknown" : "cause";
        const badCite = e.citation_ok === false ? " bad" : "";
        const cites = (e.citation_1 || e.citation_2)
          ? '<div class="cite' + badCite + '">1: ' + esc(e.citation_1 || "(none)") +
            '</div><div class="cite' + badCite + '">2: ' + esc(e.citation_2 || "(none)") +
            (e.citation_ok === false ? '<div class="gm">not a real, SKU-relevant line -- flagged</div>' : "") +
            "</div>"
          : "";
        return '<div class="gaprow2"><div class="gh2"><span>' + esc(e.event_id) +
          '</span><span class="' + causeClass + '">' + esc(e.cause || "no verdict") + "</span></div>" +
          (e.note ? '<div class="gv">' + esc(e.note) + "</div>" : "") + cites + "</div>";
      }).join("")
    : '<p class="empty">No answer.</p>';

  if (a.answer && a.answer.narrative) {
    nar.hidden = false;
    nar.textContent = a.answer.narrative;
  } else {
    nar.hidden = true;
  }

  $("#s-flagged").textContent = a.events_flagged != null ? a.events_flagged : "—";
  $("#s-answered").textContent = a.events_answered != null ? a.events_answered : "—";
  $("#s-in").textContent = a.input_tokens != null ? a.input_tokens : "—";
  $("#s-out").textContent = a.output_tokens != null ? a.output_tokens : "—";
}

$("#sid").addEventListener("change", (e) => load(e.target.value));

$("#go").addEventListener("click", async () => {
  const note = $("#note");
  note.hidden = true;
  $("#go").disabled = true;
  $("#go").textContent = "Drafting…";
  try {
    const r = await fetch("/api/draft", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ session_id: $("#sid").value }),
    }).then((x) => x.json());
    if (r.note) { note.textContent = r.note; note.hidden = false; }
    if (r.answer !== undefined) { ANSWER = r; }
    render();
  } finally {
    $("#go").disabled = false;
    $("#go").textContent = "Draft review brief";
  }
});

boot();
