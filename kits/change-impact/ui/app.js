/* The whole UI. No framework, no build step — the same rule every kit in this repo follows.
 *
 * ⚠︎ THE UI COMPUTES NO IMPACT. It renders what /api/check returned and nothing else — the match,
 * the extraction and the impact arithmetic all live once, in src/match.py and src/impact.py, and
 * this file only displays them.
 */
const $ = (s) => document.querySelector(s);
const CHANGE_LABEL = {
  expedite: "Expedite", delay: "Delay", cancel: "Cancel", qty_change: "Quantity change",
  price_change: "Price change",
};

let MSG = null;
let CANDS = [];
let RESULT = null;

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

async function boot() {
  const r = await fetch("/api/state").then((x) => x.json());
  const sel = $("#msg");
  (r.messages || []).forEach((id) => {
    const o = document.createElement("option");
    o.value = id; o.textContent = id;
    sel.appendChild(o);
  });
  $("#key").textContent = r.has_key === false ? "no API_KEY — the page still renders" : "";
  render();
  if ((r.messages || []).length) load(r.messages[0]);
}

async function load(id) {
  MSG = await fetch("/api/message?id=" + encodeURIComponent(id)).then((x) => x.json());
  const c = await fetch("/api/candidates?id=" + encodeURIComponent(id)).then((x) => x.json());
  CANDS = c.candidates || [];
  $("#msg-box").innerHTML =
    '<div class="kv"><span>Message</span><b>' + esc(MSG.message_id) + "</b></div>" +
    '<div class="kv"><span>From</span><b>' + esc(c.vendor || MSG.vendor_id) + "</b></div>" +
    '<p class="body">' + esc(MSG.text) + "</p>";
  $("#cand-box").innerHTML = CANDS.length
    ? CANDS.map((r) =>
        '<div class="cand-row"><b>' + esc(r.record_id) + "</b> — " + esc(r.description) +
        ", qty " + esc(r.qty) + " @ $" + Number(r.unit_cost).toFixed(2) +
        ", ships " + esc(r.ship_date) +
        (r.promo_end ? ' <span class="promo">promo ends ' + esc(r.promo_end) + "</span>" : "") +
        "</div>").join("")
    : '<p class="empty">Blocking found no open record for this sender’s product — a genuine NONE case.</p>';
  RESULT = null;
  render();
}

function render() {
  const box = $("#out");
  if (!RESULT) {
    box.innerHTML = '<p class="empty">No run yet — press Check to match this message and compute its impact.</p>';
    $("#s-match").textContent = "—";
    $("#s-change").textContent = "—";
    $("#s-cost").textContent = "—";
    $("#s-date").textContent = "—";
    $("#decision").textContent = "";
    return;
  }
  const r = RESULT;
  const matchLabel = r.match === "NONE" ? "No matching record"
    : r.match === "UNSURE" ? "Unsure — hand to a person" : r.match;
  box.innerHTML =
    '<div class="kv"><span>Match</span><b>' + esc(matchLabel) + "</b></div>" +
    (r.change_type ? '<div class="kv"><span>Change</span><b>' +
      esc(CHANGE_LABEL[r.change_type] || r.change_type) + "</b></div>" : "") +
    (r.citation ? '<p class="ev">' + esc(r.citation) + "</p>" : "");

  $("#s-match").textContent = r.match || "—";
  $("#s-change").textContent = r.change_type ? (CHANGE_LABEL[r.change_type] || r.change_type) : "—";
  const impact = r.computed_impact || {};
  $("#s-cost").textContent = impact.cost_impact_usd != null
    ? (impact.cost_impact_usd >= 0 ? "+$" : "-$") + Math.abs(impact.cost_impact_usd).toFixed(2) : "—";
  $("#s-date").textContent = impact.in_stock_date_delta_days != null
    ? (impact.in_stock_date_delta_days >= 0 ? "+" : "") + impact.in_stock_date_delta_days + "d" : "—";

  const dec = $("#decision");
  if (r.decision) {
    dec.textContent = r.decision === "escalate"
      ? "ESCALATE — above the materiality threshold, or a live promotion is missed."
      : "AUTO-ACCEPT — within the materiality threshold.";
    dec.classList.toggle("esc", r.decision === "escalate");
  } else {
    dec.textContent = "";
    dec.classList.remove("esc");
  }
}

$("#msg").addEventListener("change", (e) => load(e.target.value));

$("#go").addEventListener("click", async () => {
  const note = $("#note");
  note.hidden = true;
  $("#go").disabled = true;
  $("#go").textContent = "Checking…";
  try {
    const r = await fetch("/api/check", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message_id: $("#msg").value }),
    }).then((x) => x.json());
    if (r.note) { note.textContent = r.note; note.hidden = false; }
    if (r.match !== undefined && r.match !== null) { RESULT = r; }
    render();
  } finally {
    $("#go").disabled = false;
    $("#go").textContent = "Check";
  }
});

boot();
