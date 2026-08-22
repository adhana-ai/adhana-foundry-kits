// The minimal UI's whole client. No framework, no build step, no dependency.
const $ = (id) => document.getElementById(id);

const BASIS_TEXT = {
  explicit_date: "a stated date — never moved",
  calendar_days_from_order: "calendar days from the Order",
  calendar_days_from_event: "calendar days from an event",
  business_days_from_order: "business days from the Order",
  business_days_from_event: "business days from an event",
};

function cell(text, cls) {
  const td = document.createElement("td");
  td.textContent = text;
  if (cls) td.className = cls;
  return td;
}

function countedFrom(r) {
  if (r.basis === "explicit_date") return "—";
  const unit = String(r.basis || "").indexOf("business") === 0 ? "business days" : "days";
  const n = r.period_days == null ? "?" : r.period_days;
  if (r.trigger_event) {
    return n + " " + unit + " after " + r.trigger_event
      + (r.trigger_event_date ? " (" + r.trigger_event_date + ")" : " — NOT RECORDED");
  }
  return n + " " + unit + " after the Order";
}

function row(r) {
  const tr = document.createElement("tr");
  tr.appendChild(cell(r.paragraph == null ? "?" : "¶" + r.paragraph, "n"));
  const what = cell(r.item || "not stated", r.item ? "v" : "v empty");
  if (r.spans && r.spans.item) what.title = "read from " + r.spans.item.label;
  tr.appendChild(what);
  tr.appendChild(cell(BASIS_TEXT[r.basis] || r.basis || "not stated",
    r.basis ? "s" : "s none"));
  tr.appendChild(cell(countedFrom(r), "s"));
  tr.appendChild(cell(r.party_calculated_date || "—",
    r.party_calculated_date ? "s party" : "s none"));

  const model = r.due_date || (r.due_date === null ? "cannot be dated" : "—");
  const recomputed = r.computed_date || "cannot be dated";
  const agree = (r.due_date || null) === (r.computed_date || null);
  tr.appendChild(cell(model, agree ? "d" : "d bad"));
  const rc = cell(recomputed, r.computed_date ? "d ok" : "d undated");
  tr.appendChild(rc);

  const w = cell(r.working || "—", "w");
  if (!agree) w.textContent = "⚠ the reply's own values do not produce its date — " + (r.working || "");
  tr.appendChild(w);
  return tr;
}

function draw(res) {
  const body = $("rows");
  body.textContent = "";
  if (!res || !res.deadlines) {
    const tr = document.createElement("tr");
    const td = cell("Nothing has been asked yet — pick an order and press Compute.", "v empty");
    td.colSpan = 8;
    tr.appendChild(td);
    body.appendChild(tr);
    $("c-matter").textContent = "—";
    $("c-date").textContent = "—";
    $("k-rows").textContent = "— deadlines";
    $("k-undated").textContent = "— cannot be dated";
    $("k-span").textContent = "— with a span";
    return;
  }
  res.deadlines.forEach((r) => body.appendChild(row(r)));
  $("c-matter").textContent = (res.matter_number && res.matter_number.value) || "not stated";
  $("c-date").textContent = (res.order_date && res.order_date.value) || "not stated";
  $("k-rows").textContent = res.deadlines.length + " deadlines";
  // ⚠︎ TWO DIFFERENT BLANKS, AND SAYING SO IS THE POINT. "cannot be dated" is an ANSWER — the
  // Order leaves the triggering event undated — and it is not the same as a row the model failed
  // to date. The pill counts the first, off the pure-code recomputation, never off a null reply.
  const undated = res.deadlines.filter((r) => !r.computed_date).length;
  $("k-undated").textContent = undated + " cannot be dated from this Order";
  let spannable = 0, spanned = 0;
  res.deadlines.forEach((r) => {
    ["item", "trigger_event"].forEach((k) => {
      if (r[k]) { spannable += 1; if (r.spans && r.spans[k]) spanned += 1; }
    });
  });
  $("k-span").textContent = spanned + " of " + spannable + " located in their own paragraph";
}

function rulebookPanel(m) {
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
  add("Business day", [["weekdays", "Monday to Friday, excluding every court holiday below"],
                       ["not business days", m.weekend.join(", ")]]);
  add("When counting starts", [[m.trigger_day_counts ? "day one" : "day zero",
                                m.trigger_day_note]]);
  add("How each basis is counted",
      m.bases.map((b) => [b.code, b.counts + " — rolls forward: " + (b.rolls ? "YES" : "NO")]));
  add("Rolling", [["forward", m.roll.note]]);
  add("When no date can be computed", [["undatable", m.undatable_note]]);
  add("Court holidays — every one invented",
      m.holidays.map((h) => [h.date, h.name]));
  const p = document.createElement("p");
  p.className = "mxn";
  p.textContent = m.illustrative;
  box.appendChild(p);
  const q = document.createElement("p");
  q.className = "mxn";
  q.textContent = m.holiday_note;
  box.appendChild(q);
}

async function load() {
  const d = await (await fetch("/api/fields")).json();
  d.documents.forEach((id) => {
    const o = document.createElement("option"); o.value = o.textContent = id; $("doc").appendChild(o);
  });
  $("key").textContent = d.has_key ? "API_KEY set" : "no API_KEY — Compute will not call anything";
  draw(null);
  rulebookPanel(await (await fetch("/api/rulebook")).json());
  show();
}

async function show() {
  const r = await (await fetch("/api/doc?id=" + encodeURIComponent($("doc").value))).json();
  $("text").textContent = r.text || "";
}

async function go() {
  $("go").disabled = true; $("go").textContent = "Computing…"; $("note").hidden = true;
  try {
    const r = await (await fetch("/api/calendar", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ id: $("doc").value }) })).json();
    if (r.note) { $("note").textContent = r.note; $("note").hidden = false; }
    draw(r.deadlines ? r : null);
  } finally { $("go").disabled = false; $("go").textContent = "Compute"; }
}

$("go").addEventListener("click", go);
$("doc").addEventListener("change", () => { draw(null); show(); });
load();
