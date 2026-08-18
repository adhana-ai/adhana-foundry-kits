/* The whole UI. No framework, no build step — the same rule every kit in this repo follows.
 *
 * ⚠︎ THE UI COMPUTES NO FORECAST NUMBER. It renders what /api/check returned and nothing else --
 * the verdicts, the merge decision and the forecast arithmetic all live once, in src/match.py,
 * src/decide.py and src/forecast.py, and this file only displays them.
 */
const $ = (s) => document.querySelector(s);
const VERDICT_LABEL = { LIKE_ITEM: "Like item", NOT_LIKE_ITEM: "Not like item", UNSURE: "Unsure" };

let REQ = null;
let CANDS = [];
let RESULT = null;

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

async function boot() {
  const r = await fetch("/api/state").then((x) => x.json());
  const sel = $("#req");
  (r.requests || []).forEach((id) => {
    const o = document.createElement("option");
    o.value = id; o.textContent = id;
    sel.appendChild(o);
  });
  $("#key").textContent = r.has_key === false ? "no API_KEY — the page still renders" : "";
  render();
  if ((r.requests || []).length) load(r.requests[0]);
}

async function load(id) {
  REQ = await fetch("/api/request?id=" + encodeURIComponent(id)).then((x) => x.json());
  const c = await fetch("/api/candidates?id=" + encodeURIComponent(id)).then((x) => x.json());
  CANDS = c.candidates || [];
  $("#req-box").innerHTML =
    '<div class="kv"><span>Request</span><b>' + esc(REQ.request_id) + "</b></div>" +
    '<div class="kv"><span>Category</span><b>' + esc(REQ.category) + "</b></div>" +
    '<div class="kv"><span>Material</span><b>' + esc(REQ.material) + "</b></div>" +
    '<div class="kv"><span>Price tier</span><b>' + esc(REQ.price_tier) + "</b></div>" +
    '<div class="kv"><span>Channel</span><b>' + esc(REQ.channel) + "</b></div>" +
    '<div class="kv"><span>Season</span><b>' + esc(REQ.season) + "</b></div>" +
    (REQ.merchant_note ? '<p class="body">' + esc(REQ.merchant_note) + "</p>" : "");
  $("#cand-box").innerHTML = CANDS.length
    ? CANDS.map((r) =>
        '<div class="cand-row"><b>' + esc(r.item_id) + "</b> — " + esc(r.material) +
        ", " + esc(r.price_tier) + ", " + esc(r.channel) + ", " + esc(r.season) +
        ' <span class="promo">wk13 ' + Number(r.wk13_units_per_store).toFixed(1) + " units/store</span>" +
        " <span class=\"sim\">sim " + r.similarity_score.toFixed(2) + "</span>" +
        "</div>").join("")
    : '<p class="empty">Blocking found no prior item in this category — a genuine no-precedent case.</p>';
  RESULT = null;
  render();
}

function render() {
  const box = $("#out");
  if (!RESULT) {
    box.innerHTML = '<p class="empty">No run yet — press Check to match this request against its candidates and draft a forecast.</p>';
    $("#s-analogs").textContent = "—";
    $("#s-lift").textContent = "—";
    $("#s-range").textContent = "—";
    $("#s-conf").textContent = "—";
    $("#decision").textContent = "";
    return;
  }
  const r = RESULT;
  const rows = r.per_candidate || [];
  box.innerHTML = rows.length
    ? rows.map((c) =>
        '<div class="kv"><span>' + esc(c.item_id) + "</span><b class=\"" +
        (c.counted ? "yes" : "no") + "\">" + esc(VERDICT_LABEL[c.verdict] || c.verdict || "no verdict") +
        "</b></div>" + (c.reason ? '<p class="ev">' + esc(c.reason) + "</p>" : "")).join("")
    : '<p class="empty">No candidates to judge.</p>';

  const d = r.draft || {};
  $("#s-analogs").textContent = d.n_like_items != null ? d.n_like_items : "—";
  $("#s-lift").textContent = d.recommended_wk13_units != null ? d.recommended_wk13_units : "—";
  $("#s-range").textContent = (d.wk13_low != null && d.wk13_high != null)
    ? d.wk13_low + "–" + d.wk13_high : "—";
  $("#s-conf").textContent = d.confidence || "—";

  const dec = $("#decision");
  if (d.decision) {
    dec.textContent = d.decision === "draft_ready"
      ? "DRAFT READY — " + (d.why || "")
      : "INSUFFICIENT COMPS — " + (d.why || "hand to a person.");
    dec.classList.toggle("esc", d.decision !== "draft_ready");
  } else {
    dec.textContent = "";
    dec.classList.remove("esc");
  }
}

$("#req").addEventListener("change", (e) => load(e.target.value));

$("#go").addEventListener("click", async () => {
  const note = $("#note");
  note.hidden = true;
  $("#go").disabled = true;
  $("#go").textContent = "Checking…";
  try {
    const r = await fetch("/api/check", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ request_id: $("#req").value }),
    }).then((x) => x.json());
    if (r.note) { note.textContent = r.note; note.hidden = false; }
    if (r.draft !== undefined) { RESULT = r; }
    render();
  } finally {
    $("#go").disabled = false;
    $("#go").textContent = "Check";
  }
});

boot();
