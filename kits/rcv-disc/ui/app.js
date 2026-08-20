/* The whole UI. No framework, no build step — the same rule every kit in this repo follows.
 *
 * ⚠︎ THE UI COMPUTES NO DETERMINATION. It renders what /api/check returned and nothing else — the
 * resolve logic lives once, in src/resolve.py, and this file only displays it.
 *
 * ⚠︎ THE DISCREPANT LINE IS NEVER HIGHLIGHTED BEFORE A RUN. All lines render identically until a
 * result comes back — pre-marking "the odd one out" would hand the reader the answer this kit
 * exists to find, and would make the UI, not the model, the thing doing the finding.
 *
 * ⚠︎ THE UI NEVER OFFERS A WAY TO ISSUE A CHARGEBACK OR A CREDIT. Every result shown here is a
 * proposal for receiving/AP to confirm — there is no button on this page that changes that.
 */
const $ = (s) => document.querySelector(s);
const LIABLE_LABEL = {
  vendor: "Vendor", carrier: "Carrier", internal: "Internal",
  insufficient_evidence: "Insufficient evidence",
};
const DOC_LABEL = { po: "PO", bol: "BOL", received: "Receiving" };

let CASE = null;
let RESULT = null;

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

async function boot() {
  const r = await fetch("/api/state").then((x) => x.json());
  const sel = $("#case");
  (r.cases || []).forEach((id) => {
    const o = document.createElement("option");
    o.value = id; o.textContent = id;
    sel.appendChild(o);
  });
  $("#key").textContent = r.has_key === false ? "no API_KEY — the page still renders" : "";
  render();
  if ((r.cases || []).length) load(r.cases[0]);
}

async function load(id) {
  CASE = await fetch("/api/case?id=" + encodeURIComponent(id)).then((x) => x.json());
  $("#case-box").innerHTML =
    '<div class="kv"><span>Case</span><b>' + esc(CASE.case_id) + "</b></div>" +
    '<div class="kv"><span>PO</span><b>' + esc(CASE.po_number) + "</b></div>" +
    '<div class="kv"><span>Carrier</span><b>' + esc(CASE.carrier_name) + "</b></div>" +
    '<div class="kv"><span>Lines</span><b>' + (CASE.lines || []).length + "</b></div>";

  $("#lines").innerHTML = (CASE.lines || []).map((l) =>
    '<div class="ln"><span class="lsku">' + esc(l.sku) + "</span>" +
    '<span class="lq">PO <b>' + l.po_qty + "</b></span>" +
    '<span class="lq">BOL <b>' + l.bol_qty + "</b></span>" +
    '<span class="lq">Received <b>' + l.received_qty + "</b></span></div>"
  ).join("");

  $("#exc-box").innerHTML = CASE.carrier_exception
    ? "Carrier exception on file: “" + esc(CASE.carrier_exception) + "”"
    : '<span class="none">No carrier exception on file for this case.</span>';

  // A new case invalidates the last case's result — leaving it on screen beside a different
  // record would attribute one case's determination to another.
  RESULT = null;
  render();
}

function render() {
  const box = $("#result");
  if (!RESULT) {
    box.innerHTML = '<p class="empty">No run yet — click Resolve to check this case.</p>';
  } else {
    const lp = RESULT.liable_party;
    const cls = lp ? "on-" + lp : "pending";
    box.innerHTML = '<div class="verdict ' + cls + '">' +
      (lp ? esc(LIABLE_LABEL[lp] || lp) : "—") + "</div>";
  }

  $("#s-sku").textContent = RESULT && RESULT.discrepant_sku ? RESULT.discrepant_sku : "—";

  const hasQty = RESULT && RESULT.doc_a && RESULT.doc_b;
  $("#s-qty").textContent = hasQty
    ? (DOC_LABEL[RESULT.doc_a] || RESULT.doc_a) + " " + RESULT.qty_a + " / " +
      (DOC_LABEL[RESULT.doc_b] || RESULT.doc_b) + " " + RESULT.qty_b
    : "—";
  $("#s-delta").textContent = RESULT && RESULT.delta != null ? RESULT.delta : "—";

  $("#notice-box").textContent = RESULT && RESULT.notice_text
    ? RESULT.notice_text : (RESULT ? "(no notice text returned)" : "");
}

$("#case").addEventListener("change", (e) => load(e.target.value));

$("#go").addEventListener("click", async () => {
  const note = $("#note");
  note.hidden = true;
  $("#go").disabled = true;
  $("#go").textContent = "Resolving…";
  try {
    const r = await fetch("/api/check", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ case_id: $("#case").value }),
    }).then((x) => x.json());
    if (r.note) { note.textContent = r.note; note.hidden = false; }
    RESULT = r.liable_party !== undefined ? r : null;
    render();
  } finally {
    $("#go").disabled = false;
    $("#go").textContent = "Resolve";
  }
});

boot();
