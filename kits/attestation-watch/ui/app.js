// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let FIELDS = { register: [], attester: [] };

const STATUS_TEXT = {
  satisfied: "SATISFIED — filed in time, covering the right window, and nothing on the register contradicts it",
  missing: "MISSING — no return on file and the due date has passed",
  stale: "STALE — a return was filed, and not in time or not about this cycle",
  contradicted: "CONTRADICTED — the register disagrees with itself about this person",
  not_required: "NOT REQUIRED — nothing is owed here",
  not_determinable: "NOT DETERMINABLE — the register cannot answer for this person",
};

function regRow(f, cell) {
  const tr = document.createElement("tr");
  const v = cell && cell.value;
  const vtxt = v === undefined ? "not checked yet" : (v === null || v === "" ? "not stated" : v);
  const empty = v === undefined || v === null || v === "";
  tr.innerHTML = '<td class="n"></td><td class="v' + (empty ? " empty" : "") + '"></td>';
  tr.children[0].textContent = f.name;
  tr.children[1].textContent = vtxt;
  return tr;
}

function personRow(a) {
  const tr = document.createElement("tr");
  const g = (n) => (a.fields && a.fields[n] ? a.fields[n].value : null);
  const st = a.computed_status;

  const c0 = document.createElement("td");
  c0.className = "pref";
  c0.textContent = a.person_ref || "—";
  const role = document.createElement("div");
  role.className = "why";
  role.textContent = g("role") || "role not stated";
  c0.appendChild(role);

  const c1 = document.createElement("td");
  const s = document.createElement("div");
  s.className = st ? "vd vd-" + st : "vd";
  s.textContent = st ? (STATUS_TEXT[st] || st) : "—";
  c1.appendChild(s);
  const why = document.createElement("p");
  why.className = "why";
  why.textContent = a.computed_reason || "";
  c1.appendChild(why);

  // ⚠︎ TWO DIFFERENT BLANKS, AND SAYING SO IS THE POINT. A person with no due date is not a
  // person whose due date the page failed to print: it is a person for whom NO due date can be
  // derived — an unrecorded cycle, or a role the rulebook gives no cycle length for. Printing an
  // empty cell there reads as a rendering bug and hides the only interesting thing about the row.
  const c2 = document.createElement("td");
  c2.className = "dt derived";
  c2.textContent = a.computed_due_on
    || (st ? "none can be derived" : "—");

  const c3 = document.createElement("td");
  c3.className = "dt";
  c3.textContent = g("return_filed_on") || (st ? "nothing on file" : "—");

  tr.appendChild(c0); tr.appendChild(c1); tr.appendChild(c2); tr.appendChild(c3);
  return tr;
}

function draw(res) {
  const regBody = $("regrows");
  regBody.textContent = "";
  FIELDS.register.forEach((f) =>
    regBody.appendChild(regRow(f, res ? res.register[f.name] : undefined)));

  const body = $("rows");
  body.textContent = "";
  if (!res) {
    $("k-people").textContent = "— people";
    $("k-work").textContent = "— need action";
    $("k-span").textContent = "— with a span";
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4; td.className = "v empty";
    td.textContent = "not checked yet";
    tr.appendChild(td); body.appendChild(tr);
    return;
  }
  res.attesters.forEach((a) => body.appendChild(personRow(a)));
  $("k-people").textContent = res.attesters.length + " people";
  $("k-work").textContent = res.worklist.length + " need action";
  let spannable = 0, spanned = 0;
  const count = (cells) => Object.keys(cells || {}).forEach((n) => {
    const c = cells[n];
    if (c && c.spannable !== false && c.value) { spannable++; if (c.span) spanned++; }
  });
  count(res.register);
  res.attesters.forEach((a) => count(a.fields));
  $("k-span").textContent = spanned + " of " + spannable + " with a span";
}

function drawRouting(res) {
  if (!res) {
    $("c-work").textContent = "—";
    $("c-nd").textContent = "—";
    $("c-flag").textContent = "—";
    $("c-flag").className = "";
    return;
  }
  $("c-work").textContent = res.worklist.length
    ? res.worklist.join(", ") + " — " + res.worklist.length + " person(s) to act on"
    : "nobody on this register needs action today";
  $("c-nd").textContent = res.not_determinable.length
    ? res.not_determinable.join(", ") + " — the register cannot answer for them"
    : "the register answers for everybody on it";
  const f = res.needs_owner_review;
  $("c-flag").textContent = (f === null || f === undefined)
    ? "not computed — a status the rule needs was missing from the reply"
    : (f ? "YES — this register carries a contradiction or a record nobody can read. A reminder "
         + "will not resolve it; somebody has to open the file."
         : "no — anything outstanding here is a chase, not an investigation");
  $("c-flag").className = f ? "hold" : "";
}

function rulebookTable(rb) {
  const box = $("rulebook");
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
  add("Roles that carry a requirement",
      rb.roles_requiring_attestation.map((r) => [r, rb.cycle_days[r] + " day cycle"]));
  add("Roles that carry none",
      rb.roles_not_requiring_attestation.map((r) => [r, "nothing is owed, whatever the register lists"]));
  add("Grace window", [["grace_days", rb.grace_days + " days after the due date, still in time"]]);
  add("Coverage test", [["rule", rb.coverage_rule]]);
  add("Which return governs", [["rule", rb.supersede_rule]]);
  add("The two ways a register contradicts itself",
      rb.contradiction_rules.map((r, i) => ["rule " + (i + 1), r]));
  add("The six statuses", [["order", rb.statuses.join("  ·  ")]]);
  add("What puts somebody on the worklist", [["worklist", rb.worklist.join(", ")]]);
  add("When a register needs an owner", [["rule", rb.owner_review_rule]]);
  const p = document.createElement("p");
  p.className = "mxn";
  p.textContent = rb._README.join(" ");
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
  drawRouting(null);
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
    draw(r.result || null);
    drawRouting(r.result || null);
  } finally { $("go").disabled = false; $("go").textContent = "Check"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => { draw(null); drawRouting(null); show(); });
load();
