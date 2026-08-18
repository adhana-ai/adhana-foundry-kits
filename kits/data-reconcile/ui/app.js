/* The whole UI. No framework, no build step — the same rule every kit in this repo follows.
 *
 * ⚠︎ THE UI COMPUTES NO VERDICTS. It renders what /api/check returned and nothing else — the
 * check logic lives once, in src/reconcile.py, and this file only displays it.
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
  cost: "Unit cost", min_qty: "Minimum order quantity", lead_time: "Lead time",
  ship_to: "Ship-to region", order_value: "Order value",
};

let ORDER = null;
let CHECKS = [];       // the five checks, inert until a run fills them in
let VIEW = "all";

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

const EMPTY_CHECKS = ["cost", "min_qty", "lead_time", "ship_to", "order_value"].map((c) => ({
  check: c, verdict: null, citation: "", expected: null, actual: null,
}));

async function boot() {
  const r = await fetch("/api/state").then((x) => x.json());
  const sel = $("#order");
  (r.orders || []).forEach((id) => {
    const o = document.createElement("option");
    o.value = id; o.textContent = id;
    sel.appendChild(o);
  });
  $("#key").textContent = r.has_key === false ? "no API_KEY — the page still renders" : "";
  CHECKS = EMPTY_CHECKS.map((x) => ({ ...x }));
  render();
  if ((r.orders || []).length) load(r.orders[0]);
}

async function load(id) {
  ORDER = await fetch("/api/order?id=" + encodeURIComponent(id)).then((x) => x.json());
  const agr = await fetch("/api/agreement?supplier_id=" + encodeURIComponent(ORDER.supplier_id))
    .then((x) => x.json());
  const lines = (ORDER.lines || [])
    .map((l) => l.sku + " × " + l.qty + " @ $" + l.unit_cost.toFixed(2)).join(", ");
  $("#order-box").innerHTML =
    '<div class="kv"><span>Order</span><b>' + esc(ORDER.order_id) + "</b></div>" +
    '<div class="kv"><span>Supplier</span><b>' + esc(ORDER.supplier_id) + "</b></div>" +
    '<div class="kv"><span>Lines</span><b>' + esc(lines) + "</b></div>" +
    '<div class="kv"><span>Requested ship window</span><b>' +
      esc(ORDER.requested_ship_days) + " business days</b></div>" +
    '<div class="kv"><span>Ship-to</span><b>' + esc(ORDER.ship_to) + "</b></div>" +
    '<div class="kv"><span>Terms</span><b>' + esc(ORDER.terms) + "</b></div>" +
    '<div class="kv"><span>Total value</span><b>$' +
      Number(ORDER.total_value).toFixed(2) + "</b></div>";
  $("#agr").value = agr.text || "";
  // A new order invalidates the last order's verdicts — leaving them on screen beside a different
  // record would attribute one order's findings to another.
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
      ev = '<p class="ev none">The agreement does not state what this check needs.</p>';
    } else if (c.citation) {
      const bad = c.citation_in_agreement === false
        ? ' <span class="warn">not found in the agreement</span>' : "";
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

  // ⚑ THE RECONCILIATION IS PRINTED, NOT ASSUMED — same discipline as docs-comply's panel, after
  // the Admin console shipped five boxes that did not add up on all seven use-case tiles for five
  // days before anyone subtracted.
  const recon = $("#recon");
  if (!answered) {
    recon.textContent = "No run yet — the boxes fill in once an order is reconciled.";
    recon.classList.remove("bad");
  } else {
    const sum = c.clean + c.defect + c.unverifiable + c.no_verdict;
    recon.textContent = c.clean + " clean + " + c.defect + " defect + " + c.unverifiable +
      " unverifiable + " + c.no_verdict + " no verdict = " + sum + " of " + CHECKS.length +
      " checks";
    recon.classList.toggle("bad", sum !== CHECKS.length);
  }
}

$("#order").addEventListener("change", (e) => load(e.target.value));

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
  $("#go").textContent = "Reconciling…";
  try {
    const r = await fetch("/api/check", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ order_id: $("#order").value }),
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
    $("#go").textContent = "Reconcile";
  }
});

boot();
