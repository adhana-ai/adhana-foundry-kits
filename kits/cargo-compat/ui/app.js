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
  // prior_cargo and two_back_cargo are legitimately null on some sheets — the prior cargo may be
  // unrecorded, and a recertified tank has nothing behind it. The label says "not stated" rather
  // than "not found", because what the panel knows is that the reply carried nothing, not why.
  $("k-missing").textContent = (FIELDS.length - filled.length) + " not stated";
  const spannable = vals.filter((c) => c.spannable !== false && c.value);
  $("k-span").textContent = vals.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
}

const VERDICT_TEXT = {
  accept: "ACCEPT — the matrix clears this pair, on the certificate on file",
  clean_then_load: "CLEAN THEN LOAD — the tank needs a stronger certified wash first",
  refuse: "REFUSE — this pair is not made acceptable by cleaning",
  undetermined: "UNDETERMINED — the sheet does not carry what the check needs",
};

function drawDecided(verdict, reason, required, status, flag) {
  const v = $("c-verdict");
  v.textContent = verdict == null ? "—" : (VERDICT_TEXT[verdict] || verdict);
  v.className = verdict == null ? "" : ("vd vd-" + verdict);
  $("c-reason").textContent = reason || "—";
  // ⚠︎ TWO DIFFERENT BLANKS, AND SAYING SO IS THE POINT. Before a check has run there is no
  // threshold because nothing has been asked; after one, a blank means the check STOPPED before
  // it ever reached the wash comparison — an unrecorded prior cargo, a reactive pair or a
  // predecessor ban all settle the verdict earlier. Printing the second sentence in the first
  // state was found by opening the page, not by any check that passes over rendered output.
  $("c-req").textContent = required
    || (verdict == null ? "—" : "— (the check stopped before any wash threshold applied)");
  $("c-status").textContent = status == null ? "—" : status;
  $("c-flag").textContent = (flag === null || flag === undefined)
    ? "not computed — one of the two values the rule needs was missing"
    : (flag ? "YES — not clear-to-load and already loaded. Quarantine it and get a competent "
            + "person to it."
            : "no — nothing here needs a hold");
  $("c-flag").className = flag ? "hold" : "";
}

function matrixTable(m) {
  const box = $("matrix");
  box.textContent = "";
  const add = (h, rows) => {
    const d = document.createElement("div");
    d.className = "mxb";
    const t = document.createElement("div"); t.className = "mxh"; t.textContent = h;
    d.appendChild(t);
    rows.forEach(([a, b]) => {
      const r = document.createElement("div"); r.className = "mxr";
      const k = document.createElement("span"); k.className = "mxk"; k.textContent = a;
      const val = document.createElement("span"); val.textContent = b;
      r.appendChild(k); r.appendChild(val); d.appendChild(r);
    });
    box.appendChild(d);
  };
  add("Cargo classes", Object.keys(m.classes).sort().map((c) => [c, m.classes[c].join(", ")]));
  add("Reactive pairs — refuse outright, symmetric",
      m.reactive_pairs.map((p) => [p.a + " + " + p.b, p.why]));
  add("Look-back depth, by incoming grade",
      Object.keys(m.lookback).map((g) => [g, m.lookback[g] === 1
        ? "1 cargo back (the prior cargo only)"
        : m.lookback[g] + " cargoes back (the prior cargo and the one before it)"]));
  add("Banned predecessors — cleaning does not cure a ban",
      Object.keys(m.banned_predecessor_classes).map((g) => {
        const c = m.banned_predecessor_classes[g] || [];
        const n = m.banned_predecessor_cargoes[g] || [];
        const bits = [];
        if (c.length) bits.push("any cargo of class " + c.join(", "));
        if (n.length) bits.push("plus by name: " + n.join(", "));
        return [g, bits.length ? bits.join("; ") : "none"];
      }));
  add("Minimum certified wash, by the prior cargo's class",
      Object.keys(m.minimum_wash).sort().map((c) => [c, m.minimum_wash[c]]));
  add("Then raise one rung for", Object.keys(m.grade_uplift)
    .filter((g) => m.grade_uplift[g] > 0).map((g) => [g, "+1 rung, capped at the top of the ladder"]));
  add("Wash ladder, weakest to strongest", [["order", m.wash_ladder.join("  <  ")]]);
  const p = document.createElement("p");
  p.className = "mxn";
  p.textContent = m.certificate_governs;
  box.appendChild(p);
}

async function load() {
  const d = await (await fetch("/api/fields")).json();
  FIELDS = d.fields;
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set" : "no API_KEY — Check will not call anything";
  draw(null);
  drawDecided(null, null, null, null, null);
  matrixTable(await (await fetch("/api/matrix")).json());
  show();
}

async function show() {
  const r = await (await fetch("/api/doc?id=" + encodeURIComponent($("doc").value))).json();
  $("text").textContent = r.text || "";
}

async function go() {
  $("go").disabled = true; $("go").textContent = "Checking…"; $("note").hidden = true;
  try {
    const r = await (await fetch("/api/extract", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    draw(r.fields);
    const val = (n) => (r.fields && r.fields[n] ? r.fields[n].value : null);
    drawDecided(val("verdict"), r.reason, r.required_wash, val("load_status"), r.needs_hold);
  } finally { $("go").disabled = false; $("go").textContent = "Check"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => {
  draw(null); drawDecided(null, null, null, null, null); show();
});
load();
