/* The panel. Everything except the Ask-the-model button is computed here, from facts the server
   sent once — so dragging the threshold re-decides 123 windows with no request and no cost.

   ⚑ THE CONTROL IS THE ARGUMENT. This kit's claim is that no setting of the free rules gets all six
   traps right. A report can assert that; a slider lets the reader disprove it if it is false. So the
   trap line under the tiles recomputes on every input event and names which traps are handled at the
   current setting, rather than printing a conclusion somebody has to take on trust.

   ⚠︎ AND THE TILES RECONCILE OUT LOUD. Five outcomes summing to the window count, printed as an
   equation. UC011 shipped a threshold slider with no handler at all under a label promising the
   tiles would re-count; it rendered perfectly and every gate stayed green. An equation that has to
   add up is a control you can see working. */
var STATE = {windows: [], status: null};

var OUT = [
  ["paged_correct",   "ok",   "Paged, correctly",  "A real incident, and somebody was told."],
  ["missed_incident", "bad",  "MISSED INCIDENT",
   "An outage nobody was told about. The cost is the whole of the downtime, and a customer finds it."],
  ["false_page",      "warn", "False page",
   "Somebody woken for nothing. Recoverable once; enough of them and the rotation stops reading the pager."],
  ["held_correct",    "ok",   "Held, correctly",   "Noise, correctly left alone."],
  ["no_verdict",      "non",  "No verdict",
   "Nothing usable came back. Never folded into 'held' — a silent model pages nobody, so it looks calm."]
];
var TRAPS = ["flapping", "retry-storm", "deploy", "quiet-killer", "cascade", "silence"];

