/* The whole UI. No framework, no build step — the same rule every kit in this repo follows.
 *
 * ⚠︎ THE UI COMPUTES NO TRACE. It renders what /api/check returned and nothing else — the tracing
 * logic lives once, in src/payrun.py, and this file only displays it.
 *
 * ⚠︎ THE UI NEVER OFFERS A WAY TO RELEASE A PAYMENT, CHANGE A REMITTANCE DETAIL, OR COMMIT TO A
 * DATE BEYOND THE SCHEDULED RUN. Every reply shown here is informational, drafted for AP review
 * when an exception is open — there is no button on this page that changes that.
 *
 * ⚠︎ THE FOUR STAGE ROWS ARE ALWAYS SHOWN IN ORDER, EVEN THOUGH ONE OF THEM MAY LOOK "DONE" WHILE
 * AN EARLIER ONE GOVERNS. Reordering them by how complete they look would hide the exact trap the
 * eval exists to measure — see data/SOURCES.md.
 */
const $ = (s) => document.querySelector(s);
const STAGE_LABEL = {
  match_exception: "Match exception", approval_exception: "Approval exception",
  awaiting_run_inclusion: "Awaiting run inclusion", in_scheduled_run: "In scheduled run",
  remitted: "Remitted",
};

let INV = null;
let RESULT = null;

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

async function boot() {
  const r = await fetch("/api/state").then((x) => x.json());
  const sel = $("#invoice");
  (r.invoices || []).forEach((id) => {
    const o = document.createElement("option");
    o.value = id; o.textContent = id;
    sel.appendChild(o);
  });
  $("#key").textContent = r.has_key === false ? "no API_KEY — the page still renders" : "";
  render();
  if ((r.invoices || []).length) load(r.invoices[0]);
}

function stageRow(n, label, cls, lines) {
  return '<div class="stage ' + cls + '"><span class="sn">' + n + "</span>" +
    '<div class="sbody"><p class="stitle">' + esc(label) + "</p>" +
    lines.map((l) => '<p class="sline">' + l + "</p>").join("") + "</div></div>";
}

async function load(id) {
  INV = await fetch("/api/invoice?id=" + encodeURIComponent(id)).then((x) => x.json());
  $("#inv-box").innerHTML =
    '<div class="kv"><span>Invoice</span><b>' + esc(INV.invoice_id) + "</b></div>" +
    '<div class="kv"><span>Vendor</span><b>' + esc(INV.vendor_name) + "</b></div>" +
    '<div class="kv"><span>PO</span><b>' + esc(INV.po_number) + "</b></div>" +
    '<div class="kv"><span>Amount</span><b>$' + Number(INV.amount).toFixed(2) + "</b></div>" +
    '<div class="kv"><span>Submitted</span><b>' + esc(INV.submitted_date) + "</b></div>";

  const m = INV.match, a = INV.approval, ri = INV.run_inclusion, rm = INV.remittance;
  $("#stages").innerHTML =
    stageRow(1, "Match", m.matched ? "ok" : "bad",
      [m.matched ? "matched: true" : "matched: false — " + esc(m.reason)]) +
    stageRow(2, "Approval", a.status === "exception" ? "bad" : "ok",
      ["status: " + esc(a.status) + (a.status === "exception" ? " — " + esc(a.reason) : "")]) +
    stageRow(3, "Run inclusion", ri.included ? "maybe" : "bad",
      ri.included
        ? ["included: true — run " + esc(ri.run_id) + ", scheduled " + esc(ri.scheduled_date)]
        : ["included: false — " + esc(ri.reason)]) +
    stageRow(4, "Remittance", rm.remitted ? "maybe" : "bad",
      rm.remitted
        ? ["remitted: true — " + esc(rm.remittance_date) + ", " + esc(rm.method) + ", ref " +
           esc(rm.reference)]
        : ["remitted: false — " + esc(rm.reason)]);

  $("#inquiry-box").textContent = "“" + (INV.inquiry || "") + "”";

  RESULT = null;
  render();
}

function render() {
  const box = $("#result");
  if (!RESULT) {
    box.innerHTML = '<p class="empty">No run yet — click Trace to check this invoice.</p>';
  } else {
    const stage = RESULT.current_stage;
    const cls = stage ? "on-" + stage : "pending";
    box.innerHTML = '<div class="verdict ' + cls + '">' +
      (stage ? esc(STAGE_LABEL[stage] || stage) : "—") + "</div>";
  }

  $("#s-stage").textContent = RESULT && RESULT.current_stage
    ? (STAGE_LABEL[RESULT.current_stage] || RESULT.current_stage) : "—";
  $("#s-review").textContent = RESULT
    ? (RESULT.requires_ap_review ? "Required" : "Not required") : "—";
  $("#s-date").textContent = RESULT ? (RESULT.stated_date || "none stated") : "—";

  const reviewStat = document.querySelector(".stat.rev");
  if (reviewStat) reviewStat.classList.toggle("hot", !!(RESULT && RESULT.requires_ap_review));

  $("#reply-box").textContent = RESULT && RESULT.reply
    ? RESULT.reply : (RESULT ? "(no reply text returned)" : "");
}

$("#invoice").addEventListener("change", (e) => load(e.target.value));

$("#go").addEventListener("click", async () => {
  const note = $("#note");
  note.hidden = true;
  $("#go").disabled = true;
  $("#go").textContent = "Tracing…";
  try {
    const r = await fetch("/api/check", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ invoice_id: $("#invoice").value }),
    }).then((x) => x.json());
    if (r.note) { note.textContent = r.note; note.hidden = false; }
    RESULT = r.current_stage !== undefined ? r : null;
    render();
  } finally {
    $("#go").disabled = false;
    $("#go").textContent = "Trace";
  }
});

boot();
