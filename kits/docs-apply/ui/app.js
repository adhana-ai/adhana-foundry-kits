/* Picker -> document + request; a method -> the diff, split into intended and collateral.
 * ⚑ COLLATERAL IS RENDERED EVEN WHEN IT IS EMPTY, as an explicit "none". A section that only
 * appears when something is wrong is a section nobody learns to read. */
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
let REQS = [];

function diffHtml(rows) {
  if (!rows.length) return '<div class="miss">none</div>';
  return rows.map(([kind, text]) =>
    `<div class="${kind}">${kind === 'added' ? '+' : '-'} ${esc(text)}</div>`).join('');
}

function render(r) {
  if (r.skipped) { $('#note').textContent = r.skipped; return; }
  if (r.error) {
    $('#verdict').innerHTML = '<span class="pill p-bad">unparseable</span>';
    $('#out').innerHTML = `<p class="miss">${esc(r.error)} (finish_reason: ${esc(r.finish_reason)})</p>`;
    return;
  }
  if (r.declined) {
    $('#verdict').innerHTML = '<span class="pill p-warn">declined &mdash; nothing written</span>';
    $('#out').innerHTML =
      '<h3>Intended change, had it applied</h3><div class="d">' + diffHtml(r.intended) + '</div>' +
      '<h3>Collateral</h3><div class="d"><div class="miss">none &mdash; the file was not touched</div></div>';
    return;
  }
  const clean = r.collateral.length === 0;
  $('#verdict').innerHTML = clean
    ? '<span class="pill p-ok">written &middot; no collateral</span>'
    : `<span class="pill p-bad">written &middot; ${r.collateral.length} unasked line(s) moved</span>`;
  $('#out').innerHTML =
    '<h3>Intended change</h3><div class="d">' + diffHtml(r.intended) + '</div>' +
    '<h3>Collateral &mdash; what moved that nobody asked to move</h3><div class="d">' +
    diffHtml(r.collateral) + '</div>';
}

async function load(id) {
  const d = await (await fetch('/api/doc?id=' + id)).json();
  $('#before').textContent = d.before;
  $('#request').textContent = d.request;
  $('#verdict').innerHTML = '';
  $('#out').innerHTML = '<p class="miss">Run a method.</p>';
  $('#note').textContent = '';
}

(async function init() {
  const { docs } = await (await fetch('/api/docs')).json();
  REQS = docs;
  $('#pick').innerHTML = docs.map(d => `<option value="${d.doc_id}">${d.doc_id}</option>`).join('');
  $('#pick').onchange = (e) => load(e.target.value);
  $('#floor').onclick = async () => {
    $('#note').textContent = 'running the free floor…';
    render(await (await fetch('/api/floor?id=' + $('#pick').value)).json());
    $('#note').textContent = 'free floor — pure code, $0.00';
  };
  $('#model').onclick = async () => {
    $('#note').textContent = 'calling the model, 1 call…';
    render(await (await fetch('/api/model?id=' + $('#pick').value)).json());
    $('#note').textContent = 'model — 1 call spent';
  };
  await load(docs[0].doc_id);
})();
