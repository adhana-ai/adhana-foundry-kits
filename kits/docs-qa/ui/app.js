/* docs-qa UI. Plain JS, no framework, no build step -- open the file and read it.
 *
 * It renders what the server returns and computes nothing of its own. Every number on screen came
 * from a module the eval harness also drives, so the UI and results/ cannot disagree about what
 * the pipeline does. If you change the pipeline, this follows for free. */

const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const n = (x, d = 0) => x == null ? "—" : Number(x).toLocaleString(undefined,
  { minimumFractionDigits: d, maximumFractionDigits: d });

const get = async p => {
  const r = await fetch(p);
  if (!r.ok) throw new Error(`${p} -> ${r.status}`);
  return r.json();
};

let STATUS = null, RESULTS = null;

/* ── status strip ─────────────────────────────────────────────────────── */

function renderStatus(s) {
  const t = (k, v, cls = "") => `<span class="stat ${cls}"><span class="k">${k}</span><span class="v">${v}</span></span>`;
  const fmts = Object.entries(s.corpus.by_format).sort()
    .map(([f, c]) => `${f} ${c}`).join(" · ");
  $("#status").innerHTML =
    t("corpus", `${s.corpus.documents} docs`) +
    t("chunks", n(s.corpus.chunks)) +
    t("formats", fmts) +
    t("retriever", s.retriever, "on") +
    t("top-k", s.top_k) +
    (s.has_key
      ? t("model", esc(s.model || "set"), "on")
      : t("model", "not set — offline", "off"));
}

/* ── ask ──────────────────────────────────────────────────────────────── */

function renderAsk(d) {
  $("#askout").hidden = false;

  /* The failure band. Only ever shown for a question from the labelled set, because only then do
     we know which document SHOULD have won. A free-typed question has no expectation, and
     inventing one would be the kit lying about its own confidence. */
  const band = $("#failband"), e = d.expected;
  if (e && e.cause) {
    band.hidden = false;
    /* TWO DIFFERENT FAILURES WEAR THE ONE CAUSE NAME, and saying the wrong one is worse than
       saying nothing. `bad_ranking` fires whenever the answer is absent from the retrieved
       passages -- which happens both when the right document never came back AND when it came
       back but the chunks that won were its table of contents. This band used to assert the
       first unconditionally; on L26 it read "retrieval did not rank it into the top 5" directly
       above three EXPECTED passages from that very document. The evidence was on screen
       contradicting the caption. `doc_retrieved` already distinguishes them, so use it. */
    const where = e.doc_retrieved
      ? `<code>${esc(e.doc)}</code> WAS ranked into the top ${d.hits.length}, but the chunks that ` +
        `won carry none of the answer — so the split is what failed here, not the search`
      : `<code>${esc(e.doc)}</code> was not ranked into the top ${d.hits.length} at all`;
    band.innerHTML =
      `<strong>${esc(e.cause)}</strong> — the answer to this question is in ${where}. ` +
      `The model below is answering without the evidence, which is why it should decline. ` +
      `<em>This failure is real, reproducible and costs nothing to see: it is pure code.</em>`;
  } else band.hidden = true;

  /* The answer, or an honest empty slot. */
  const a = d.answer;
  $("#answer").innerHTML = a
    ? `<div class="answer">${esc(a.text)}</div>
       <div class="meta">
         <span class="stat"><span class="k">model</span><span class="v">${esc(a.model)}</span></span>
         <span class="stat"><span class="k">in</span><span class="v">${n(a.input_tokens)}</span></span>
         <span class="stat"><span class="k">out</span><span class="v">${n(a.output_tokens)}</span></span>
         <span class="stat"><span class="k">took</span><span class="v">${n(a.latency_ms)} ms</span></span>
       </div>`
    : `<div class="empty">${esc(d.note || "no answer")}</div>`;

  $("#rethint").textContent =
    `${d.hits.length} passages, ${d.retriever} retriever, ${d.retrieval_ms} ms — no key, no network.`;

  $("#hits").innerHTML = d.hits.map((h, i) => {
    const want = e && h.doc === e.doc;
    return `<div class="hit ${want ? "want" : ""}">
      <div class="hit-head">
        <span class="n">[${i + 1}]</span>
        <span class="doc">${esc(h.doc)}</span>
        <span class="fmt">${esc(h.format)}</span>
        ${want ? '<span class="fmt">expected</span>' : ""}
        <span class="score">${h.score}</span>
      </div>
      <div class="hit-body">${esc(h.text)}</div>
    </div>`;
  }).join("");

  $("#parts").innerHTML = d.prompt.parts.map(p =>
    `<div class="part"><span class="nm">${esc(p.name)}</span>
       <span class="src">${esc(p.chunk || "")}</span>
       <span class="ch">${n(p.chars)} chars</span></div>`).join("") +
    `<div class="part"><span class="nm">TOTAL</span><span class="src"></span>
       <span class="ch">${n(d.prompt.chars)} chars</span></div>`;

  $("#rawprompt").textContent = d.prompt.system + "\n\n———\n\n" + d.prompt.user;
}

