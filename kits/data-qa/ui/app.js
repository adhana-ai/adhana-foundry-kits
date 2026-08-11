/* The minimal UI. No framework and no build step — a forker should be able to read this file
   top to bottom and change it, which is not true of a bundle.

   ⚑ IT ALWAYS SHOWS THE SQL. The rows alone cannot tell a right answer from a lucky one, so the
   generated statement is never hidden behind a toggle. That is the kit's whole teaching point. */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s === null || s === undefined ? "" : s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

let HAS_KEY = false;

async function boot() {
  const s = await (await fetch("/api/status")).json();
  HAS_KEY = s.has_key;
  const tables = Object.entries(s.tables)
    .map(([t, n]) => `<b>${esc(t)}</b> ${n.toLocaleString()} rows`).join(" &middot; ");
  $("status").innerHTML =
    `${tables} &middot; schema card <b>${s.schema_card.length}</b> chars sent on every question` +
    (s.has_key
      ? ` &middot; model <b>${esc(s.model || "not set")}</b>`
      : ` &middot; <span class="warn">no API key — the recorded run below still renders; ` +
        `asking a new question needs your own key</span>`);
  if (!s.has_key) $("connect").classList.remove("hidden");

  const ex = await (await fetch("/api/examples")).json();
  $("examples").innerHTML = ex.examples.map(e =>
    `<button data-q="${esc(e.question)}" class="${e.answerable ? "" : "un"}"
      title="${esc(e.tests)}">${esc(e.id)}</button>`).join("");
  $("examples").querySelectorAll("button").forEach(b =>
    b.onclick = () => { $("q").value = b.dataset.q; ask(); });

  renderRuns(await (await fetch("/api/results")).json());
}

function renderRuns(d) {
  if (!d.runs || !d.runs.length) {
    $("runs").innerHTML = `<div class="note">${esc(d.note || "no run recorded yet")}</div>`;
    return;
  }
  $("runs").innerHTML = d.runs.map(r => {
    const s = r.summary || {};
    const acc = s.accuracy === undefined ? "&mdash;" : (100 * s.accuracy).toFixed(1) + "%";
    const causes = Object.entries(s.causes || {})
      .map(([c, n]) => `${esc(c)} ${n}`).join(" &middot; ") || "no failures recorded";
    // ONE CARD PER RUN. A re-score is shown as a correction to this run's score, with the number
    // it replaced still on screen — never as a second run, which is what a kit claiming `run once`
    // must not appear to have done.
    const rs = r.rescored
      ? `<div class="causes">re-scored from
         <b>${(100 * (r.rescored.accuracy_before || 0)).toFixed(1)}%</b> &mdash;
         ${esc(r.rescored.note || "ruler corrected")}.
         <b>No model was called;</b> the recorded statements were re-judged.
         ${(r.rescored.rows_changed || []).length} row(s) moved.</div>`
      : "";
    return `<div class="run">
      <div class="big">${acc} <span class="note">execution match &middot; ${s.rows || 0} questions
        &middot; ${esc(r.model || "model not recorded")} &middot; one run</span></div>
      <div class="causes">${causes}</div>
      ${rs}
      ${(r.could_not_verify || []).map(c => `<div class="cnv">could not verify: ${esc(c)}</div>`)
        .join("")}
    </div>`;
  }).join("");
}

function renderRows(d) {
  if (!d.columns || !d.columns.length) return `<div class="note">no columns returned</div>`;
  const head = d.columns.map(c => `<th>${esc(c)}</th>`).join("");
  const body = d.rows.map(r => `<tr>${r.map(v =>
    `<td>${v === null ? '<span class="note">NULL</span>' : esc(v)}</td>`).join("")}</tr>`).join("");
  return `<div class="tablewrap"><table><tr>${head}</tr>${body}</table></div>`;
}

async function ask() {
  const q = $("q").value.trim();
  if (!q) return;
  $("out").classList.remove("hidden");
  $("sql").className = "";
  $("sql").textContent = "asking…";
  $("guard").textContent = "";
  $("result").innerHTML = "";
  $("meta").textContent = "";
  $("go").disabled = true;

  let d;
  try {
    d = await (await fetch("/api/ask", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ question: q })
    })).json();
  } finally {
    $("go").disabled = false;
  }

  if (!d.ok) {
    $("sql").textContent = "—";
    $("guard").className = "note bad";
    $("guard").textContent = d.error || "something went wrong";
    return;
  }

  $("sql").textContent = d.sql || "—";

  if (d.stage === "cannot_answer") {
    $("sql").className = "";
    $("guard").className = "note gold";
    $("guard").textContent = d.message;
    $("result").innerHTML = `<div class="note">Nothing was run. This is a correct outcome.</div>`;
  } else if (d.stage === "refused") {
    $("sql").className = "refused";
    $("guard").className = "note bad";
    $("guard").textContent = "BLOCKED — " + d.guard_reason;
    $("result").innerHTML = `<div class="note bad">${esc(d.message)}</div>`;
  } else if (d.stage === "exec_error") {
    $("sql").className = "refused";
    $("guard").className = "note bad";
    $("guard").textContent = d.error;
    $("result").innerHTML = `<div class="note">The statement ran and SQLite rejected it.</div>`;
  } else {
    $("sql").className = "okq";
    $("guard").className = "note";
    $("guard").textContent = "Guard: single read-only SELECT. Executed.";
    $("result").innerHTML = renderRows(d);
    if (d.truncated) {
      $("result").innerHTML +=
        `<div class="note gold">Truncated at the row cap — this is not the whole result.</div>`;
    }
  }
  const bits = [];
  if (d.model_ms !== undefined) bits.push(`model ${d.model_ms.toFixed(0)} ms`);
  if (d.exec_ms !== undefined) bits.push(`query ${d.exec_ms.toFixed(1)} ms`);
  if (d.row_count !== undefined) bits.push(`${d.row_count} row(s)`);
  if (d.input_tokens) bits.push(`tokens in/out ${d.input_tokens}/${d.output_tokens || 0}`);
  bits.push(`prompt ${d.prompt_chars} chars`);
  $("meta").textContent = bits.join(" · ");
}

$("go").onclick = ask;
$("q").addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });

$("save").onclick = async () => {
  const body = {
    PROVIDER: $("c-provider").value.trim(), BASE_URL: $("c-base").value.trim(),
    MODEL: $("c-model").value.trim(), API_KEY: $("c-key").value.trim()
  };
  const d = await (await fetch("/api/connect", {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body)
  })).json();
  $("saved").className = d.ok ? "note" : "note bad";
  $("saved").textContent = d.ok
    ? `saved ${d.saved.join(", ")} to ${d.path} — reload to use it`
    : (d.error || "could not save");
};

boot();
