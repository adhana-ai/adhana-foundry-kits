/* The whole UI. No framework, no build step — the same rule every kit in this repo follows.
 *
 * ⚠︎ THE UI COMPUTES NO VERDICTS. It renders what /api/check returned and nothing else — the
 * check logic lives once, in src/close.py, and this file only displays it.
 *
 * ⚠︎ THE UI NEVER OFFERS A WAY TO POST, APPROVE OR CLEAR ANYTHING. Every verdict shown here is a
 * draft for a preparer/reviewer to act on outside this kit — there is no button on this page that
 * changes that.
 *
 * ⚠︎ AN `unverifiable` ROW DELIBERATELY SHOWS AN EMPTY EVIDENCE BLOCK rather than the
 * nearest-looking clause. Offering a citation that does not decide the check reads as evidence and
 * is not — it is the single most misleading thing this page could draw, because it makes a gap
 * look like a finding. src/prompt.py asks the model for an empty citation on that verdict for the
 * same reason.
 */
const $ = (s) => document.querySelector(s);
const LABEL = { clean: "Clean", defect: "Defect", unverifiable: "Unverifiable" };
const CHECK_LABEL = {
  account: "Posting account", amount: "Amount vs. prior approved", basis: "Calculation basis",
  residual: "Reconciliation residual",
};

let CYCLE = null;
let CHECKS = [];       // the four checks, inert until a run fills them in
let VIEW = "all";

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

const EMPTY_CHECKS = ["account", "amount", "basis", "residual"].map((c) => ({
  check: c, verdict: null, citation: "", expected: null, actual: null,
}));

async function boot() {
  const r = await fetch("/api/state").then((x) => x.json());
  const sel = $("#cycle");
  (r.cycles || []).forEach((id) => {
    const o = document.createElement("option");
    o.value = id; o.textContent = id;
    sel.appendChild(o);
  });
  $("#key").textContent = r.has_key === false ? "no API_KEY — the page still renders" : "";
  CHECKS = EMPTY_CHECKS.map((x) => ({ ...x }));
  render();
  if ((r.cycles || []).length) load(r.cycles[0]);
}

async function load(id) {
  CYCLE = await fetch("/api/cycle?id=" + encodeURIComponent(id)).then((x) => x.json());
  const basis = await fetch("/api/basis?rje_id=" + encodeURIComponent(CYCLE.rje_id))
    .then((x) => x.json());
  $("#cycle-box").innerHTML =
    '<div class="kv"><span>Close cycle</span><b>' + esc(CYCLE.close_id) + "</b></div>" +
    '<div class="kv"><span>Recurring template</span><b>' + esc(CYCLE.rje_id) + "</b></div>" +
    '<div class="kv"><span>Period</span><b>' + esc(CYCLE.period) + "</b></div>" +
    '<div class="kv"><span>Drafted account</span><b>' +
      esc(CYCLE.je_account_id) + " — " + esc(CYCLE.je_account_name) + "</b></div>" +
    '<div class="kv"><span>Drafted amount</span><b>$' +
      Number(CYCLE.je_amount).toFixed(2) + "</b></div>" +
    '<div class="kv"><span>Drafted basis note</span><b>' + esc(CYCLE.je_basis_note) + "</b></div>" +
    '<div class="kv"><span>GL balance</span><b>$' +
      Number(CYCLE.recon_gl_balance).toFixed(2) + "</b></div>" +
    '<div class="kv"><span>Supporting balance</span><b>$' +
      Number(CYCLE.recon_supporting_balance).toFixed(2) + "</b></div>" +
    '<div class="kv"><span>Residual</span><b>$' +
      Number(CYCLE.recon_residual).toFixed(2) + "</b></div>";
  $("#basis").value = basis.text || "";
  // A new cycle invalidates the last cycle's verdicts — leaving them on screen beside a different
  // record would attribute one cycle's findings to another.
  CHECKS = EMPTY_CHECKS.map((x) => ({ ...x }));
  render();
}

function counts() {
  const c = { clean: 0, defect: 0, unverifiable: 0, no_verdict: 0 };
  CHECKS.forEach((x) => { if (x.verdict in c) c[x.verdict]++; else c.no_verdict++; });
  return c;
}

function render() {
  const box = $("#checks");
  box.innerHTML = "";
  const shown = CHECKS.filter((c) => VIEW === "all" || c.verdict === VIEW);
  if (!shown.length) {
    box.innerHTML = '<p class="empty">Nothing in this view.</p>';
  }
  shown.forEach((c) => {
    const row = document.createElement("div");
    row.className = "chk " + (c.verdict || "pending");
    let ev;
    if (c.verdict === "unverifiable") {
      ev = '<p class="ev none">The basis document does not state what this check needs.</p>';
    } else if (c.citation) {
      const bad = c.citation_in_basis === false
        ? ' <span class="warn">not found in the basis document</span>' : "";
      ev = '<p class="ev">' + esc(c.citation) + bad + "</p>";
    } else {
      ev = "";
    }
    const vals = (c.expected != null || c.actual != null)
      ? '<span class="vals">expected ' + esc(c.expected) + " · actual " + esc(c.actual) + "</span>"
      : "";
    row.innerHTML =
      '<span class="v"><span class="cid">' + esc(c.check) + "</span>" +
      (c.verdict ? esc(LABEL[c.verdict]) : "—") + "</span>" +
      '<div class="body"><p class="txt">' + esc(CHECK_LABEL[c.check] || c.check) + "</p>" +
      vals + ev + "</div>";
    box.appendChild(row);
  });

  const c = counts();
  const answered = CHECKS.some((x) => x.verdict);
  $("#s-total").textContent = CHECKS.length || "—";
  $("#s-cln").textContent = answered ? c.clean : "—";
  $("#s-dft").textContent = answered ? c.defect : "—";
  $("#s-unv").textContent = answered ? c.unverifiable : "—";
  $("#s-nov").textContent = answered ? c.no_verdict : "—";

  // ⚑ THE RECONCILIATION IS PRINTED, NOT ASSUMED — same discipline as data-reconcile's panel,
  // after the Admin console shipped five boxes that did not add up on all seven use-case tiles for
  // five days before anyone subtracted.
  const recon = $("#recon");
  if (!answered) {
    recon.textContent = "No run yet — the boxes fill in once a close cycle is checked.";
    recon.classList.remove("bad");
  } else {
    const sum = c.clean + c.defect + c.unverifiable + c.no_verdict;
    recon.textContent = c.clean + " clean + " + c.defect + " defect + " + c.unverifiable +
      " unverifiable + " + c.no_verdict + " no verdict = " + sum + " of " + CHECKS.length +
      " checks";
    recon.classList.toggle("bad", sum !== CHECKS.length);
  }
}

$("#cycle").addEventListener("change", (e) => load(e.target.value));

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
      body: JSON.stringify({ close_id: $("#cycle").value }),
    }).then((x) => x.json());
    if (r.note) { note.textContent = r.note; note.hidden = false; }
    if (r.checks) {
      const by = {};
      r.checks.forEach((x) => { by[x.check] = x; });
      CHECKS = CHECKS.map((x) => ({ ...x, ...(by[x.check] || {}) }));
    }
    render();
  } finally {
    $("#go").disabled = false;
    $("#go").textContent = "Check";
  }
});

boot();
