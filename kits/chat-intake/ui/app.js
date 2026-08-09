/* chat-intake — the whole UI. Vanilla, no build step, no dependency.
 *
 * ⚠︎ TWO SOURCES OF TRUTH ARE SHOWN AND THEY ARE NEVER MERGED. `replay` is the dataset's own
 * dialogue state — what the conversation actually established by this turn. `answer` is a model's
 * reading of the same turns, and only exists when a key is configured. Painting them into one
 * column would turn a replay into a prediction, which is the one dishonest thing this page could
 * do. Without a key you see replay only, and the banner says so.
 */
(function () {
  "use strict";
  var S = { conv: null, step: 0, hasKey: false, answer: null };
  var $ = function (id) { return document.getElementById(id); };

  function get(url) { return fetch(url).then(function (r) { return r.json(); }); }

  function show(id, on) { $(id).hidden = !on; }

  function boot() {
    get("/api/state").then(function (st) {
      S.hasKey = st.has_key;
      if (!st.built) {
        show("notbuilt", true);
        $("buildcmds").textContent = st.build_with.join("\n");
        return;
      }
      show("replay", !st.has_key);
      show("picker", true);
      show("statedoc", true);
      $("conv").innerHTML = st.cases.map(function (c) {
        return '<option value="' + c.dialogue_id + '">' + c.dialogue_id + " · " + c.intent +
               " — " + c.opening.slice(0, 58) + "</option>";
      }).join("");
      $("states").innerHTML = st.states.map(function (s) {
        return '<div class="card"><span class="nm"></span><p class="m"></p>' +
               '<p><b>Wrong here costs:</b> <span class="c"></span></p></div>';
      }).join("");
      // Text set via textContent rather than interpolated, so a value from disk can never become
      // markup. The shapes above are ours; the strings are the kit's data.
      var cards = $("states").querySelectorAll(".card");
      st.states.forEach(function (s, i) {
        cards[i].querySelector(".nm").textContent = s.key;
        cards[i].querySelector(".m").textContent = s.means;
        cards[i].querySelector(".c").textContent = s.costs;
      });
      load();
    });
  }

  function load() {
    get("/api/conversation/" + encodeURIComponent($("conv").value)).then(function (c) {
      S.conv = c; S.step = 0; S.answer = null; S.unparsedStreak = 0;
      show("live", true);
      $("intent").textContent = c.intent + " — " + c.required.length + " required fact(s)";
      render();
    });
  }

  function stateOf(fact) {
    var step = S.conv.steps[S.step];
    var src = S.answer ? S.answer.collected : step.replay;
    if (!(fact in src)) return { cls: "gap", label: "still missing", value: "not yet given" };
    var v = src[fact];
    var shown = Array.isArray(v) ? v[0] : v;
    if (S.answer) {
      var gold = step.replay[fact];
      var ok = gold && gold.some(function (g) {
        return String(g).trim().toLowerCase() === String(shown).trim().toLowerCase();
      });
      if (!ok) return { cls: "brk", label: "wrong against gold", value: shown };
    }
    return { cls: "met", label: "collected", value: shown };
  }

  function render() {
    var step = S.conv.steps[S.step];
    $("turns").innerHTML = "";
    step.turns.forEach(function (t) {
      var d = document.createElement("div");
      d.className = "turn" + (t.speaker === "USER" ? " u" : "");
      var w = document.createElement("span"); w.className = "who"; w.textContent = t.speaker;
      var u = document.createElement("span"); u.className = "utt"; u.textContent = t.utterance;
      d.appendChild(w); d.appendChild(u); $("turns").appendChild(d);
    });

    var body = $("slots"); body.innerHTML = "";
    S.conv.required.forEach(function (f) {
      var s = stateOf(f);
      var tr = document.createElement("tr"); tr.className = s.cls;
      var a = document.createElement("td"); a.className = "fact"; a.textContent = f;
      var b = document.createElement("td"); b.textContent = s.value;
      var c = document.createElement("td");
      c.innerHTML = '<span class="st ' + s.cls + '"></span>';
      c.querySelector(".st").textContent = s.label;
      tr.appendChild(a); tr.appendChild(b); tr.appendChild(c); body.appendChild(tr);
    });

    var src = S.answer ? S.answer.collected : step.replay;
    var missing = S.conv.required.filter(function (f) { return !(f in src); });
    var d = $("decision");
    d.className = "decision" + (missing.length ? "" : " stop");
    d.textContent = (missing.length
      ? "Ask again — " + missing.length + " required fact(s) still missing: " + missing.join(", ")
      : "Nothing further is needed — the checklist is full.")
      + (S.answer ? "  [model]" : "  [replay — the dataset's own state, not a prediction]");

    $("step").disabled = S.step >= S.conv.steps.length - 1;
    $("ask").hidden = !S.hasKey;
  }

  /* One call, on the turn currently displayed. Split out of advance() so the FIRST turn can be
   * read too — the shoot tool needs a model answer at step 0, and more importantly a reader who
   * opens a conversation and presses this expects the answer to be about what they are looking at.
   *
   * ⚠︎ IT IS A BUTTON, NOT SOMETHING load() DOES. Calling on load would spend a call every time
   * the picker changes, which is a bill nobody asked for by browsing. */
  function ask() {
    if (!S.hasKey || !S.conv) return;
    var step = S.conv.steps[S.step];
    $("ask").disabled = true;
    fetch("/api/turn", {
      method: "POST", headers: { "Content-Type": "application/json" },
      /* The unparsed streak rides in the request beside the turns, because the server keeps no
       * state between calls and a counter is not the thing to break that for. */
      body: JSON.stringify({ intent: S.conv.intent, turns: step.turns,
                             unparsed_before: S.unparsedStreak || 0 })
    }).then(function (r) { return r.json(); }).then(function (out) {
      $("ask").disabled = false;
      if (out.error) { return; }        // replay stays on screen; it is still true
      S.unparsedStreak = out.unparsed_streak || 0;
      S.answer = out;
      render();
    }).catch(function () { $("ask").disabled = false; });
  }

  function advance() {
    if (S.step >= S.conv.steps.length - 1) return;
    S.step += 1;
    S.answer = null;
    render();
    ask();
  }

  $("conv").addEventListener("change", load);
  $("step").addEventListener("click", advance);
  $("ask").addEventListener("click", ask);
  /* The streak resets with the conversation. A counter that outlives its conversation
   would escalate a fresh one on its first reply. */
  $("reset").addEventListener("click", function () {
    S.step = 0; S.answer = null; S.unparsedStreak = 0; render();
  });
  boot();
})();
