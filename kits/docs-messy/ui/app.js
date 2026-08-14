/* The side-by-side. Fetches both conditions, then overlays whichever method you ran.
 *
 * ⚑ THE TABLE COMPARES AGAINST THE PAGE, NOT AGAINST THE CLEAN ANSWER. Scoring the scanned column
 * against what the CLEAN extraction returned would hide the case that matters most: both columns
 * confidently wrong in the same way. Gold is the document, for both. */
const $ = (s) => document.querySelector(s);
let GOLD = {}, FLOOR = null, MODEL = null, FIELDS = [];

function normish(v) {
  if (v === null || v === undefined) return null;
  const s = String(v).trim().replace(/\s+/g, ' ').replace(/[.,:;|~^]+$/, '');
  if (!s || ['not stated', 'none', 'null', 'n/a', 'unknown', '-'].includes(s.toLowerCase()))
    return null;
  return s;
}

function cell(gold, got) {
  const g = normish(gold), p = normish(got);
  if (g === null && p === null) return ['<span class="miss">not stated</span>', 'm-ok', 'declined'];
  if (g === null && p !== null) return [esc(p), 'm-inv', 'invented'];
  if (p === null) return ['<span class="miss">&mdash;</span>', 'm-wrong', 'missed'];
  const ok = String(p).toLowerCase() === String(g).toLowerCase();
  return [esc(p), ok ? 'm-ok' : 'm-wrong', ok ? 'ok' : 'wrong'];
}

const esc = (s) => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

function render() {
  const tb = $('#out tbody');
  tb.innerHTML = '';
  const src = MODEL || FLOOR;
  for (const f of FIELDS) {
    const g = GOLD[f];
    const c = src ? cell(g, src.clean[f]) : ['<span class="miss">run a method</span>', '', ''];
    const m = src ? cell(g, src.messy[f]) : ['', '', ''];
    tb.insertAdjacentHTML('beforeend',
      `<tr><td>${f}</td>
           <td class="v">${g === null || g === undefined
              ? '<span class="miss">not stated</span>' : esc(g)}</td>
           <td class="v">${c[0]}</td>
           <td class="v">${m[0]}</td>
           <td>${m[1] ? `<span class="mark ${m[1]}">${m[2]}</span>` : ''}</td></tr>`);
  }
}

async function load(id) {
  FLOOR = MODEL = null;
  const d = await (await fetch('/api/doc?id=' + id)).json();
  $('#clean').textContent = d.clean;
  $('#messy').textContent = d.messy;
  GOLD = d.gold || {};
  FIELDS = Object.keys(GOLD);
  $('#note').textContent = '';
  render();
}

(async function init() {
  const { docs } = await (await fetch('/api/docs')).json();
  $('#pick').innerHTML = docs.map(d =>
    `<option value="${d.doc_id}">${d.doc_id} &mdash; ${d.kind.toLowerCase()}</option>`).join('');
  $('#pick').onchange = (e) => load(e.target.value);
  $('#floor').onclick = async () => {
    $('#note').textContent = 'running the free floor…';
    FLOOR = await (await fetch('/api/floor?id=' + $('#pick').value)).json();
    MODEL = null;
    $('#note').textContent = 'free floor — pure code, $0.00';
    render();
  };
  $('#model').onclick = async () => {
    $('#note').textContent = 'calling the model, 2 calls…';
    const r = await (await fetch('/api/model?id=' + $('#pick').value)).json();
    if (r.skipped) { $('#note').textContent = r.skipped; return; }
    MODEL = r;
    $('#note').textContent = 'model — 2 calls spent';
    render();
  };
  await load(docs[0].doc_id);
})();
