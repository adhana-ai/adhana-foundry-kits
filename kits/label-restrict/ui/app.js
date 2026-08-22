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
  // Five fields are legitimately null on some cases — three intervals a label extract does not
  // state, the days since an application that was never made, and a days-to-harvest the proposal
  // omits. The label says "not stated" rather than "not found", because what the panel knows is
  // that the reply carried nothing, not why.
  $("k-missing").textContent = (FIELDS.length - filled.length) + " not stated";
  const spannable = vals.filter((c) => c.spannable !== false && c.value);
  $("k-span").textContent = vals.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
}

const VERDICT_TEXT = {
  within_label: "WITHIN LABEL — every applicable restriction is satisfied as it stands",
  wait_required: "WAIT REQUIRED — every hard restriction is met and an interval has not elapsed",
  outside_label: "OUTSIDE LABEL — a restriction is breached that no waiting will cure",
  insufficient_information: "INSUFFICIENT INFORMATION — a restriction this turns on is not stated",
};

const STATE_TEXT = {
  pass: "passed",
  breach: "BREACHED — this is the one that decided it",
  not_applicable: "not applicable — skipped, and it passes",
  not_stated: "NOT STATED — the walk stopped here; it could not be performed",
};

function drawDecided(verdict, restriction, reason, status, flag) {
  const v = $("c-verdict");
  v.textContent = verdict == null ? "—" : (VERDICT_TEXT[verdict] || verdict);
  v.className = verdict == null ? "" : ("vd vd-" + verdict);
  // ⚠︎ TWO DIFFERENT BLANKS, AND SAYING SO IS THE POINT. Before a check has run there is no
  // restriction because nothing has been asked. After one, `none` is a real answer meaning every
  // check passed — and printing it as a dash would make a clean case look like a missing one.
  $("c-restriction").textContent = restriction == null
    ? "—"
    : (restriction === "none" ? "none — no check decided against this proposal" : restriction);
  $("c-reason").textContent = reason || "—";
  $("c-status").textContent = status == null ? "—" : status;
  $("c-flag").textContent = (flag === null || flag === undefined)
    ? "not computed — one of the two values the rule needs was missing"
    // ⚠︎ "NOT INSIDE THE LABEL AS IT STANDS", NEVER "OUTSIDE THE LABEL". The flag fires on any
    // verdict other than `within_label` — which includes `wait_required` and
    // `insufficient_information`, and neither of those is `outside_label`. Naming the wrong one of
    // the four here would print a verdict the reply never gave, on the payoff row of the page.
    : (flag ? "YES — not inside the label as it stands, and the product is already on the crop. "
            + "Record it and get a qualified adviser to it."
            : "no — nothing here needs a hold");
  $("c-flag").className = flag ? "hold" : "";
}

function drawWalk(checks) {
  const body = $("walk");
  body.textContent = "";
  if (!checks || !checks.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td class="n">—</td><td class="dim"></td>';
    tr.children[1].textContent = "Nothing has been checked yet.";
    body.appendChild(tr);
    return;
  }
  checks.forEach((c) => {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td class="n"></td><td class="w"></td>';
    tr.children[0].textContent = c.id;
    tr.children[1].textContent = STATE_TEXT[c.state] || c.state;
    tr.children[1].className = "w st-" + c.state;
    body.appendChild(tr);
  });
  // The checks BELOW the one that stopped the walk were never run, and the panel says so rather
  // than leaving a reader to infer that eight rows minus four means four passes.
  const shown = checks.length;
  const tr = document.createElement("tr");
  tr.innerHTML = '<td class="n">—</td><td class="dim"></td>';
  tr.children[1].textContent = shown < 8
    ? ("the remaining " + (8 - shown) + " check(s) were never run: the walk stops at the first "
       + "check that fires")
    : "all eight checks ran";
  body.appendChild(tr);
}

function checkTable(m) {
  const box = $("checks");
  box.textContent = "";
  const warn = document.createElement("p");
  warn.className = "mxn";
  warn.textContent = (m._README || []).join(" ");
  box.appendChild(warn);
  m.checks.slice().sort((a, b) => a.order - b.order).forEach((c) => {
    const d = document.createElement("div");
    d.className = "mxb";
    const t = document.createElement("div");
    t.className = "mxh";
    t.textContent = c.order + ". " + c.id + "  —  " + c.kind + " → " + c.breach_verdict;
    d.appendChild(t);
    [["compare", c.label_field + "  " + c.op + "  " + c.proposal_field],
     ["test", c.test],
     ["why", c.why]].forEach(([a, b]) => {
      const r = document.createElement("div"); r.className = "mxr";
      const k = document.createElement("span"); k.className = "mxk"; k.textContent = a;
      const val = document.createElement("span"); val.textContent = b;
      r.appendChild(k); r.appendChild(val); d.appendChild(r);
    });
    box.appendChild(d);
  });
  [["Precedence", m.precedence], ["Skipped is not unknown", m.skipped_is_not_unknown],
   ["At the limit", m.at_the_limit]].forEach(([h, body]) => {
    const p = document.createElement("p");
    p.className = "mxn";
    p.textContent = h + " — " + body;
    box.appendChild(p);
  });
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
  drawWalk(null);
  checkTable(await (await fetch("/api/checks")).json());
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
    drawDecided(val("verdict"), val("deciding_restriction"), r.reason,
                val("application_status"), r.needs_hold);
    drawWalk(r.checks);
  } finally { $("go").disabled = false; $("go").textContent = "Check"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => {
  draw(null); drawDecided(null, null, null, null, null); drawWalk(null); show();
});
load();