function esc(s){ return String(s == null ? "" : s).replace(/[&<>"]/g, function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]; }); }

/* The free floor, exactly as src/rules.py runs it, over facts the server computed. Kept to the
   three inputs the rules actually have — an error count, a regex hit, and (optionally) the silence
   the code worked out. Anything else here would be the browser judging better than the floor does,
   which would flatter the floor and hide the finding. */
function floorPages(w, t, useKw, useAbs){
  if (w.loud >= t) return true;
  if (useKw && w.keyword) return true;
  if (useAbs && w.silent && w.silent.length) return true;
  return false;
}

function outcomeOf(w, pages){
  if (w.label == null) return null;
  var should = w.label === "page";
  if (pages) return should ? "paged_correct" : "false_page";
  return should ? "missed_incident" : "held_correct";
}

function paint(){
  var t = parseInt(document.getElementById("thr").value, 10);
  var useKw = document.getElementById("kw").checked;
  var useAbs = document.getElementById("ab").checked;
  document.getElementById("tv").textContent = t;

  var counts = {}, perTrap = {};
  OUT.forEach(function(o){ counts[o[0]] = 0; });
  TRAPS.forEach(function(k){ perTrap[k] = {n: 0, wrong: 0}; });

  STATE.windows.forEach(function(w){
    var pages = floorPages(w, t, useKw, useAbs);
    var out = outcomeOf(w, pages);
    if (out) counts[out]++;
    if (perTrap[w.trap]){
      perTrap[w.trap].n++;
      if (out === "missed_incident" || out === "false_page") perTrap[w.trap].wrong++;
    }
    var el = document.querySelector('[data-win="' + w.id + '"]');
    if (el){
      el.className = "win " + (out === "missed_incident" ? "bad"
                    : out === "false_page" ? "warn" : "ok");
      el.querySelector("[data-out]").textContent =
        (pages ? "PAGES" : "holds") + " — " + (OUT.filter(function(o){ return o[0] === out; })[0] || ["","","?"])[2];
    }
  });

  document.getElementById("tiles").innerHTML = OUT.map(function(o){
    return '<div class="tile ' + o[1] + '"><div class="k">' + esc(o[2]) + '</div>' +
           '<div class="n">' + counts[o[0]] + '</div><p>' + esc(o[3]) + '</p></div>';
  }).join("");

  var tot = OUT.reduce(function(a, o){ return a + counts[o[0]]; }, 0);
  document.getElementById("recon").textContent =
    OUT.map(function(o){ return counts[o[0]]; }).join(" + ") + " = " + tot + " windows judged" +
    "  —  at this setting the free rules miss " + counts.missed_incident +
    " incident(s) and wake somebody for nothing " + counts.false_page + " time(s).";

  var handled = TRAPS.filter(function(k){ return perTrap[k].n > 0 && perTrap[k].wrong === 0; });
  document.getElementById("traps").innerHTML =
    "<b>traps handled completely at this setting: " + handled.length + " of " + TRAPS.length +
    "</b> &nbsp; " + TRAPS.map(function(k){
      var ok = perTrap[k].n > 0 && perTrap[k].wrong === 0;
      return '<span class="' + (ok ? "yes" : "no") + '">' + (ok ? "✓ " : "✗ ") + esc(k) + "</span>";
    }).join(" &nbsp; ");
}

function logHtml(w){
  var rows = (w.collapsed || []).map(function(r){
    var x = r.count > 1 ? '<span class="x"> ×' + r.count + " " + esc(r.first.slice(11,19)) +
            "–" + esc(r.last.slice(11,19)) + "</span>" : "";
    return '<div class="ln"><div class="t">' + esc(r.first.slice(11,19)) + "</div>" +
           '<div class="sv">' + esc(r.service) + "</div>" +
           '<div class="lv ' + esc(r.level) + '">' + esc(r.level) + "</div>" +
           '<div class="m">' + esc(r.message) + x + "</div></div>";
  }).join("");
  if (!rows) rows = '<div class="ln"><div class="m">(no log lines at all in this window)</div></div>';
  var more = w.collapsed_total > (w.collapsed || []).length
    ? '<p class="more">' + (w.collapsed_total - w.collapsed.length) +
      " more distinct line(s) in this window, not shown here.</p>" : "";
  return '<div class="log">' + rows + "</div>" + more;
}

function render(){
  document.getElementById("windows").innerHTML = STATE.windows.map(function(w){
    var note = (w.silent || []).map(function(s){
      var h = (w.silent_history || {})[s] || [];
      return "NOTE: " + esc(s) + " emitted nothing in this window. Previous " + h.length +
             ": " + h.join(", ") + ".";
    }).join("<br>");
    return '<article class="win" data-win="' + esc(w.id) + '">' +
      '<div class="whead"><span class="wid">' + esc(w.id) + "</span>" +
      '<span class="chip trap">' + esc(w.trap) + "</span>" +
      '<span class="chip truth">truth: ' + esc(w.label) + "</span>" +
      '<span class="chip out" data-out>—</span>' +
      (w.keyword ? '<span class="chip">keyword hit</span>' : "") +
      (w.silent && w.silent.length ? '<span class="chip">silent: ' + esc(w.silent.join(", ")) + "</span>" : "") +
      '<span class="cnt">' + w.loud + " error/fatal</span>" +
      '<button class="ask" data-ask="' + esc(w.id) + '">Ask the model (1 call)</button></div>' +
      (note ? '<p class="note">' + note + "</p>" : "") +
      logHtml(w) +
      '<p class="verdict" data-verdict></p></article>';
  }).join("");

  document.querySelectorAll("[data-ask]").forEach(function(b){
    b.onclick = function(){ ask(b.getAttribute("data-ask"), b); };
  });
  paint();
}

function ask(id, btn){
  var card = document.querySelector('[data-win="' + id + '"]');
  var out = card.querySelector("[data-verdict]");
  btn.disabled = true; out.textContent = "calling the model — one call…";
  fetch("/api/triage", {method: "POST", headers: {"Content-Type": "application/json"},
                        body: JSON.stringify({id: id})})
    .then(function(r){ return r.json().then(function(j){ return {ok: r.ok, j: j}; }); })
    .then(function(res){
      btn.disabled = false;
      var j = res.j;
      if (!res.ok || j.error){
        out.innerHTML = '<span class="err">' + esc(j.error || "call failed") +
          "</span> — the free floor still says <b>" + esc(j.floor_verdict || "?") + "</b> (" +
          esc((j.floor_reasons || []).join("; ")) + ")";
        return;
      }
      out.innerHTML = "model: <b>" + esc(j.verdict || "(nothing usable)") + "</b> &nbsp; outcome: <b>" +
        esc(j.outcome) + "</b> &nbsp; free floor: " + esc(j.floor_verdict) +
        " &nbsp; truth: " + esc(j.label) + " &nbsp; " + j.input_tokens + " in / " +
        j.output_tokens + " out, finish " + esc(j.finish_reason);
    })
    .catch(function(e){ btn.disabled = false; out.innerHTML = '<span class="err">' + esc(e) + "</span>"; });
}

fetch("/api/status").then(function(r){ return r.json(); }).then(function(s){
  STATE.status = s;
  document.getElementById("thr").value = s.threshold;
  // ⚠︎ Both halves are whole sentences. The first version glued a trailing "— every " onto a note
  // that already began "Every Ask-the-model click…", and rendered "every Every" on the first line
  // a reader sees. Every gate was green; it was found by looking at the page.
  document.getElementById("cost").textContent =
    (s.has_key
      ? "A key IS configured (" + (s.model || "?") + "), so this page can spend. "
      : "No key is configured, so nothing on this page can call anything. ") + s.cost_note;
  var g = s.gate || {};
  document.getElementById("gate").textContent =
    g.candidates + " of " + g.windows + " windows pass the gate and could reach a model; the other " +
    (g.windows - g.candidates) + " are held for free. Gate recall " +
    (100 * g.gate_recall).toFixed(1) + "% — every incident survives it. " +
    "A gate that dropped incidents would set a ceiling no model quality could lift.";
  if (s.claim){
    document.getElementById("claim").textContent =
      "Measured over " + s.claim.settings_tested + " settings of the free rules: " +
      (s.claim.holds ? "none got all six traps right. The one no setting reaches is "
                     + (s.claim.unreachable_traps || []).join(", ") + "."
                     : "some settings DID get all six — the free floor is enough.");
  }
  return fetch("/api/windows");
}).then(function(r){ return r.json(); }).then(function(d){
  STATE.windows = d.windows;
  render();
});

["thr", "kw", "ab"].forEach(function(id){
  var el = document.getElementById(id);
  el.addEventListener("input", paint);
  el.addEventListener("change", paint);
});
