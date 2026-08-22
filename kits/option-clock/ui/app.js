// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);
let FIELDS = [];
let WINDOW_DAYS = null;

function row(f, cell) {
  const tr = document.createElement("tr");
  const v = cell && cell.value;
  const span = cell && cell.span;
  const vtxt = v === undefined ? "not read yet" : (v === null || v === "" ? "not stated" : v);
  const empty = v === undefined || v === null || v === "";
  tr.innerHTML =
    '<td class="n"></td><td class="v' + (empty ? " empty" : "") + '"></td>' +
    '<td class="s' + (span ? "" : " none") + '"></td>';
  tr.children[0].textContent = f.name;
  tr.children[1].textContent = vtxt;
  tr.children[2].textContent = span ? ("§ " + span.section)
    : (cell && cell.spannable === false ? "n/a — counted, not stated" : "—");
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
  // option_granted_date, trigger_date and expiry_date are legitimately null on some registers —
  // two entries may disagree about a grant date, a triggering event may not have happened, and an
  // option whose clock has not started has no expiry. The label says "not stated" rather than
  // "not found", because what the panel knows is that the reply carried nothing, not why.
  $("k-missing").textContent = (FIELDS.length - filled.length) + " not stated";
  const spannable = vals.filter((c) => c.spannable !== false && c.value);
  $("k-span").textContent = vals.filter((c) => c.span).length + " of " + spannable.length
    + " with a span";
}

const STATUS_TEXT = {
  live: "LIVE — the counted expiry is beyond the window. Nothing is due on this today",
  lapsing: "LAPSING — the counted expiry falls inside the window. This one needs somebody now",
  lapsed: "LAPSED — the counted expiry is on or before the date this register is current as at",
  not_determinable: "NOT DETERMINABLE — the register does not carry what the count needs. "
    + "This is not a clearance",
};

function drawCounted(r) {
  const s = r ? r.counted_status : null;
  const v = $("c-status");
  v.textContent = s == null ? "—" : (STATUS_TEXT[s] || s);
  v.className = s == null ? "" : ("vd vd-" + s);

  $("c-start").textContent = (r && r.counted_clock_start_date)
    || (r ? "— (the clock never started, so there is nothing to count from)" : "—");
  // ⚠︎ TWO DIFFERENT BLANKS, AND SAYING SO IS THE POINT. Before a read there is no expiry because
  // nothing has been asked; after one, a blank means the count could not be STARTED — a triggering
  // event that has not happened, or two entries disagreeing about the grant date. Printing the
  // second sentence in the first state was found by opening the page, not by any check that passes
  // over rendered output.
  $("c-expiry").textContent = (r && r.counted_expiry_date)
    || (r ? "— (no expiry could be counted: " + (r.undetermined_because || "unknown") + ")" : "—");
  const d = r ? r.counted_days_to_expiry : null;
  $("c-days").textContent = (d === null || d === undefined) ? "—"
    : (d <= 0 ? Math.abs(d) + " day(s) ago"
              : "in " + d + " day(s)" + (WINDOW_DAYS && d <= WINDOW_DAYS
                  ? " — inside the " + WINDOW_DAYS + "-day window" : ""));
  $("c-reason").textContent = (r && r.reason) || "—";

  const carried = r && r.fields && r.fields.register_status
    ? r.fields.register_status.value : null;
  const cc = $("c-carried");
  if (carried == null) { cc.textContent = "—"; cc.className = ""; }
  else if (s && ((carried === "live") !== (s === "live"))) {
    cc.textContent = carried + " — which disagrees with the count";
    cc.className = "mismatch";
  } else { cc.textContent = carried; cc.className = ""; }

  const flag = r ? r.escalate_now : null;
  $("c-flag").textContent = (flag === null || flag === undefined)
    ? (r ? "not computed — one of the two values the rule needs was missing"
         : "—")
    : (flag ? "YES — not live, and the register still carries it as live. Nobody is looking at "
            + "this one. Open it first."
            : "no — nothing here needs escalating today");
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
      const line = document.createElement("div"); line.className = "mxr";
      const k = document.createElement("span"); k.className = "mxk"; k.textContent = a;
      const val = document.createElement("span"); val.textContent = b;
      line.appendChild(k); line.appendChild(val); d.appendChild(line);
    });
    box.appendChild(d);
  };
  add("What starts the clock", Object.keys(r.clock_start).map((k) => [k, r.clock_start[k]]));
  add("What perfects an extension",
      Object.keys(r.perfection).map((k) => [k + "-controlled", r.perfection[k]]));
  add("How extensions stack", [["order", r.stacking_note]]);
  add("How months are added", [["calendar", r.month_arithmetic_note]]);
  add("A contradicted date", [["rule", r.contradiction_rule]]);
  add("The window", [[r.window_days + " days", r.window_note]]);
  add("The four statuses", Object.keys(r.statuses).map((k) => [k, r.statuses[k]]));
  add("What is not evidence", [
    ["register status", r.register_status_is_not_evidence],
    ["clerk note", r.clerk_note_is_not_evidence],
  ]);
  const p = document.createElement("p");
  p.className = "mxn";
  p.textContent = r._README.join(" ");
  box.appendChild(p);
}

async function load() {
  const d = await (await fetch("/api/fields")).json();
  FIELDS = d.fields;
  WINDOW_DAYS = d.window_days;
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set"
    : "no API_KEY — Read the clock will not call anything";
  draw(null);
  drawCounted(null);
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
    const r = await (await fetch("/api/extract", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    draw(r.fields);
    drawCounted(r.fields ? r : null);
  } finally { $("go").disabled = false; $("go").textContent = "Read the clock"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => {
  draw(null); drawCounted(null); show();
});
load();
