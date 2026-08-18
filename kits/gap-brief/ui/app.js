/* The whole UI. No framework, no build step — the same rule every kit in this repo follows.
 *
 * ⚠︎ THE UI COMPUTES NO MATERIALITY AND NO GAP LIST. It renders what the server returned and
 * nothing else — which gaps are material lives once, in src/segment.py, and this file only
 * displays them.
 */
const $ = (s) => document.querySelector(s);

let CYCLE = null;
let ANSWER = null;

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function fmtUsd(v) {
  return v == null ? "—" : "$" + Number(v).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

async function boot() {
  const r = await fetch("/api/state").then((x) => x.json());
  const sel = $("#cid");
  (r.cycles || []).forEach((id) => {
    const o = document.createElement("option");
    o.value = id; o.textContent = id;
    sel.appendChild(o);
  });
  $("#key").textContent = r.has_key === false ? "no API_KEY — the page still renders" : "";
  render();
  if ((r.cycles || []).length) load(r.cycles[0]);
}

async function load(id) {
  const r = await fetch("/api/cycle?id=" + encodeURIComponent(id)).then((x) => x.json());
  CYCLE = r;
  const gaps = r.packed.gaps;
  $("#gaphint").textContent = gaps.length + " of " + r.all_items.length + " line items";
  $("#gap-box").innerHTML = gaps.length
    ? gaps.map((g) => {
        const v = g.views;
        const vtxt = ["demand", "supply", "financial"].map((k) => {
          const val = v[k + "_plan_usd"];
          return k + " " + (val == null ? "not submitted" : fmtUsd(val));
        }).join(" · ");
        return '<div class="gaprow"><div class="gh"><span>' + esc(g.item_id) + " — " + esc(g.item_label) +
          '</span><span>' + fmtUsd(g.delta_usd) + (g.delta_pct != null ? " (" + g.delta_pct + "%)" : "") +
          '</span></div><div class="gv">' + esc(vtxt) + "</div>" +
          (g.missing_view ? '<div class="gm">missing view: ' + esc(g.missing_view) + "</div>" : "") +
          "</div>";
      }).join("")
    : '<p class="empty">No material gaps this cycle.</p>';
  $("#notes-box").innerHTML = r.cycle_notes_html || (r.packed.notes || []).map((n) =>
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
    $("#s-material").textContent = CYCLE ? CYCLE.pack_meta.gaps_packed : "—";
    $("#s-answered").textContent = "—";
    $("#s-in").textContent = "—";
    $("#s-out").textContent = "—";
    return;
  }
  const a = ANSWER;
  const gaps = (a.answer && a.answer.gaps) || [];
  box.innerHTML = gaps.length
    ? gaps.map((g) => {
        const causeClass = g.cause === "unknown" ? "cause unknown" : "cause";
        const badCite = g.citation_ok === false ? " bad" : "";
        const cites = (g.citation_1 || g.citation_2)
          ? '<div class="cite' + badCite + '">1: ' + esc(g.citation_1 || "(none)") +
            '</div><div class="cite' + badCite + '">2: ' + esc(g.citation_2 || "(none)") +
            (g.citation_ok === false ? '<div class="gm">not a real, item-relevant line -- flagged</div>' : "") +
            "</div>"
          : "";
        return '<div class="gaprow2"><div class="gh2"><span>' + esc(g.item_id) +
          '</span><span class="' + causeClass + '">' + esc(g.cause || "no verdict") + "</span></div>" +
          (g.note ? '<div class="gv">' + esc(g.note) + "</div>" : "") + cites +
          (g.missing_view ? '<div class="gm">missing view acknowledged</div>' : "") + "</div>";
      }).join("")
    : '<p class="empty">No answer.</p>';

  if (a.answer && a.answer.narrative) {
    nar.hidden = false;
    nar.textContent = a.answer.narrative;
  } else {
    nar.hidden = true;
  }

  $("#s-material").textContent = a.gaps_material != null ? a.gaps_material : "—";
  $("#s-answered").textContent = a.gaps_answered != null ? a.gaps_answered : "—";
  $("#s-in").textContent = a.input_tokens != null ? a.input_tokens : "—";
  $("#s-out").textContent = a.output_tokens != null ? a.output_tokens : "—";
}

$("#cid").addEventListener("change", (e) => load(e.target.value));

$("#go").addEventListener("click", async () => {
  const note = $("#note");
  note.hidden = true;
  $("#go").disabled = true;
  $("#go").textContent = "Drafting…";
  try {
    const r = await fetch("/api/draft", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ cycle_id: $("#cid").value }),
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
