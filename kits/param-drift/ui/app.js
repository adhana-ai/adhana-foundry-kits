/* The whole UI. No framework, no build step — the same rule every kit in this repo follows.
 *
 * ⚠︎ THE UI COMPUTES NO CORRECTED VALUE AND NO DEVIATION. It renders what the server returned and
 * nothing else — the window stats, the trend, the outliers and the corrected-value formula all
 * live once, in src/aggregate.py and src/formulas.py, and this file only displays them.
 */
const $ = (s) => document.querySelector(s);

let PARAM = null;
let RESULT = null;
let FLOOR = null;

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

async function boot() {
  const r = await fetch("/api/state").then((x) => x.json());
  const sel = $("#pid");
  (r.parameters || []).forEach((id) => {
    const o = document.createElement("option");
    o.value = id; o.textContent = id;
    sel.appendChild(o);
  });
  $("#key").textContent = r.has_key === false ? "no API_KEY — the page still renders" : "";
  render();
  if ((r.parameters || []).length) load(r.parameters[0]);
}

async function load(id) {
  const r = await fetch("/api/parameter?id=" + encodeURIComponent(id)).then((x) => x.json());
  PARAM = r;
  FLOOR = await fetch("/api/floor?id=" + encodeURIComponent(id)).then((x) => x.json());
  const p = r.parameter;
  $("#param-box").innerHTML =
    '<div class="kv"><span>Parameter</span><b>' + esc(p.parameter_id) + "</b></div>" +
    '<div class="kv"><span>Entity</span><b>' + esc(p.entity) + "</b></div>" +
    '<div class="kv"><span>Configured value</span><b>' + esc(p.configured_value) + " " + esc(p.unit) + "</b></div>" +
    '<div class="kv"><span>Trend</span><b>' + esc(r.facts.trend.direction) +
      (r.facts.trend.delta_pct != null ? " (" + r.facts.trend.delta_pct + "%)" : "") + "</b></div>";
  $("#window-box").innerHTML = r.window.map((w) =>
    '<div class="wrow' + (w.note ? " outlier" : "") + '"><span>' + esc(w.period_label) + '</span><b>' +
    esc(w.observed) + "</b>" + (w.note ? '<span class="note-tag">' + esc(w.note) + "</span>" : "") +
    "</div>").join("");
  RESULT = null;
  render();
}

function render() {
  const box = $("#out");
  if (!RESULT) {
    box.innerHTML = FLOOR
      ? '<p class="empty">Free floor says <b>' + esc(FLOOR.verdict) + '</b> (' + esc(FLOOR.reasons[0]) +
        "). Press Check to get the model's own verdict."
      : '<p class="empty">No run yet — press Check.</p>';
    $("#s-verdict").textContent = "—";
    $("#s-floor").textContent = FLOOR ? FLOOR.verdict : "—";
    $("#s-value").textContent = "—";
    $("#s-dev").textContent = "—";
    $("#decision").textContent = "";
    return;
  }
  const r = RESULT;
  box.innerHTML =
    '<div class="kv"><span>Verdict</span><b>' + esc(r.verdict || "no verdict") + "</b></div>" +
    (r.reason ? '<p class="ev">' + esc(r.reason) + "</p>" : "");

  $("#s-verdict").textContent = r.verdict || "—";
  $("#s-floor").textContent = r.floor_verdict || "—";
  $("#s-value").textContent = r.proposed_value != null ? r.proposed_value : "—";
  $("#s-dev").textContent = r.deviation != null ? (r.deviation >= 0 ? "+" : "") + r.deviation : "—";

  const dec = $("#decision");
  if (r.verdict) {
    dec.textContent = r.verdict === "FLAG"
      ? "FLAGGED — a person should review this parameter; nothing was changed automatically."
      : "HELD — nothing surfaced.";
    dec.classList.toggle("esc", r.verdict === "FLAG");
  } else {
    dec.textContent = "";
    dec.classList.remove("esc");
  }
}

$("#pid").addEventListener("change", (e) => load(e.target.value));

$("#go").addEventListener("click", async () => {
  const note = $("#note");
  note.hidden = true;
  $("#go").disabled = true;
  $("#go").textContent = "Checking…";
  try {
    const r = await fetch("/api/check", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ parameter_id: $("#pid").value }),
    }).then((x) => x.json());
    if (r.note) { note.textContent = r.note; note.hidden = false; }
    if (r.verdict !== undefined) { RESULT = r; }
    render();
  } finally {
    $("#go").disabled = false;
    $("#go").textContent = "Check";
  }
});

boot();
