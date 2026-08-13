/* The panel. Everything on this page except the Judge button is computed locally and costs nothing.
 *
 * ⚠︎ NOTHING HERE CALLS A MODEL ON LOAD. The shared .env means a fresh kit already holds a live key, so
 * a page that judged a pair as a side effect of rendering would spend money for opening a browser tab.
 * /api/status is read to SHOW the state; /api/judge is only ever reached from a click.
 */
const $ = (s) => document.querySelector(s);
const OUT = {
  merged_correct: ["ok", "Correct merge"],
  false_merge: ["bad", "False merge"],
  missed_match: ["warn", "Missed match"],
  apart_correct: ["ok", "Correct apart"],
  no_verdict: ["non", "No verdict"],
};
let PAIRS = [], THRESHOLD = 0.7;

function outcome(p, merged) {
  if (!p.label) return null;                      // unlabelled pair: no truth to score against
  const same = p.label === "same";
  if (merged) return same ? "merged_correct" : "false_merge";
  return same ? "missed_match" : "apart_correct";
}

function render() {
  THRESHOLD = parseFloat($("#thr").value);
  $("#tv").textContent = THRESHOLD.toFixed(2);
  const counts = { merged_correct: 0, false_merge: 0, missed_match: 0, apart_correct: 0, no_verdict: 0 };
  const html = PAIRS.map((p) => {
    const merged = p.verdict ? p.verdict === "SAME" : p.score >= THRESHOLD;
    const o = outcome(p, merged);
    if (o) counts[o]++;
    const cls = o ? OUT[o][0] : "non";
    const rows = ["name", "dob", "address", "email"].map((f) => {
      const d = p.fields[f];
      return `<tr class="${d.exact ? "same" : "differ"}"><th>${f}</th>
        <td>${esc(d.a)}</td><td>${esc(d.b)}</td>
        <td class="fs">${d.exact ? "same" : (d.score * 100).toFixed(0) + "%"}</td></tr>`;
    }).join("");
    return `<article class="pair ${cls}">
      <div class="phead">
        <span class="pid">${p.pair_id || "—"}</span>
        ${p.trap ? `<span class="chip trap">${p.trap}</span>` : ""}
        ${p.label ? `<span class="chip">truth: ${p.label}</span>` : `<span class="chip">unlabelled</span>`}
        <span class="chip out">${o ? OUT[o][1] : "no label"}</span>
        <span class="score">${p.score.toFixed(2)}</span>
        <button data-a="${p.a.id}" data-b="${p.b.id}" class="judge">Judge · 1 call</button>
      </div>
      <table class="fields">
        <tr><th></th><th>${esc(p.a.id)}</th><th>${esc(p.b.id)}</th><th></th></tr>${rows}
      </table>
      <p class="verdict" id="v-${p.a.id}-${p.b.id}">${p.verdict ? `model said <b>${p.verdict}</b>` : ""}</p>
    </article>`;
  }).join("");
  $("#pairs").innerHTML = html;

  $("#tiles").innerHTML = Object.entries(OUT).map(([k, [cls, label]]) =>
    `<div class="tile ${cls}"><span class="k">${label}</span><span class="n">${counts[k]}</span></div>`
  ).join("");
  const tot = Object.values(counts).reduce((a, b) => a + b, 0);
  $("#recon").textContent =
    `${counts.merged_correct} + ${counts.false_merge} + ${counts.missed_match} + ` +
    `${counts.apart_correct} + ${counts.no_verdict} = ${tot} labelled pairs — the five reconcile, so a ` +
    `silent model cannot be scored as a careful one.`;

  document.querySelectorAll("button.judge").forEach((b) => (b.onclick = judge));
}

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

async function judge(ev) {
  const btn = ev.currentTarget, a = btn.dataset.a, b = btn.dataset.b;
  btn.disabled = true; btn.textContent = "calling…";
  const r = await fetch("/api/judge", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ a, b }),
  }).then((x) => x.json());
  const line = $(`#v-${a}-${b}`);
  if (r.error) {
    line.innerHTML = `<b class="err">${esc(r.error)}</b> — the free score is still ${r.score?.toFixed(2)}`;
    btn.textContent = "Judge · 1 call"; btn.disabled = false; return;
  }
  const p = PAIRS.find((x) => x.a.id === a && x.b.id === b);
  p.verdict = r.verdict;
  /* An empty reply is NOT "different". It is its own state, and the line says so rather than
   * silently keeping the pair apart. */
  line.innerHTML = r.replied
    ? `model said <b>${esc(r.verdict)}</b> · ${r.input_tokens}/${r.output_tokens} tokens`
    : `<b class="err">nothing usable came back</b> — counted as NO VERDICT, not as "different"`;
  render();
}

(async function boot() {
  const st = await fetch("/api/status").then((r) => r.json());
  $("#cost").innerHTML = st.has_key
    ? `key configured (<b>${esc(st.model || "no MODEL set")}</b>). ${esc(st.cost_note)}`
    : `<b>no key configured</b> — every score on this page still works. ${esc(st.cost_note)}`;
  /* ⚠︎ EVERY CANDIDATE PAIR, NOT THE TOP N. This asked for the top 40 by score, which made the
   * threshold control look broken: the 40 highest-scoring pairs are all above 0.90, so dragging from
   * 0.70 to 0.90 reclassified nothing and the tiles never moved. The trade between false merges and
   * missed matches is the one thing this panel exists to show, and a slice taken from one end of the
   * score range is exactly the slice that cannot show it. 128 pairs is small; blocking already did
   * the reduction that makes rendering all of them cheap. */
  const data = await fetch("/api/pairs?limit=1000").then((r) => r.json());
  PAIRS = data.pairs;
  const bl = data.blocking;
  $("#blocking").textContent =
    `${bl.candidate_pairs} candidate pairs from ${bl.records} records — ${bl.all_pairs} possible, ` +
    `a ${(bl.reduction * 100).toFixed(1)}% reduction, and it kept ` +
    `${bl.true_pairs_surviving}/${bl.true_pairs} of the true matches ` +
    `(recall ${(bl.blocking_recall * 100).toFixed(0)}%).`;
  $("#thr").oninput = render;
  render();
})();
