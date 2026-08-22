// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let FIELDS = [];

const SEP_TEXT = {
  distinct: "DISTINCT",
  bundled: "BUNDLED",
  not_determined: "NOT DETERMINED",
};
const PAT_TEXT = {
  over_time: "OVER TIME",
  point_in_time: "POINT IN TIME",
  not_determined: "NOT DETERMINED",
};
const STATED = {
  required_first: "must come first",
  separately_available: "can be taken alone",
  silent: "says nothing about separability",
};
const TIMING = {
  period: "states a period",
  event: "states a single event",
  silent: "states no timing",
};
const CHARGE = {
  separate_fee: "a fee of its own",
  no_separate_charge: "no separate charge",
  not_stated: "fee not separately stated",
};

function cell(row, name) {
  const c = row.cells[name];
  return c ? c.value : null;
}

function draw(rows) {
  const body = $("rows");
  body.textContent = "";
  if (!rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td class="v empty" colspan="6"></td>';
    tr.children[0].textContent = "not built yet";
    body.appendChild(tr);
    $("k-lines").textContent = "— lines";
    $("k-open").textContent = "— not determined";
    $("k-span").textContent = "— with a span";
    return;
  }
  rows.forEach((r) => {
    const tr = document.createElement("tr");
    const sep = cell(r, "separation");
    const pat = cell(r, "pattern");
    // "says nothing" is the finding, not a gap — it is written out in words rather than left as an
    // empty cell, because a blank here reads as a bug and the whole point is that the CONTRACT is
    // silent, not the model.
    //
    // ⚠︎ THE CHARGE IS NOT REPEATED HERE. It has its own column two cells to the left, and the
    // first shot of this page printed it twice — caught by opening the screenshot, not by any
    // check that passes over rendered output. This column is the two facts the fee column cannot
    // show: what the pack says about separability, and what it says about timing.
    const stated = [STATED[cell(r, "dependency")] || "—",
                    TIMING[cell(r, "timing")] || "—"].join(" · ");
    tr.innerHTML =
      '<td class="n"></td><td class="v"></td><td class="n"></td><td class="st"></td>' +
      '<td></td><td></td>';
    tr.children[0].textContent = cell(r, "item_code") || "—";
    tr.children[1].textContent = cell(r, "item_label") || "not stated";
    tr.children[2].textContent = CHARGE[cell(r, "charge")] || "—";
    tr.children[3].textContent = stated;
    tr.children[4].textContent = sep ? (SEP_TEXT[sep] || sep) : "—";
    tr.children[4].className = sep ? ("vd vd-" + sep) : "";
    tr.children[5].textContent = pat ? (PAT_TEXT[pat] || pat) : "—";
    tr.children[5].className = pat ? ("vd vd-" + pat) : "";
    body.appendChild(tr);
  });
  const open = rows.reduce((n, r) =>
    n + (cell(r, "separation") === "not_determined" ? 1 : 0)
      + (cell(r, "pattern") === "not_determined" ? 1 : 0), 0);
  const spannable = rows.length;
  const spanned = rows.filter((r) => r.cells.item_label && r.cells.item_label.span).length;
  $("k-lines").textContent = rows.length + " lines";
  $("k-open").textContent = open + " not determined";
  $("k-span").textContent = spanned + " of " + spannable + " with a span";
}

function drawDecided(contractId, rows, flag) {
  $("c-id").textContent = contractId || "—";
  $("c-count").textContent = rows ? String(rows.length) : "—";
  const open = rows ? rows.reduce((n, r) =>
    n + (cell(r, "separation") === "not_determined" ? 1 : 0)
      + (cell(r, "pattern") === "not_determined" ? 1 : 0), 0) : null;
  $("c-open").textContent = open === null ? "—"
    : (open + " of " + (rows.length * 2) + " calls — the pack does not answer these, and saying so "
       + "is the point of the worksheet");
  $("c-flag").textContent = (flag === null || flag === undefined)
    ? "not computed — the reply carried no line the rule could read"
    : (flag ? "YES — at least one PRICED line whose separation and delivery pattern the pack "
            + "settles neither of. Money attached, and the contract answers neither question."
            : "no — every priced line's calls are settled by the pack");
  $("c-flag").className = flag ? "hold" : "";
}

function rulebookPanel(r) {
  const box = $("rulebook");
  box.textContent = "";
  const add = (h, rows) => {
    const d = document.createElement("div");
    d.className = "mxb";
    const t = document.createElement("div"); t.className = "mxh"; t.textContent = h;
    d.appendChild(t);
    rows.forEach(([a, b]) => {
      const row = document.createElement("div"); row.className = "mxr";
      const k = document.createElement("span"); k.className = "mxk"; k.textContent = a;
      const v = document.createElement("span"); v.textContent = b;
      row.appendChild(k); row.appendChild(v); d.appendChild(row);
    });
    box.appendChild(d);
  };
  add("What counts as a line on the worksheet",
      r.what_is_an_obligation_here.map((s, i) => [String(i + 1), s]));
  ["charge", "dependency", "timing"].forEach((k) => {
    add("Stated fact — " + k,
        Object.keys(r.stated_facts[k]).map((v) => [v, r.stated_facts[k][v]]));
  });
  add("Separation — in order, stop at the first that fires",
      r.separation_rule.map((s) => [s.slice(0, 2), s.slice(3)]));
  add("Delivery pattern", r.pattern_rule.map((s) => [s.slice(0, 2), s.slice(3)]));
  const why = document.createElement("p");
  why.className = "mxn";
  why.textContent = r.why_not_determined_is_first_class;
  box.appendChild(why);
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
    : "no API_KEY — Build worksheet will not call anything";
  draw(null);
  drawDecided(null, null, null);
  rulebookPanel(await (await fetch("/api/rulebook")).json());
  show();
}

async function show() {
  const r = await (await fetch("/api/doc?id=" + encodeURIComponent($("doc").value))).json();
  $("text").textContent = r.text || "";
}

async function go() {
  $("go").disabled = true; $("go").textContent = "Building…"; $("note").hidden = true;
  try {
    const r = await (await fetch("/api/extract", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    draw(r.obligations);
    const cid = r.contract && r.contract.contract_id ? r.contract.contract_id.value : null;
    drawDecided(cid, r.obligations, r.needs_drafting_review);
  } finally { $("go").disabled = false; $("go").textContent = "Build worksheet"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => {
  draw(null); drawDecided(null, null, null); show();
});
load();
