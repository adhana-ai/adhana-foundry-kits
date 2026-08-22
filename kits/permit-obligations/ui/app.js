// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let FIELDS = [], OBFIELDS = [];

const STATUS_TEXT = {
  overdue: "OVERDUE",
  due_in_window: "DUE SOON",
  not_yet_due: "not yet due",
  not_binding: "does not bind",
  not_determinable: "CANNOT DETERMINE",
};

function topRows(fields) {
  const body = $("toprows");
  body.textContent = "";
  FIELDS.forEach((f) => {
    const cell = fields ? fields[f.name] : undefined;
    const v = cell && cell.value;
    const tr = document.createElement("tr");
    tr.innerHTML = '<td class="n"></td><td class="v"></td><td class="s"></td>';
    tr.children[0].textContent = f.name;
    tr.children[1].textContent = v === undefined ? "not read yet"
      : (v === null || v === "" ? "not stated" : v);
    if (v === undefined || v === null || v === "") tr.children[1].className = "v empty";
    tr.children[2].textContent = cell && cell.span ? ("§ " + cell.span.section) : "—";
    if (!(cell && cell.span)) tr.children[2].className = "s none";
    body.appendChild(tr);
  });
}

function drawRows(obligations) {
  const body = $("rows");
  body.textContent = "";
  if (!obligations) {
    $("k-rows").textContent = "— conditions";
    $("k-span").textContent = "— with a span";
    $("k-work").textContent = "— need action";
    $("k-nd").textContent = "— cannot determine";
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="5" class="v empty"></td>';
    tr.children[0].textContent = "Nothing has been read yet. Pick a register and press Read.";
    body.appendChild(tr);
    return;
  }
  obligations.forEach((o) => {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td class="n"></td><td class="n"></td><td></td><td class="n"></td><td class="w"></td>';
    tr.children[0].textContent = o.condition_id || "—";
    tr.children[1].textContent = (o.cells && o.cells.obligation_type
      && o.cells.obligation_type.value) || "—";
    const st = document.createElement("span");
    st.className = "st st-" + (o.status || "none");
    st.textContent = STATUS_TEXT[o.status] || "—";
    tr.children[2].appendChild(st);
    // ⚠︎ TWO DIFFERENT BLANKS, AND SAYING SO IS THE POINT. A row with no due date is not a row
    // whose date is unknown: the rule STOPPED before any date applied — a superseded condition, a
    // trigger that has not fired, or a register that does not carry what the rule needs. Printing
    // an empty cell there reads as a bug in the kit rather than as a fact about the register.
    tr.children[3].textContent = o.due_date || "— no date applies";
    tr.children[4].textContent = o.reason || o.undetermined_because || "—";
    body.appendChild(tr);
  });

  const need = obligations.filter((o) => o.status === "overdue" || o.status === "due_in_window");
  const nd = obligations.filter((o) => o.status === "not_determinable");
  const cells = obligations.flatMap((o) => Object.values(o.cells || {}));
  const spannable = cells.filter((c) => c.spannable !== false && c.value);
  $("k-rows").textContent = obligations.length + " conditions";
  $("k-span").textContent = cells.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
  $("k-work").textContent = need.length + " need action";
  $("k-nd").textContent = nd.length + " cannot determine";
}

function drawEscalate(flag) {
  const c = $("c-esc");
  c.className = flag ? "hold" : "";
  c.textContent = (flag === null || flag === undefined)
    ? "not computed — one of the values the rule needs was missing"
    : (flag
      ? "YES — something on this register is already overdue and the site's own flag calls it "
        + "on track or closed. Nobody is looking at it."
      : "no — nothing overdue here is going unflagged by the site itself");
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
  add("Obligation types, their cycles and their OWN action windows",
      Object.keys(r.obligation_types).sort().map((k) => {
        const s = r.obligation_types[k];
        const how = s.basis === "cycle" ? ("every " + s.interval_days + " days from the last recorded date")
          : s.basis === "reporting_period" ? ("a " + s.period + ", due " + s.deadline_month_day
            + " of the following year")
          : "nothing is due until the trigger fires";
        return [k, how + "  ·  window " + s.window_days + " days"];
      }));
  add("Condition states — read before any date",
      Object.keys(r.condition_states).map((k) => [k, r.condition_states[k]]));
  add("Trigger states", Object.keys(r.trigger_states).map((k) => [k, r.trigger_states[k]]));
  add("Statuses", [["order", r.statuses.join("  ·  ")]]);
  [r.window_note, r.condition_states_note, r.period_credited_note, r.never].forEach((n) => {
    const p = document.createElement("p");
    p.className = "mxn";
    p.textContent = n;
    box.appendChild(p);
  });
}

async function load() {
  const d = await (await fetch("/api/fields")).json();
  FIELDS = d.fields; OBFIELDS = d.obligation_fields;
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set"
    : "no API_KEY — Read register will not call anything";
  topRows(null);
  drawRows(null);
  drawEscalate(undefined);
  rulebookTable(await (await fetch("/api/rulebook")).json());
  show();
}

async function show() {
  const r = await (await fetch("/api/doc?id=" + encodeURIComponent($("doc").value))).json();
  $("text").textContent = r.text || "";
}

async function go() {
  $("go").disabled = true; $("go").textContent = "Reading…"; $("note").hidden = true;
  try {
    const r = await (await fetch("/api/read", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    topRows(r.fields);
    drawRows(r.obligations);
    drawEscalate(r.escalate);
  } finally { $("go").disabled = false; $("go").textContent = "Read register"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => {
  topRows(null); drawRows(null); drawEscalate(undefined); show();
});
load();
