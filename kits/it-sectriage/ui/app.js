/* The panel. Every window card renders the alerts and the gold answer (so the page is honest
   about what "correct" means here before anyone spends a call); "Ask the model" is the only thing
   that costs anything, and it is one call per press, on your key.

   ⚠︎ THE GOLD GROUPING IS SHOWN, NOT HIDDEN, BEFORE A CALL IS MADE. This is a demo of the MECHANIC,
   not a blind quiz -- the point is to see the trap (a shared IP, a calm phishing report) and watch
   whether the model falls into it, the same way ops-triage shows the truth label on every card. */
var STATE = {windows: [], trapByWin: {}};

function esc(s){ return String(s == null ? "" : s).replace(/[&<>"]/g, function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]; }); }

function fmtGroups(groups){
  if (!groups || !groups.length) return "<i>no case (all false positive)</i>";
  return groups.map(function(g){ return "[" + g.map(esc).join(", ") + "]"; }).join("  ");
}

function alertHtml(a, goldDisp){
  var ind = Object.keys(a.indicators).map(function(k){
    return '<span class="kv">' + esc(k) + "=" + esc(a.indicators[k]) + "</span>"; }).join(" ");
  return '<div class="alert">' +
    '<div class="ahead"><span class="aid">' + esc(a.alert_id) + "</span>" +
    '<span class="atype">' + esc(a.alert_type) + "</span>" +
    '<span class="aent">' + esc(a.entity) + "</span>" +
    '<span class="ats">' + esc(a.ts.slice(11, 19)) + "</span>" +
    (goldDisp ? '<span class="chip ' + (goldDisp === "true_positive" ? "tp" : "fp") + '">' +
      esc(goldDisp) + "</span>" : "") + "</div>" +
    '<p class="adesc">' + esc(a.description) + "</p>" +
    '<p class="aind">' + ind + "</p></div>";
}

function cardHtml(w){
  var g = STATE.trapByWin[w.id] || {};
  var trapChip = g.trap ? '<span class="chip trap">' + esc(g.trap.replace("_", " ")) + "</span>"
                        : "";
  return '<article class="win" data-win="' + esc(w.id) + '">' +
    '<div class="whead"><span class="wid">' + esc(w.id) + "</span>" +
    '<span class="chip">' + w.alerts.length + " alerts</span>" +
    '<span class="chip">analyst: ' + esc(w.on_call_analyst) + "</span>" +
    trapChip +
    '<button class="ask" data-ask="' + esc(w.id) + '">Ask the model (1 call)</button></div>' +
    (w.alerts.map(function(a){
      return alertHtml(a, (g.gold_alert_dispositions || {})[a.alert_id]); }).join("")) +
    '<p class="gold"><b>gold case groups:</b> ' + fmtGroups(g.gold_case_groups) + "</p>" +
    '<div class="result" data-result></div></article>';
}

function render(){
  document.getElementById("windows").innerHTML = STATE.windows.map(cardHtml).join("");
  document.querySelectorAll("[data-ask]").forEach(function(b){
    b.onclick = function(){ ask(b.getAttribute("data-ask"), b); };
  });
}

function renderResult(wid, j){
  var card = document.querySelector('[data-win="' + wid + '"]');
  var out = card.querySelector("[data-result]");
  if (j.note){
    out.innerHTML = '<p class="err">' + esc(j.note) + "</p>";
    return;
  }
  var disp = j.alert_dispositions || {};
  var rows = Object.keys(disp).map(function(aid){
    return '<span class="kv">' + esc(aid) + "=" + esc(disp[aid]) + "</span>"; }).join(" ");
  var recs = (j.recommendations || []).map(function(r){
    return '<div class="rec"><b>[' + (r.case || []).map(esc).join(", ") + "]</b> " +
      esc(r.action || "") + '<div class="cites">cites: ' +
      (r.citations || []).map(esc).join(", ") + "</div></div>";
  }).join("");
  out.innerHTML = '<p class="modelout"><b>model dispositions:</b> ' + rows + "</p>" +
    '<p class="modelout"><b>model case groups:</b> ' + fmtGroups(j.case_groups) + "</p>" + recs +
    '<p class="tok">' + (j.input_tokens || 0) + " in / " + (j.output_tokens || 0) + " out</p>";
}

function ask(wid, btn){
  var card = document.querySelector('[data-win="' + wid + '"]');
  var out = card.querySelector("[data-result]");
  btn.disabled = true; out.innerHTML = "calling the model — one call…";
  fetch("/api/triage", {method: "POST", headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({id: wid})})
    .then(function(r){ return r.json(); })
    .then(function(j){ btn.disabled = false; renderResult(wid, j); })
    .catch(function(e){ btn.disabled = false; out.innerHTML = '<span class="err">' + esc(e) +
      "</span>"; });
}

fetch("/api/state").then(function(r){ return r.json(); }).then(function(s){
  document.getElementById("cost").textContent =
    (s.has_key
      ? "A key IS configured, so this page can spend. "
      : "No key is configured, so nothing on this page can call anything. ") +
    "Every 'Ask the model' click is ONE call on your key; nothing else here calls anything.";
  var g = s.gate || {};
  document.getElementById("gate").textContent =
    g.windows + " case windows, " + g.alerts + " alerts total — " +
    g.false_negative_trap_windows + " carry the calmly-worded true-positive phishing trap, " +
    g.false_correlation_trap_windows + " carry the coincidental-indicator merge trap.";
  document.getElementById("tiles").innerHTML =
    '<div class="tile"><div class="k">windows</div><div class="n">' + g.windows + "</div></div>" +
    '<div class="tile"><div class="k">alerts</div><div class="n">' + g.alerts + "</div></div>" +
    '<div class="tile warn"><div class="k">false-negative trap</div><div class="n">' +
    g.false_negative_trap_windows + "</div></div>" +
    '<div class="tile warn"><div class="k">false-correlation trap</div><div class="n">' +
    g.false_correlation_trap_windows + "</div></div>";

  return Promise.all(s.windows.map(function(id){
    return fetch("/api/window?id=" + encodeURIComponent(id)).then(function(r){ return r.json(); });
  }));
}).then(function(rows){
  STATE.windows = rows.map(function(r){ return r.window; });
  rows.forEach(function(r){ STATE.trapByWin[r.window.id] = r; });
  render();
});
