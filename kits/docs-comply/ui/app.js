/* The whole UI. No framework, no build step — the same rule every kit in this repo follows.
 *
 * ⚠︎ THE UI COMPUTES NO VERDICTS. It renders what /api/check returned and nothing else. UC001
 * learned the cost of the alternative: a ranker ported into JS became a second copy of the
 * behaviour that then had to be held identical to the Python one by a gate. Everything here is
 * display — including the five summary boxes, which come from src/comply.summary().
 *
 * ⚠︎ A `never_addressed` ROW DELIBERATELY SHOWS AN EMPTY EVIDENCE BLOCK rather than the
 * nearest-looking line. Offering a quote that does not decide the rule reads as evidence and is
 * not — it is the single most misleading thing this page could draw, because it makes an absence
 * look like a finding. `src/prompt.py` asks the model for an empty quote on that verdict for the
 * same reason.
 */
const $ = (s) => document.querySelector(s);
const LABEL = { met: "Met", breached: "Breached", never_addressed: "Never addressed" };

let RULES = [];       // the rulebook, then the last result as returned
let VIEW = "all";

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

async function boot() {
  const r = await fetch("/api/state").then((x) => x.json());
  const sel = $("#doc");
  (r.documents || []).forEach((d) => {
    const o = document.createElement("option");
    o.value = d; o.textContent = d;
    sel.appendChild(o);
  });
  $("#key").textContent = r.has_key === false ? "no API_KEY — the page still renders" : "";
  if (r.rule_count) {
    $("#rbline").textContent =
      r.rule_count + " rules, transcribed from " + r.rulebook_section +
      " (" + r.rulebook_edition + " edition) at build time — never written from memory.";
  }
  const rb = await fetch("/api/rulebook").then((x) => x.json());
  // Pre-run, every rule is shown with no verdict — an inert preview of what will be asked.
  RULES = (rb.rules || []).map((x) => ({
    rule: x.id, cite: x.cite, element: x.element, requirement: x.requirement,
    verdict: null, quote: "",
  }));
  render();
  if ((r.documents || []).length) load(r.documents[0]);
}

async function load(id) {
  const r = await fetch("/api/doc?id=" + encodeURIComponent(id)).then((x) => x.json());
  $("#src").value = r.text || "";
  // A new document invalidates the last document's verdicts. Leaving them on screen beside a
  // different record would attribute one document's findings to another — the worst thing a
  // compliance panel can do, and it costs one line to prevent.
  RULES = RULES.map((x) => ({ ...x, verdict: null, quote: "", quote_in_doc: null }));
  render();
}

function counts() {
  const c = { met: 0, breached: 0, never_addressed: 0, no_verdict: 0 };
  RULES.forEach((x) => { if (x.verdict in c) c[x.verdict]++; else c.no_verdict++; });
  return c;
}

function render() {
  const box = $("#rules");
  box.innerHTML = "";
  const shown = RULES.filter((c) => VIEW === "all" || c.verdict === VIEW);
  if (!shown.length) {
    box.innerHTML = '<p class="empty">Nothing in this view.</p>';
  }
  shown.forEach((c) => {
    const row = document.createElement("div");
    row.className = "rule " + (c.verdict || "pending");
    let ev;
    if (c.verdict === "never_addressed") {
      ev = '<p class="ev none">No line in the document addresses this requirement.</p>';
    } else if (c.quote) {
      // `quote_in_doc` is checked in Python, not here — see the header note. false means the
      // model produced a line the document does not contain, which is worth showing loudly.
      const bad = c.quote_in_doc === false
        ? ' <span class="warn">not found in the document</span>' : "";
      ev = '<p class="ev">' + esc(c.quote) + bad + "</p>";
    } else {
      ev = "";
    }
    row.innerHTML =
      '<span class="v"><span class="rid">' + esc(c.rule) + "</span>" +
      (c.verdict ? esc(LABEL[c.verdict]) : "—") + "</span>" +
      '<div class="body"><span class="cite">' + esc(c.cite) + "</span>" +
      '<p class="txt">' + esc(c.requirement || c.element) + "</p>" + ev + "</div>";
    box.appendChild(row);
  });

  const c = counts();
  const answered = RULES.some((x) => x.verdict);
  $("#s-total").textContent = RULES.length || "—";
  $("#s-met").textContent = answered ? c.met : "—";
  $("#s-brk").textContent = answered ? c.breached : "—";
  $("#s-gap").textContent = answered ? c.never_addressed : "—";
  $("#s-nov").textContent = answered ? c.no_verdict : "—";

  // ⚑ THE RECONCILIATION IS PRINTED, NOT ASSUMED. The Admin console shipped use-case tiles whose
  // five numbers did not add up, on all seven kits, for five days — found by someone subtracting.
  // Showing the arithmetic means the page cannot quietly disagree with itself.
  const recon = $("#recon");
  if (!answered) {
    recon.textContent = "No run yet — the boxes fill in once a document is checked.";
    recon.classList.remove("bad");
  } else {
    const sum = c.met + c.breached + c.never_addressed + c.no_verdict;
    recon.textContent = c.met + " met + " + c.breached + " breached + " + c.never_addressed +
      " never addressed + " + c.no_verdict + " no verdict = " + sum + " of " + RULES.length +
      " rules";
    recon.classList.toggle("bad", sum !== RULES.length);
  }
}

$("#doc").addEventListener("change", (e) => load(e.target.value));

$("#viewseg").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  VIEW = b.dataset.view;
  [...e.currentTarget.querySelectorAll("button")].forEach((x) => x.classList.toggle("on", x === b));
  render();
});

$("#go").addEventListener("click", async () => {
  const note = $("#note");
  note.hidden = true;
  $("#go").disabled = true;
  $("#go").textContent = "Checking…";
  try {
    const r = await fetch("/api/check", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("#doc").value }),
    }).then((x) => x.json());
    if (r.note) { note.textContent = r.note; note.hidden = false; }
    if (r.rules) {
      // The reply carries verdicts keyed by rule id; the requirement text stays local so the
      // response does not have to re-send the whole rulebook on every check.
      const by = {};
      r.rules.forEach((x) => { by[x.rule] = x; });
      RULES = RULES.map((x) => ({ ...x, ...(by[x.rule] || {}) }));
    }
    render();
  } finally {
    $("#go").disabled = false;
    $("#go").textContent = "Check against rulebook";
  }
});

boot();
