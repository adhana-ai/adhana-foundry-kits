/* The whole UI. No framework, no build step — the same rule every kit in this repo follows.
 *
 * ⚠︎ THE UI COMPUTES NO MATERIALITY AND NO EXCEPTION LIST. It renders what the server returned
 * and nothing else — which items are material lives once, in src/segment.py, and this file only
 * displays them.
 */
const $ = (s) => document.querySelector(s);

let BATCH = null;
let ANSWER = null;

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function fmtUnits(v) {
  return v == null ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

async function boot() {
  const r = await fetch("/api/state").then((x) => x.json());
  const sel = $("#bid");
  (r.batches || []).forEach((id) => {
    const o = document.createElement("option");
    o.value = id; o.textContent = id;
    sel.appendChild(o);
  });
  $("#key").textContent = r.has_key === false ? "no API_KEY — the page still renders" : "";
  render();
  if ((r.batches || []).length) load(r.batches[0]);
}

async function load(id) {
  const r = await fetch("/api/batch?id=" + encodeURIComponent(id)).then((x) => x.json());
  BATCH = r;
  const items = r.packed.items;
  $("#itemhint").textContent = items.length + " of " + r.all_items.length + " flagged items";
  $("#item-box").innerHTML = items.length
    ? items.map((it) => {
        const actual = it.unreliable_evidence ? "actual: unreliable this week" : "actual " + fmtUnits(it.actual_pos_units);
        const flags = [it.lost_sales_oos_flag ? "OOS flag" : null, it.promo_flag ? "promo flag" : null]
          .filter(Boolean).join(" · ");
        return '<div class="gaprow"><div class="gh"><span>' + esc(it.item_id) + " — " + esc(it.item_label) +
          " @ " + esc(it.location) + '</span><span>' + fmtUnits(it.delta_units) +
          (it.delta_pct != null ? " (" + it.delta_pct + "%)" : "") + '</span></div><div class="gv">' +
          "forecast " + fmtUnits(it.forecast_units) + " · " + actual +
          " · prior-year " + fmtUnits(it.prior_year_analog_units) +
          (flags ? " · " + esc(flags) : "") + "</div>" +
          (it.unreliable_evidence ? '<div class="gm">unreliable evidence: recent POS not trustworthy</div>' : "") +
          "</div>";
      }).join("")
    : '<p class="empty">No material exceptions this batch.</p>';
  $("#notes-box").innerHTML = (r.packed.notes || []).map((n) =>
    '<div class="noterow">' + esc(n) + "</div>").join("");

  ANSWER = null;
  render();
}

function render() {
  const box = $("#out");
  const nar = $("#narrative");
  if (!ANSWER) {
    box.innerHTML = '<p class="empty">No draft yet — press Draft brief.</p>';
    nar.hidden = true;
    $("#s-material").textContent = BATCH ? BATCH.pack_meta.items_packed : "—";
    $("#s-answered").textContent = "—";
    $("#s-in").textContent = "—";
    $("#s-out").textContent = "—";
    return;
  }
  const a = ANSWER;
  const items = (a.answer && a.answer.items) || [];
  box.innerHTML = items.length
    ? items.map((it) => {
        const causeClass = it.cause === "unknown" ? "cause unknown" : "cause";
        const badCite = it.citation_ok === false ? " bad" : "";
        const cites = (it.citation_1 || it.citation_2)
          ? '<div class="cite' + badCite + '">1: ' + esc(it.citation_1 || "(none)") +
            '</div><div class="cite' + badCite + '">2: ' + esc(it.citation_2 || "(none)") +
            (it.citation_ok === false ? '<div class="gm">not a real, item-relevant line -- flagged</div>' : "") +
            "</div>"
          : "";
        return '<div class="gaprow2"><div class="gh2"><span>' + esc(it.item_id) +
          '</span><span class="' + causeClass + '">' + esc(it.cause || "no verdict") + "</span></div>" +
          (it.note ? '<div class="gv">' + esc(it.note) + "</div>" : "") + cites +
          (it.unreliable_evidence ? '<div class="gm">unreliable evidence acknowledged</div>' : "") + "</div>";
      }).join("")
    : '<p class="empty">No answer.</p>';

  if (a.answer && a.answer.narrative) {
    nar.hidden = false;
    nar.textContent = a.answer.narrative;
  } else {
    nar.hidden = true;
  }

  $("#s-material").textContent = a.items_material != null ? a.items_material : "—";
  $("#s-answered").textContent = a.items_answered != null ? a.items_answered : "—";
  $("#s-in").textContent = a.input_tokens != null ? a.input_tokens : "—";
  $("#s-out").textContent = a.output_tokens != null ? a.output_tokens : "—";
}

$("#bid").addEventListener("change", (e) => load(e.target.value));

$("#go").addEventListener("click", async () => {
  const note = $("#note");
  note.hidden = true;
  $("#go").disabled = true;
  $("#go").textContent = "Drafting…";
  try {
    const r = await fetch("/api/draft", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ batch_id: $("#bid").value }),
    }).then((x) => x.json());
    if (r.note) { note.textContent = r.note; note.hidden = false; }
    if (r.answer !== undefined) { ANSWER = r; }
    render();
  } finally {
    $("#go").disabled = false;
    $("#go").textContent = "Draft brief";
  }
});

boot();
