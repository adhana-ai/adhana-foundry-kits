"""SEAM 2 — the cut. Turning a stream into things that can be judged one at a time.

⚑ THIS IS THE FIRST STATION AND IT IS PURE CODE, WHICH IS THE WHOLE SHAPE OF THIS KIT. Every other
use case in this repo receives its unit of work already formed: a document arrives, a question is
asked, a pair of rows is handed over. An event stream has no units in it. Something has to decide
where one thing being judged stops and the next begins, and that decision is made here, before a
model is involved, by code a person can read.

⚠︎ AND IT IS NOT A NEUTRAL STEP. A five-minute bucket and a fifteen-minute bucket are two different
questions about one incident, not two settings of one question. Widen the window and the retry
storm's recovery line lands inside it, so the window explains itself and the right answer flips
from page to hold. Narrow it and the cascade splits across four windows, each of which looks like a
separate outage, which is how a pager storm is manufactured out of one root cause. The bucket size
is a product decision wearing the costume of a constant, so it is a constant with an argument
attached rather than a number buried in a loop.

⚑ WHY FIXED BUCKETS AND NOT A SESSIONISER. Grouping events by "gaps longer than n seconds" produces
windows whose boundaries depend on the traffic, which means the unit of work changes shape when the
system gets busy — exactly when you least want the measurement to move. Fixed buckets are boring,
reproducible, and cut some incidents in half; that last one is a real cost and it is visible in the
labels rather than hidden, because a two-window incident is labelled `page` in both of its windows.

── DEDUPLICATION ──────────────────────────────────────────────────────────────────────────────────

⚑ 47 IDENTICAL LINES ARE ONE FACT, AND SENDING THEM 47 TIMES IS PAYING TO SAY IT AGAIN. The flapping
health check emits the same string every six seconds; verbatim, it would be most of the prompt and
most of the bill. `collapse()` folds identical (service, level, message) triples into one line
carrying its count and its first and last timestamp.

⚠︎ THE COUNT IS KEPT, LOUDLY, BECAUSE IT IS EVIDENCE AND NOT NOISE. "healthz timeout ×47 over 4m42s"
and "healthz timeout" are different observations — the first says a probe is failing continuously,
the second says it failed. Collapsing without the count would delete the very signal a rule engine
uses, and then the comparison between the model and the rules would be unfair in the model's
favour, which is the one direction this repo must never let a measurement lean.

── THE GATE ───────────────────────────────────────────────────────────────────────────────────────

⚑ `candidates()` IS THE ANALOGUE OF UC011's BLOCKER AND IT CARRIES THE SAME DANGER. Nothing sane
asks a model about every five-minute slice of a healthy system — the great majority of windows are
ordinary traffic and are held for free. So a cheap pure-code gate decides which windows are worth a
call, and every score this kit publishes is conditional on that gate having passed the window at
all.

⚠︎ WHICH IS WHY THE GATE HAS TO BE ABLE TO SEE AN ABSENCE. The obvious gate is "any ERROR, FATAL or
WARN in the window". It is one line, it is what everybody writes first, and on this corpus it drops
every single `silence` window — a service that has stopped logging produces no line of any level,
so the cheapest possible filter silently discards the hardest trap in the set before anything can
look at it. The kit's headline finding would have been destroyed by its own pre-filter, and the
scores would have looked *better* for it, because the windows it dropped are ones the model would
have had to get right. `stats()` measures exactly this and publishes it beside every score.

**A pre-filter that cannot see the thing the kit is about is not an optimisation. It is the bug.**
"""
import csv
import datetime as dt
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS = os.path.join(HERE, "data", "events.csv")

# Must match tools/build_corpus.py. Both read it from here rather than each holding a copy.
START = dt.datetime(2026, 3, 14, 0, 0, 0, tzinfo=dt.timezone.utc)
WINDOW_S = 300

LOUD = ("ERROR", "FATAL")
# ⚠︎ `deploy` IS LEGITIMATELY QUIET AND MUST NEVER COUNT AS SILENT. It is a release pipeline, not a
# request path: it says nothing for hours at a time and that is health, not an outage. A gate that
# did not know this would page on every quiet afternoon, and the corpus deliberately contains those
# afternoons.
ALWAYS_TALKING = ("checkout", "auth", "payments", "orders", "billing", "search", "postgres")
# How much history the absence check reads. Six windows is thirty minutes: long enough that a
# service which merely paused is not reported, short enough to notice inside one pager cycle.
HISTORY = 6


