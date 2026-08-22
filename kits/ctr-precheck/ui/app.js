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
  // ⚠︎ TWO DIFFERENT REASONS A CELL HAS NO SPAN, AND SAYING WHICH IS THE POINT. An enum is copied
  // off the page and then mapped onto a fixed vocabulary, so it has a source and no exact string
  // to point at. A DERIVED field — the qualifying total, the missing elements, the mis-coded ids,
  // the defect list — has no source at all: it is the answer to a question the page never states.
  // Printing one label for both would quietly claim the arithmetic was read off the pack.
  tr.children[2].textContent = span ? ("§ " + span.section)
    : (cell && cell.spannable === false
        ? (f.type === "enum" ? "n/a — fixed value" : "n/a — derived, not copied")
        : "—");
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
  // linked_record_id, missing_identification_elements, miscoded_transaction_ids and
  // log_qualifying_total are all legitimately null on some packs — there is often no second
  // record, nothing missing, nothing mis-coded, and on a pack with an uncaptured amount there is
  // no computable total at all. The label says "not stated" rather than "not found", because what
  // the panel knows is that the reply carried nothing, not why.
  $("k-missing").textContent = (FIELDS.length - filled.length) + " not stated";
  const spannable = vals.filter((c) => c.spannable !== false && c.value);
  $("k-span").textContent = vals.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
}

function fmt(n) {
  if (n === null || n === undefined || n === "") return null;
  const v = Number(n);
  return Number.isFinite(v) ? v.toLocaleString("en-GB") + " CU" : String(n);
}

function drawDecided(defects, reasons, drafted, logTotal, flag, answered, stated) {
  const res = $("c-result");
  // ⚠︎ THREE STATES, AND COLLAPSING ANY TWO OF THEM IS THE DEFECT THIS PANEL EXISTS TO AVOID.
  // "nothing asked yet" is not "clean", and "clean" is not "the reply carried no answer". On a QC
  // surface those three look identical if you only render the defect list, and the middle one —
  // a filing with nothing wrong with it — is the commonest row in a real queue.
  if (!answered) { res.textContent = "—"; res.className = ""; }
  else if (defects === null) {
    res.textContent = "NO ANSWER — the reply carried no defect list, so nothing was decided";
    res.className = "vd vd-unknown";
  } else if (!defects.length) {
    res.textContent = "CLEAN — the rulebook finds nothing wrong with this draft";
    res.className = "vd vd-clean";
  } else {
    res.textContent = defects.length + (defects.length === 1 ? " DEFECT" : " DEFECTS")
      + " — this draft needs work before anyone submits it";
    res.className = "vd vd-defect";
  }

  const box = $("c-defects");
  box.textContent = "";
  if (!answered || defects === null) { box.textContent = "—"; }
  else if (!defects.length) { box.textContent = "none"; }
  else {
    const ul = document.createElement("ul");
    ul.className = "dfl";
    defects.forEach((code) => {
      const li = document.createElement("li");
      const k = document.createElement("span"); k.className = "dfc"; k.textContent = code;
      const w = document.createElement("span"); w.className = "dfw";
      w.textContent = (reasons && reasons[code]) || "";
      li.appendChild(k); li.appendChild(w); ul.appendChild(li);
    });
    box.appendChild(ul);
  }

  const st = $("c-stated");
  if (!answered || stated == null) {
    st.textContent = answered ? "the reply carried no defect list at all" : "—";
    st.className = "";
  } else {
    const a = (stated || "none").split(/[,;]/).map((s) => s.trim().toLowerCase())
      .filter(Boolean).sort().join(", ");
    const b = (defects && defects.length ? defects.slice().sort().join(", ") : "none");
    st.textContent = a + (a === b ? "  (agrees with the rulebook run over its own numbers)"
      : "  — DISAGREES with the rulebook run over its own numbers, which gives: " + b);
    st.className = a === b ? "" : "hold";
  }

  $("c-drafted").textContent = fmt(drafted) || "—";
  // A null qualifying total is not zero and must never print as one — it is the whole
  // `insufficient_information` case, and a "0 CU" here would read as "nothing was reportable".
  $("c-log").textContent = (logTotal === null || logTotal === undefined)
    ? (answered ? "— (an amount in the log was never captured, so no total can be computed)" : "—")
    : fmt(logTotal);
  $("c-flag").textContent = (flag === null || flag === undefined)
    ? (answered ? "not computed — the reply carried no defect list, and an unknown is not a pass"
                : "—")
    : (flag ? "YES — the totals, or whether a filing is due at all, cannot stand as drafted. Back "
            + "to the preparer before anyone submits."
            : "no — nothing here changes what would be filed");
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
      const row = document.createElement("div"); row.className = "mxr";
      const k = document.createElement("span"); k.className = "mxk"; k.textContent = a;
      const val = document.createElement("span"); val.textContent = b;
      row.appendChild(k); row.appendChild(val); d.appendChild(row);
    });
    box.appendChild(d);
  };
  add("Threshold", [["more than", r.threshold.toLocaleString("en-GB") + " " + r.unit
    + " for one patron, one direction, one gaming day"]]);
  add("Aggregation window", [["gaming day", r.gaming_day_start + " on its own date to "
    + r.gaming_day_start + " the following calendar date"],
    ["directions", "cash in and cash out aggregate separately and are never netted"]]);
  add("Transaction codes", Object.keys(r.transaction_codes).sort().map((c) => [c,
    r.transaction_codes[c].direction + " · "
    + (r.transaction_codes[c].reportable ? "reportable" : "NOT reportable — never in a currency total")
    + " · " + r.transaction_codes[c].what]));
  add("Required identification elements",
      r.identification_elements.map((e) => [e, "must be on the draft"]));
  add("Staleness", [["horizon", "identification captured more than "
    + r.identification_stale_days + " days before the gaming day is stale"]]);
  add("Same-person link keys",
      r.identity_link_keys.map((k) => [k.replace(/_/g, " "), "both must match"]));
  add("Defect codes", Object.keys(r.defect_codes).map((c) => [c, r.defect_codes[c]]));
  add("Stopping order", r.stopping_order.map((s) => {
    const i = s.indexOf(" ");
    return [s.slice(0, i), s.slice(i + 1)];
  }));
  const p = document.createElement("p");
  p.className = "mxn";
  p.textContent = r._README.join(" ");
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
  drawDecided(null, null, null, null, null, false, null);
  rulebookTable(await (await fetch("/api/rulebook")).json());
  show();
}

async function show() {
  const r = await (await fetch("/api/doc?id=" + encodeURIComponent($("doc").value))).json();
  $("text").textContent = r.text || "";
}

async function go() {
  $("go").disabled = true; $("go").textContent = "Checking…"; $("note").hidden = true;
  try {
    const r = await (await fetch("/api/check", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    draw(r.fields);
    if (!r.fields) { drawDecided(null, null, null, null, null, false, null); return; }
    const val = (n) => (r.fields[n] ? r.fields[n].value : null);
    const stated = val("defects_found");
    drawDecided(stated == null ? null : r.recomputed_defects, r.recomputed_reasons,
                val("draft_reported_total"), val("log_qualifying_total"),
                r.needs_recompute, true, stated);
  } finally { $("go").disabled = false; $("go").textContent = "Check"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => {
  draw(null); drawDecided(null, null, null, null, null, false, null); show();
});
load();
