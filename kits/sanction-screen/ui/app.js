// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let FIELDS = [];

function row(f, cell) {
  const tr = document.createElement("tr");
  const v = cell && cell.value;
  const span = cell && cell.span;
  const vtxt = v === undefined ? "not checked yet" : (v === null || v === "" ? "not stated" : v);
  const empty = v === undefined || v === null || v === "";
  tr.innerHTML =
    '<td class="n"></td><td class="v' + (empty ? " empty" : "") + '"></td>' +
    '<td class="s' + (span ? "" : " none") + '"></td>';
  tr.children[0].textContent = f.name;
  tr.children[1].textContent = vtxt;
  tr.children[2].textContent = span ? ("§ " + span.section)
    : (cell && cell.spannable === false ? "n/a — fixed value" : "—");
  return tr;
}

function draw(fields) {
  const body = $("rows");
  body.textContent = "";
  FIELDS.forEach((f) => body.appendChild(row(f, fields ? fields[f.name] : undefined)));
  if (!fields) { $("k-filled").textContent = "— filled"; $("k-missing").textContent = "— not stated";
                 $("k-span").textContent = "— with a span"; return; }
  const vals = FIELDS.map((f) => fields[f.name] || {});
  const filled = vals.filter((c) => c.value !== null && c.value !== undefined && c.value !== "");
  $("k-filled").textContent = filled.length + " filled";
  // Six fields are legitimately null on some alerts — an identifier value where the type is
  // `none`, and a date or place of birth the record does not carry. The label says "not stated"
  // rather than "not found", because what the panel knows is that the reply carried nothing, not
  // why. ⚠︎ A PARTIAL DATE IS NOT ONE OF THESE: "1978" is a value and prints as one.
  $("k-missing").textContent = (FIELDS.length - filled.length) + " not stated";
  const spannable = vals.filter((c) => c.spannable !== false && c.value);
  $("k-span").textContent = vals.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
}

const VERDICT_TEXT = {
  same_party: "SAME PARTY — an identifier the rulebook trusts joins these two records",
  not_a_match: "NOT A MATCH — an identifier the rulebook trusts separates them",
  insufficient_information:
    "INSUFFICIENT INFORMATION — the file does not decide this alert either way",
};

const DECIDING_TEXT = {
  passport_number: "the passport number",
  national_id_number: "the national identity number",
  tax_reference: "the tax reference",
  date_of_birth: "the date of birth",
  place_of_birth: "the place of birth",
  date_of_birth_and_place_of_birth: "the date of birth and the place of birth together",
  none: "nothing on the file — and that IS the answer, not a gap in it",
};

function drawDecided(verdict, deciding, reason, settle, status, flag) {
  const v = $("c-verdict");
  v.textContent = verdict == null ? "—" : (VERDICT_TEXT[verdict] || verdict);
  v.className = verdict == null ? "" : ("vd vd-" + verdict);
  const d = $("c-deciding");
  d.textContent = deciding == null ? "—" : (DECIDING_TEXT[deciding] || deciding);
  d.className = deciding === "none" ? "dec-none" : "";
  $("c-reason").textContent = reason || "—";
  // ⚠︎ TWO DIFFERENT BLANKS, AND SAYING SO IS THE POINT. Before an adjudication has run there is
  // no next step because nothing has been asked; after one, a blank here means the file DID
  // decide, so there is nothing left to go and get. Printing "nothing would settle it" in the
  // first state would be a lie about a question nobody asked.
  $("c-settle").textContent = settle
    || (verdict == null ? "—" : "— (the file decided this one; nothing further is needed)");
  $("c-status").textContent = status == null ? "—" : status;
  $("c-flag").textContent = (flag === null || flag === undefined)
    ? "not computed — one of the two values the rule needs was missing"
    : (flag ? "YES — not dismissible on the file and the account is already live. This is a "
            + "worklist ordering, not a freeze: nothing here stops a payment or closes a case."
            : "no — nothing here needs to jump the queue");
  $("c-flag").className = flag ? "hold" : "";
}

function rulebookTable(r) {
  const box = $("rulebook");
  box.textContent = "";
  const add = (h, rows) => {
    const d = document.createElement("div");
    d.className = "mxb";
    const t = document.createElement("div"); t.className = "mxh"; t.textContent = h;
    d.appendChild(t);
    rows.forEach(([a, b]) => {
      const row2 = document.createElement("div"); row2.className = "mxr";
      const k = document.createElement("span"); k.className = "mxk"; k.textContent = a;
      const val = document.createElement("span"); val.textContent = b;
      row2.appendChild(k); row2.appendChild(val); d.appendChild(row2);
    });
    box.appendChild(d);
  };
  add("Identifier strength tiers", [
    ["strong", r.identifier_tiers.strong.join(", ")],
    ["moderate", r.identifier_tiers.moderate.join(", ")],
    ["weak", r.identifier_tiers.weak.join(", ")],
  ]);
  add("What each tier does", [
    ["strong", r.strong_note],
    ["moderate", r.moderate_note],
    ["weak", r.weak_note],
  ]);
  add("When a moderate identifier is comparable",
      Object.keys(r.comparable).map((k) => [k, r.comparable[k]]));
  add("Identifiers of different types", [["not comparable", r.different_types_note]]);
  add("Decision order — stop at the first check that fires",
      r.decision_order.map((s) => [s.split(".")[0], s.slice(s.indexOf(".") + 2)]));
  add("Minimum moderate agreements to join two records",
      [["threshold", String(r.min_moderate_agreements)]]);
  const p = document.createElement("p");
  p.className = "mxn";
  p.textContent = r.not_an_authority;
  box.appendChild(p);
}

async function load() {
  const d = await (await fetch("/api/fields")).json();
  FIELDS = d.fields;
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set"
    : "no API_KEY — Adjudicate will not call anything";
  draw(null);
  drawDecided(null, null, null, null, null, null);
  rulebookTable(await (await fetch("/api/rulebook")).json());
  show();
}

async function show() {
  const r = await (await fetch("/api/doc?id=" + encodeURIComponent($("doc").value))).json();
  $("text").textContent = r.text || "";
}

async function go() {
  $("go").disabled = true; $("go").textContent = "Adjudicating…"; $("note").hidden = true;
  try {
    const r = await (await fetch("/api/extract", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    draw(r.fields);
    const val = (n) => (r.fields && r.fields[n] ? r.fields[n].value : null);
    drawDecided(val("verdict"), val("deciding_identifier"), r.reason, r.would_settle_it,
                val("account_status"), r.needs_escalation);
  } finally { $("go").disabled = false; $("go").textContent = "Adjudicate"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => {
  draw(null); drawDecided(null, null, null, null, null, null); show();
});
load();
