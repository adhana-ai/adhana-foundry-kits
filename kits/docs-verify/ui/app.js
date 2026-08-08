/* The whole UI. No framework, no build step — the same rule every kit in this repo follows.
 *
 * ⚠︎ THE UI COMPUTES NO VERDICTS. It renders what /api/verify returned and nothing else. UC001
 * learned the cost of the alternative: a ranker ported into JS became a second copy of the
 * behaviour that then had to be held identical to the Python one by a gate. Everything here is
 * display.
 *
 * ⚠︎ A `not_stated` ROW DELIBERATELY SHOWS AN EMPTY EVIDENCE BLOCK rather than the nearest-looking
 * line. Offering a quote that does not decide the claim reads as evidence and is not — it is the
 * single most misleading thing this page could draw, because it makes an absence look like a
 * finding. `src/prompt.py` asks the model for an empty quote on that verdict for the same reason.
 */
const $ = (s) => document.querySelector(s);
const LABEL = { supported: "Supported", contradicted: "Contradicted", not_stated: "Not stated" };

let CLAIMS = [];      // last result, as returned
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
  if ((r.documents || []).length) load(r.documents[0]);
}

async function load(id) {
  const r = await fetch("/api/doc?id=" + encodeURIComponent(id)).then((x) => x.json());
  $("#src").value = r.text || "";
  // Pre-run, the claims are shown with no verdict — an inert preview of what will be asked.
  CLAIMS = (r.claims || []).map((c) => ({ claim: c.text, verdict: null, quote: "" }));
  render();
}

function counts() {
  const c = { supported: 0, contradicted: 0, not_stated: 0 };
  CLAIMS.forEach((x) => { if (x.verdict in c) c[x.verdict]++; });
  return c;
}

function render() {
  const box = $("#claims");
  box.innerHTML = "";
  const shown = CLAIMS.filter((c) => VIEW === "all" || c.verdict === VIEW);
  if (!shown.length) {
    box.innerHTML = '<p class="empty">Nothing in this view.</p>';
  }
  shown.forEach((c) => {
    const row = document.createElement("div");
    row.className = "claim " + (c.verdict || "pending");
    let ev;
    if (c.verdict === "not_stated") {
      ev = '<p class="ev none">No sentence in the source addresses this claim.</p>';
    } else if (c.quote) {
      // `quote_in_doc` is checked in Python, not here — see the header note. false means the
      // model produced a sentence the document does not contain, which is worth showing loudly.
      const bad = c.quote_in_doc === false
        ? ' <span class="warn">not found in the source</span>' : "";
      ev = '<p class="ev">' + esc(c.quote) + bad + "</p>";
    } else {
      ev = "";
    }
    row.innerHTML =
      '<span class="v">' + (c.verdict ? esc(LABEL[c.verdict]) : "—") + "</span>" +
      '<div class="body"><p class="txt">' + esc(c.claim) + "</p>" + ev + "</div>";
    box.appendChild(row);
  });
  const c = counts();
  $("#s-total").textContent = CLAIMS.length || "—";
  $("#s-sup").textContent = c.supported;
  $("#s-con").textContent = c.contradicted;
  $("#s-not").textContent = c.not_stated;
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
    const r = await fetch("/api/verify", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("#doc").value }),
    }).then((x) => x.json());
    if (r.note) { note.textContent = r.note; note.hidden = false; }
    if (r.claims) CLAIMS = r.claims;
    render();
  } finally {
    $("#go").disabled = false;
    $("#go").textContent = "Check claims";
  }
});

boot();