def load_events(path=EVENTS):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def index_of(stamp):
    """Which window an ISO timestamp falls in. Arithmetic against START, never the clock."""
    t = dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    return int((t - START).total_seconds() // WINDOW_S)


def cut(events, n_windows=None):
    """The stream into fixed buckets. Returns a list of {id, index, start, events}."""
    buckets = {}
    for e in events:
        buckets.setdefault(index_of(e["ts"]), []).append(e)
    n = n_windows or (max(buckets) + 1 if buckets else 0)
    out = []
    for i in range(n):
        out.append({"id": "w%03d" % i, "index": i,
                    "start": (START + dt.timedelta(seconds=i * WINDOW_S)).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"),
                    "events": sorted(buckets.get(i, []), key=lambda e: e["ts"])})
    return out


def collapse(win):
    """Identical (service, level, message) folded into one line with its count and time span.

    Order is preserved by first appearance, because the sequence is part of the evidence: a deploy
    line followed by errors is a different window from errors followed by a deploy line, and a
    dictionary that sorted its keys would delete that distinction.
    """
    seen, order = {}, []
    for e in win["events"]:
        key = (e["service"], e["level"], e["message"])
        if key not in seen:
            seen[key] = {"service": e["service"], "level": e["level"], "message": e["message"],
                         "count": 0, "first": e["ts"], "last": e["ts"]}
            order.append(key)
        row = seen[key]
        row["count"] += 1
        row["last"] = max(row["last"], e["ts"])
        row["first"] = min(row["first"], e["ts"])
    return [seen[k] for k in order]


def counts(win):
    """The numbers a rule engine actually has. Levels are counted over RAW events, not collapsed
    lines — 47 timeouts is 47 errors to a threshold, and pretending otherwise would hand the floor
    a discount it does not get in production."""
    out = {"ERROR": 0, "FATAL": 0, "WARN": 0, "INFO": 0}
    for e in win["events"]:
        out[e["level"]] = out.get(e["level"], 0) + 1
    out["loud"] = out["ERROR"] + out["FATAL"]
    out["lines"] = len(win["events"])
    return out


def gone_silent(windows, i, history=HISTORY):
    """Services that emitted nothing in window `i` while being reliably talkative before it.

    ⚑ THIS IS THE ONLY THING IN THE WHOLE KIT THAT LOOKS OUTSIDE ITS OWN WINDOW, and it has to:
    zero lines from `payments` is unremarkable on its own and alarming only against the fact that
    payments has not stopped talking once all day. A window is not self-describing, which is worth
    knowing before designing any system that judges one.

    ⚠︎ THE RULE IS A MAJORITY OF THE HISTORY, NOT ALL OF IT, AND THE FIRST VERSION GOT THIS WRONG.
    Requiring the service to have talked in *every* one of the previous `history` windows detects
    the moment silence STARTS and is blind the moment after — because by the second window of an
    outage, the immediately-previous window is itself silent and the condition can never hold
    again. Measured on this corpus, that version passed 3 of the 6 `silence` windows and reported a
    gate recall of 85%, losing the second half of every silence incident. **An outage does not stop
    being an outage because it is still going on.** A majority of the history keeps the onset and
    the continuation, and degrades honestly: once a service has been quiet for more than `history`
    windows, silence is the new normal to this check and it stops firing. That is a real ceiling on
    how long an outage can go unnoticed here, and it is written down rather than discovered later.
    """
    if i < history:
        return []                       # no history yet — refuse to guess rather than guess quietly
    here = {e["service"] for e in windows[i]["events"]}
    out = []
    for svc in ALWAYS_TALKING:
        if svc in here:
            continue
        talked = sum(1 for k in range(1, history + 1)
                     if any(e["service"] == svc for e in windows[i - k]["events"]))
        if talked * 2 > history:
            out.append(svc)
    return sorted(out)


def candidates(windows):
    """The windows worth spending a call on, and why each one qualified.

    Cheap, pure code, and deliberately generous: this decides what the model is ALLOWED to see, so
    an error here cannot be recovered downstream by any amount of model quality.
    """
    out = {}
    for i, w in enumerate(windows):
        c = counts(w)
        silent = gone_silent(windows, i)
        why = []
        if c["loud"]:
            why.append("%d error/fatal line(s)" % c["loud"])
        if c["WARN"]:
            why.append("%d warn line(s)" % c["WARN"])
        if silent:
            why.append("silent: %s" % ", ".join(silent))
        if why:
            out[w["id"]] = {"why": why, "silent": silent, "counts": c}
    return out


def stats(windows, labels):
    """What the gate cost, in the only currency that matters: incidents it never showed anybody.

    ⚠︎ `gate_recall` IS THE CEILING ON EVERY SCORE THIS KIT PUBLISHES. A window the gate drops is
    held by default and no model can rescue it, so a gate that quietly loses 30% of the incidents
    would make every downstream number look 30% better than the system is. It is published beside
    the scores for the same reason UC011 publishes blocking recall: a number conditional on a step
    nobody reported is not a measurement.
    """
    cand = candidates(windows)
    by_id = {row["id"]: row for row in labels}
    should = [r for r in labels if r["label"] == "page"]
    kept = [r for r in should if r["id"] in cand]
    lost = [r["id"] for r in should if r["id"] not in cand]
    return {"windows": len(windows), "candidates": len(cand),
            "reduction": round(1 - len(cand) / len(windows), 4) if windows else None,
            "should_page": len(should), "should_page_surviving": len(kept),
            "gate_recall": round(len(kept) / len(should), 4) if should else None,
            "lost_to_gate": lost,
            "lost_traps": sorted({by_id[i]["trap"] for i in lost})}
