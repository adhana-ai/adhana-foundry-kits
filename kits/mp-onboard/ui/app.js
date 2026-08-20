/* The whole UI. No framework, no build step — the same rule every kit in this repo follows.
 *
 * ⚠︎ THE UI COMPUTES NO CROSS-CHECK. It renders what /api/check returned and nothing else — the
 * cross-check logic lives once, in src/onboard.py, and this file only displays it.
 *
 * ⚠︎ THE UI NEVER OFFERS A WAY TO APPROVE, DENY, OR ESCALATE AN APPLICATION. Every flag shown here
 * is drafted for a verification analyst — there is no button on this page that decides anything.
 *
 * ⚠︎ THE SEVEN FIELD ROWS ARE ALWAYS SHOWN IN THE SAME ORDER, WHETHER OR NOT A ROW LOOKS CLEAN.
 * Reordering by how good a row looks would bury the exact trap the eval exists to measure — an
 * otherwise-spotless application with one mismatched banking field — see data/SOURCES.md.
 */
const $ = (s) => document.querySelector(s);

const FIELDS = ["business_name", "business_address", "tax_id", "bank_account_name",
  "bank_routing_number", "owner_name", "owner_address"];
const FIELD_LABEL = {
  business_name: "Business name", business_address: "Business address", tax_id: "Tax ID",
  bank_account_name: "Bank account name", bank_routing_number: "Bank routing number",
  owner_name: "Owner name", owner_address: "Owner address",
};
const FIELD_DOC_LABEL = {
  business_name: "business registration · legal_name",
  business_address: "business registration · registered_address",
  tax_id: "business registration · tax_id",
  bank_account_name: "bank letter · account_holder_name",
  bank_routing_number: "bank letter · routing_number",
  owner_name: "government ID · full_name",
  owner_address: "government ID · address",
};
const FLAG_LABEL = { match: "Match", mismatch: "Mismatch", mismatch_explained: "Explained" };

let APP = null;
let RESULT = null;

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function docValue(app, field) {
  if (field === "business_name") return app.business_registration.legal_name;
  if (field === "business_address") return app.business_registration.registered_address;
  if (field === "tax_id") return app.business_registration.tax_id;
  if (field === "bank_account_name") return app.bank_letter.account_holder_name;
  if (field === "bank_routing_number") return app.bank_letter.routing_number;
  if (field === "owner_name") return app.id_document.full_name;
  if (field === "owner_address") return app.id_document.address;
  return "";
}

async function boot() {
  const r = await fetch("/api/state").then((x) => x.json());
  const sel = $("#application");
  (r.applications || []).forEach((id) => {
    const o = document.createElement("option");
    o.value = id; o.textContent = id;
    sel.appendChild(o);
  });
  $("#key").textContent = r.has_key === false ? "no API_KEY — the page still renders" : "";
  if ((r.applications || []).length) {
    await load(r.applications[0]);
  } else {
    render();
  }
}

function fieldRow(field, flag) {
  const cls = flag ? (flag === "match" ? "ok" : flag === "mismatch" ? "bad" : "maybe") : "";
  const declared = APP.declared[field];
  const doc = docValue(APP, field);
  return '<div class="stage ' + cls + '"><span class="sn">' +
    (flag ? FLAG_LABEL[flag][0] : "?") + "</span>" +
    '<div class="sbody"><p class="stitle">' + esc(FIELD_LABEL[field]) + "</p>" +
    '<p class="sline"><b>declared</b> ' + esc(declared) + "</p>" +
    '<p class="sline"><b>' + esc(FIELD_DOC_LABEL[field]) + "</b> " + esc(doc) + "</p></div></div>";
}

async function load(id) {
  APP = await fetch("/api/application?id=" + encodeURIComponent(id)).then((x) => x.json());
  $("#app-box").innerHTML =
    '<div class="kv"><span>Application</span><b>' + esc(APP.application_id) + "</b></div>" +
    '<div class="kv"><span>Category</span><b>' + esc(APP.category) + "</b></div>";

  RESULT = null;
  renderFields();
  $("#note-box").textContent = APP.submission_note
    ? "“" + APP.submission_note + "”" : "(no submission note provided)";
  render();
}

function renderFields() {
  // ⚠︎ GUARDED ON APP, NOT JUST RESULT. fieldRow() reads APP.declared -- called from render(),
  // which boot() can reach before load() has set APP (see the no-applications branch above).
  // A blank panel here is honest; a thrown TypeError here previously took the whole page's
  // render() down silently, including the parts that do not depend on APP at all.
  if (!APP) { $("#fields").innerHTML = ""; return; }
  const flags = RESULT || {};
  $("#fields").innerHTML = FIELDS.map((f) => fieldRow(f, flags[f] || null)).join("");
}

function render() {
  renderFields();
  const box = $("#result");
  // ⚠︎ "ANSWERED" MEANS AT LEAST ONE FIELD CAME BACK NON-NULL, NOT "RESULT IS TRUTHY". The
  // no-API_KEY response from /api/check is a real 200 with application_id/note set and all seven
  // fields explicitly null -- nothing was checked. RESULT is still an object, so `!RESULT` alone
  // cannot tell "nothing was called" apart from "called, and every field matched" -- and treating
  // them the same used to render an unchecked application as a green "all fields match" verdict
  // with 0/0/0 stats, the exact false-clean shape this kit exists to catch, coming from its own UI.
  const answered = !!(RESULT && FIELDS.some((f) => RESULT[f] != null));
  if (!answered) {
    box.innerHTML = '<p class="empty">No run yet — click Cross-check to check this application.</p>';
  } else {
    const flagged = FIELDS.filter((f) => RESULT[f] && RESULT[f] !== "match");
    const cls = flagged.length ? "on-mismatch" : "on-match";
    box.innerHTML = '<div class="verdict ' + cls + '">' +
      (flagged.length
        ? flagged.length + " of " + FIELDS.length + " field(s) flagged"
        : "all fields match") + "</div>";
  }

  const counts = { match: 0, mismatch: 0, mismatch_explained: 0 };
  if (answered) FIELDS.forEach((f) => { if (RESULT[f] in counts) counts[RESULT[f]]++; });
  $("#s-match").textContent = answered ? counts.match : "—";
  $("#s-mismatch").textContent = answered ? counts.mismatch : "—";
  $("#s-explained").textContent = answered ? counts.mismatch_explained : "—";

  const misStat = document.querySelector(".stat.mis");
  if (misStat) misStat.classList.toggle("hot", !!(RESULT && counts.mismatch > 0));

  $("#summary-box").textContent = RESULT && RESULT.summary
    ? RESULT.summary : (RESULT ? "(no summary text returned)" : "");
}

$("#application").addEventListener("change", (e) => load(e.target.value));

$("#go").addEventListener("click", async () => {
  const note = $("#note");
  note.hidden = true;
  $("#go").disabled = true;
  $("#go").textContent = "Checking…";
  try {
    const r = await fetch("/api/check", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ application_id: $("#application").value }),
    }).then((x) => x.json());
    if (r.note) { note.textContent = r.note; note.hidden = false; }
    RESULT = r.business_name !== undefined ? r : null;
    render();
  } finally {
    $("#go").disabled = false;
    $("#go").textContent = "Cross-check";
  }
});

boot();