async function ask(question, id) {
  const btn = $("#askbtn");
  btn.disabled = true; btn.textContent = "…";
  try {
    const q = `/api/ask?q=${encodeURIComponent(question)}` + (id ? `&id=${id}` : "");
    renderAsk(await get(q));
  } catch (err) {
    $("#askout").hidden = false;
    $("#answer").innerHTML = `<div class="empty">${esc(err.message)}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = "Ask";
  }
}

/* Starter questions come from the labelled set and from the RECORDED results, so the one marked
   as a known failure is marked because it failed a real run -- not because someone decided it
   should be the demo. */
function renderChips(labels, runs) {
  const rows = (runs[0] || {}).rows || [];
  const cause = Object.fromEntries(rows.map(r => [r.id, r.cause]));
  const byId = Object.fromEntries(labels.map(l => [l.id, l]));
  const good = rows.filter(r => !r.cause).slice(0, 3).map(r => r.id);
  const bad = (rows.find(r => r.cause === "bad_ranking") || {}).id;
  const pick = [...good, bad].filter(Boolean);

  $("#chips").innerHTML = pick.map(id => {
    const l = byId[id]; if (!l) return "";
    const fail = !!cause[id];
    return `<button class="chip" data-id="${id}" data-q="${esc(l.question)}">
      ${esc(l.question)}${fail ? '<span class="tag">known failure</span>' : ""}</button>`;
  }).join("");

  $$("#chips .chip").forEach(c => c.addEventListener("click", () => {
    $("#q").value = c.dataset.q;
    ask(c.dataset.q, c.dataset.id);
  }));
}

/* ── recorded results ─────────────────────────────────────────────────── */

function renderResults(runs) {
  if (!runs.length) { $("#results").innerHTML = '<div class="empty">no runs in results/</div>'; return; }

  $("#results").innerHTML = runs.map(run => {
    const s = run.summary, live = run.model;
    const tile = (k, v, cls = "") => `<div class="tile ${cls}"><span class="k">${k}</span><span class="v">${v}</span></div>`;

    const tiles =
      tile("rows", s.rows) +
      tile("doc in top-k", (100 * s.doc_hit_rate).toFixed(1) + "%") +
      tile("answer in prompt", (100 * s.answer_in_context_rate).toFixed(1) + "%") +
      tile("retrieval p50", s.retrieval_latency_p50_ms + " ms") +
      tile("retrieval p95", s.retrieval_latency_p95_ms + " ms") +
      (s.accuracy != null
        ? tile("accuracy", (100 * s.accuracy).toFixed(1) + "%", "good") +
          tile("model p50", n(s.model_latency_p50_ms) + " ms") +
          tile("tokens in/out", n(s.input_tokens_total) + " / " + n(s.output_tokens_total))
        : tile("accuracy", "—", "dash") + tile("model p50", "—", "dash") + tile("tokens", "—", "dash"));

    const fails = (run.rows || []).filter(r => r.cause);
    const failTable = fails.length ? `
      <h2 class="block">Failures — ${fails.length} of ${s.rows}, by cause</h2>
      <div class="scroll"><table>
        <thead><tr><th class="m">id</th><th>question</th><th class="m">cause</th><th class="m">answering doc</th><th class="m">in top-k?</th></tr></thead>
        <tbody>${fails.map(r => `<tr class="fail clickable" data-ask="${esc(r.question)}" data-id="${esc(r.id)}">
          <td class="m">${esc(r.id)}</td><td>${esc(r.question)}</td>
          <td class="m">${esc(r.cause)}</td><td class="m">${esc(r.doc)}</td>
          <td class="m">${r.doc_hit ? "yes — wrong chunk" : "no"}</td></tr>`).join("")}</tbody>
      </table></div>` : "";

    const cnv = (run.could_not_verify || []).map(x => `<li>${esc(x)}</li>`).join("");

    return `<section class="block">
      <div class="runhead">
        <h3>${esc(run.run_id)}</h3>
        <span class="who">${live ? esc(run.provider + " · " + run.model) : "retrieval only — no model, no key"}
          · ${esc(run.retriever)} · k=${run.top_k} · ${run.dataset.rows} labelled rows
          · corpus ${run.corpus.documents} docs / ${n(run.corpus.chunks)} chunks</span>
      </div>
      <div class="tiles">${tiles}</div>
      ${live ? "" : '<p class="hint">The dashed tiles are the model half. They are drawn empty rather than omitted — absent and zero are different states.</p>'}
      ${failTable}
      <div class="note warn"><strong>What could not be verified in this run</strong><ul>${cnv}</ul></div>
      <div class="note"><strong>No provenance stamp yet.</strong> The harness deliberately does not
        write <code>as_of</code> or <code>verified_by</code> — a harness that stamps its own
        provenance is one that can stamp a run nobody made. Those fields are the capture step's to
        write.</div>
    </section>`;
  }).join("");
}

/* ── corpus ───────────────────────────────────────────────────────────── */

function renderCorpus(c) {
  const tile = (k, v, cls = "") => `<div class="tile ${cls}"><span class="k">${k}</span><span class="v">${v}</span></div>`;
  const b = c.boilerplate || {}, cc = c.chunk_chars;
  const fmts = Object.entries(c.by_format).sort();

  $("#corpus").innerHTML = `
    <section class="block">
      <h2>What is in it</h2>
      <div class="tiles">${tile("documents", c.documents.length)}${fmts.map(([f, k]) => tile(f, k)).join("")}</div>
      <p class="hint">Five formats on purpose. A corpus that is all one format cannot show
        extraction failing, and extraction is the failure a reader most needs to see.</p>
    </section>

    <section class="block">
      <h2>Extraction <span class="seam">seam 2 · src/extract.py</span></h2>
      <div class="tiles">
        ${tile("failures", c.extraction_failures.length, c.extraction_failures.length ? "bad" : "good")}
        ${tile("of documents", c.documents.length)}
      </div>
      ${c.extraction_failures.length
        ? `<div class="scroll"><table><thead><tr><th class="m">doc</th><th>error</th></tr></thead><tbody>
            ${c.extraction_failures.map(f => `<tr class="fail"><td class="m">${esc(f.doc)}</td><td>${esc(f.error)}</td></tr>`).join("")}
           </tbody></table></div>`
        : '<p class="hint">Zero today. The block stays visible at zero so your own corpus can show a number that is not zero.</p>'}
    </section>

    <section class="block">
      <h2>Boilerplate removed <span class="seam">cross-document, not a selector</span></h2>
      <div class="tiles">${tile("lines dropped", n(b.lines_dropped))}${tile("distinct", n(b.distinct_lines))}</div>
      <p class="hint">Site furniture found by line frequency across the corpus and within each
        format group — the same nav arrives spelled differently depending on the format it was
        rendered into, so no single spelling reaches half the corpus.</p>
      ${(b.examples || []).length ? `<div class="parts">${(b.examples || []).slice(0, 6).map(x =>
        `<div class="part"><span class="nm">dropped</span><span class="src">${esc(x)}</span></div>`).join("")}</div>` : ""}
    </section>

    <section class="block">
      <h2>Chunking <span class="seam">seam 3 · src/chunk.py</span></h2>
      <div class="tiles">
        ${tile("chunks", n(cc.count))}${tile("p50", n(cc.p50))}${tile("p90", n(cc.p90))}
        ${tile("max", n(cc.max), cc.ceiling && cc.max <= cc.ceiling ? "good" : "bad")}
        ${tile("ceiling", n(cc.ceiling))}
      </div>
      <p class="hint">The distribution, not the average — the defect this pipeline actually had was
        a 15,623-character chunk, and an average would have hidden it. Max is shown against the
        ceiling so the invariant is visible rather than asserted.</p>
    </section>

    <section class="block">
      <h2>Every document <span class="seam">click a row to see where the chunker cut</span></h2>
      <div class="scroll"><table>
        <thead><tr><th class="m">document</th><th class="m">format</th><th class="m">chunks</th><th class="m">chars</th></tr></thead>
        <tbody>${c.documents.map(d => `<tr class="clickable" data-doc="${esc(d.doc)}">
          <td class="m">${esc(d.doc)}</td><td class="m">${esc(d.format)}</td>
          <td class="m">${d.chunks}</td><td class="m">${n(d.chars)}</td></tr>`).join("")}</tbody>
      </table></div>
      <div id="docview"></div>
    </section>

    <section class="block">
      <h2>Point it at your own documents</h2>
      <div class="note">
        <ol style="margin:0;padding-left:20px">
          <li>Drop your files into <code>data/corpus/</code></li>
          <li>Run <code>python -m src.index</code></li>
          <li>Ask again — that is the whole change</li>
        </ol>
      </div>
      <div class="note warn"><strong>What breaks when you do.</strong> A format with no entry in
        <code>EXTRACTORS</code> is skipped and recorded, not silently dropped. And the labelled set
        stops applying the moment the corpus changes — every accuracy number here describes
        <em>this</em> corpus, so re-label before believing a score on yours.</div>
    </section>`;

  $$("#corpus tr.clickable").forEach(tr => tr.addEventListener("click", async () => {
    const d = await get("/api/doc?id=" + encodeURIComponent(tr.dataset.doc));
    $("#docview").innerHTML = `<div class="block"><h2>${esc(d.doc)} — ${d.chunks.length} chunks</h2>
      <div class="hits">${d.chunks.map((c, i) => `<div class="hit">
        <div class="hit-head"><span class="n">[${i + 1}]</span><span class="doc">${esc(c.id)}</span>
          <span class="score">${n(c.chars)} chars</span></div>
        <div class="hit-body">${esc(c.text)}</div></div>`).join("")}</div></div>`;
    $("#docview").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }));
}

/* ── tabs + boot ──────────────────────────────────────────────────────── */

function showTab(name) {
  $$(".tab").forEach(x => {
    const on = x.dataset.tab === name;
    x.classList.toggle("sel", on);
    x.setAttribute("aria-selected", String(on));
  });
  $$(".panel").forEach(p => { p.hidden = true; });
  $("#tab-" + name).hidden = false;
}
$$(".tab").forEach(t => t.addEventListener("click", () => showTab(t.dataset.tab)));

/* A recorded failure is only evidence if you can go and see it happen. Clicking a row loads that
   exact question into Ask, so the table's claim and the live run are one click apart -- and the
   URL carries it, so the case can be linked to rather than described. */
document.addEventListener("click", ev => {
  const tr = ev.target.closest("tr[data-ask]");
  if (!tr) return;
  const q = tr.dataset.ask, id = tr.dataset.id;
  history.replaceState(null, "", `/?q=${encodeURIComponent(q)}&id=${encodeURIComponent(id)}`);
  $("#q").value = q;
  showTab("ask");
  window.scrollTo({ top: 0, behavior: "smooth" });
  ask(q, id);
});

$("#askform").addEventListener("submit", ev => {
  ev.preventDefault();
  const q = $("#q").value.trim();
  if (q) ask(q, null);          // free-typed: no label, so no expectation is claimed
});

(async function boot() {
  try {
    STATUS = await get("/api/status");
    renderStatus(STATUS);
    const [labels, results, corpus] = await Promise.all(
      [get("/api/labels"), get("/api/results"), get("/api/corpus")]);
    RESULTS = results.runs;
    renderChips(labels.labels, RESULTS);
    renderResults(RESULTS);
    renderCorpus(corpus);

    // #results / #corpus open a tab directly; ?q=…&id=… asks on load, so a specific case --
    // especially a failing one -- is a link rather than a description of where to click.
    const tab = location.hash.slice(1);
    if (["ask", "results", "corpus"].includes(tab)) showTab(tab);
    const p = new URLSearchParams(location.search);
    if (p.get("q")) { $("#q").value = p.get("q"); showTab("ask"); ask(p.get("q"), p.get("id")); }
  } catch (e) {
    $("#status").innerHTML = `<span class="stat off"><span class="v">${esc(e.message)}</span></span>`;
  }
})();
