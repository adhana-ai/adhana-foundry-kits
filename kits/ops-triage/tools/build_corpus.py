#!/usr/bin/env python3
"""Generate the event stream and the labelled windows from a fixed seed.

    python3 tools/build_corpus.py

Writes data/events.csv and data/labelled.jsonl, byte-identical on every run. Nothing is fetched and
nothing is licensed from anybody: the events are invented here, so the corpus ships under this
repo's MIT licence and there is no third-party grant to verify.

⚑ WHY THE LOGS ARE INVENTED, AND WHY THAT IS THE HONEST CHOICE HERE RATHER THAN THE CONVENIENT ONE.
Real production logs cannot be published at all. They carry hostnames, internal service names,
customer identifiers, session tokens and the shape of somebody's internal network, and no amount of
scrubbing makes that safe to put in a public repo — the interesting lines are exactly the ones that
carry the most identifying detail. A synthetic stream is the only kind of alert-triage corpus that
can be re-run by a stranger with a clone and no agreement to sign. See data/SOURCES.md.

⚑ THE UNIT OF WORK IS A WINDOW, WHICH IS WHY THIS FILE EMITS TWO THINGS. Every other kit in this
repo labels a thing that arrives whole — a document, a question, a pair of rows. Here the raw
material is a STREAM, and the thing being judged does not exist until something cuts it up. So the
generator writes the stream (`events.csv`) and the ground truth for each five-minute slice of it
(`labelled.jsonl`), and `src/window.py` is what turns the first into the second's subject. Change
the bucket size and you have changed the question, not the answer.

⚑ THE SIX TRAPS ARE PLANTED, NOT HOPED FOR. A corpus that cannot express the failure cannot show
the eval layer earning its keep. Each one is generated on purpose, counted, and asserted:

    flapping        a health check that has been failing for nine days and never meant anything.
                    LOUD and the correct answer is to do nothing.
    retry-storm     high volume, self-healing, backoff working exactly as designed. LOUD, harmless.
    deploy          errors that spike right after a release line and stop on their own. LOUD, and
                    the explanation is one INFO line the rule engine cannot read.
    quiet-killer    one WARN, no threshold reacts, and in two days every login stops. THE
                    EXPENSIVE ONE.
    cascade         one root cause, five services failing, 200+ lines. LOUD and real.
    silence         a service that stops logging. ⚑ NO REGEX CAN SEE THIS — the signal is the
                    ABSENCE of lines, and every rule in the free floor is written to match text
                    that is there.

⚠︎ AND THE PLANTED ONES MUST BE THE ONLY ONES — THIS IS WHERE UC010 WENT WRONG. Its generator drew
400 names from a pool of 280 combinations and produced 117 accidental duplicates under a comment
claiming exactly one was planted; nobody noticed until the eval started scoring collisions nobody
had designed. So `audit()` asserts the census here: every window carries exactly one trap, the trap
counts match the constants at the top of this file, and — the check that matters most on a corpus
whose signal is an absence — every window labelled `silence` really does contain zero lines from a
service that was active in the windows before it. An accidental silence is a build failure, not a
curiosity.

⚠︎ THE NOISE IS NOT TIDIED AND MUST NOT BE. It is tempting to emit a clean stream so the numbers
look better. The noise IS the input: a real pager sits on top of a service that logs constantly and
mostly boringly, and a corpus without that floor measures a different problem.
"""
import csv
import datetime as dt
import json
import os
import random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS = os.path.join(HERE, "data", "events.csv")
LABELS = os.path.join(HERE, "data", "labelled.jsonl")

SEED = 20260813
# ⚑ THE CLOCK IS NEVER READ. A corpus stamped with "now" is a corpus that changes every time it is
# built, which would make every committed number in this repo unreproducible. The stream starts at a
# fixed instant and every timestamp is derived from it by arithmetic.
START = dt.datetime(2026, 3, 14, 0, 0, 0, tzinfo=dt.timezone.utc)
WINDOW_S = 300                       # five minutes — the bucket size, and see window.py on why
N_WINDOWS = 240                      # 20 hours of stream

# ⚑ THE COMPOSITION IS DECLARED HERE AND ASSERTED BELOW, because it is the only place a reader can
# check that the corpus says what the README says it says. These are windows, not events.
N_QUIET = 150            # nothing but ordinary INFO traffic, and one WARN in some of them
N_FLAPPING = 40          # the broken health check
N_RETRY = 18             # backoff storms that recover
N_DEPLOY = 12            # a release, then errors that stop on their own
N_QUIET_KILLER = 8       # one WARN that means an outage in two days
N_SILENCE = 6            # a service stops logging
N_CASCADE = 6            # one root cause, everything downstream

SERVICES = ["checkout", "auth", "payments", "orders", "billing", "search", "postgres", "deploy"]
# ⚠︎ `deploy` IS NOT A SERVICE AND IT IS IN THE LIST ANYWAY. It is a release pipeline writing to the
# same stream, which is exactly how it looks to a pager, and its INFO lines are the context the
# `deploy` trap turns on. Excluding it here would have deleted the trap.

NORMAL = {
    "checkout": ["cart {n} converted in {ms}ms", "session {n} started",
                 "payment intent {n} created", "cart {n} abandoned after {ms}ms"],
    "auth": ["token issued for session {n}", "login succeeded in {ms}ms",
             "session {n} refreshed", "logout for session {n}"],
    "payments": ["charge {n} authorised in {ms}ms", "settlement batch {n} queued",
                 "refund {n} completed", "webhook {n} acknowledged"],
    "orders": ["order {n} accepted", "order {n} dispatched in {ms}ms",
               "inventory check {n} passed", "order {n} invoiced"],
    "billing": ["invoice {n} rendered in {ms}ms", "dunning run {n} complete",
                "subscription {n} renewed", "credit note {n} issued"],
    "search": ["query {n} served in {ms}ms", "index segment {n} merged",
               "suggest cache warm, {n} entries", "query {n} served in {ms}ms"],
    "postgres": ["checkpoint complete, {n} buffers written", "autovacuum finished on table {n}",
                 "connection {n} authorised", "replication lag {ms}ms"],
    "deploy": ["pipeline {n} green", "artefact {n} published", "canary {n} healthy"],
}
# A little ordinary WARN traffic, so "any WARN" is not a free oracle for the gate or the rules. A
# corpus where every WARN is an incident makes both look far better than they are.
BENIGN_WARN = {
    "checkout": "slow downstream call to search, {ms}ms",
    "auth": "clock skew {ms}ms against ntp peer",
    "payments": "retrying webhook {n}, attempt 2",
    "orders": "inventory check {n} took {ms}ms",
    "billing": "invoice {n} re-rendered after template cache miss",
    "search": "query {n} exceeded {ms}ms budget",
    "postgres": "autovacuum on table {n} skipped, lock not available",
    "deploy": "canary {n} restarted once before becoming healthy",
}

# ⚑ THE QUIET KILLERS ARE WRITTEN AS REAL LINES, NOT AS "PROBLEM DETECTED". The whole claim of this
# trap is that a competent regex does not fire on them and a person reading them would act, so they
# have to be the sort of line a real system emits when something slow and fatal is starting. Each
# is a genuine two-day-fuse failure: nothing is on fire and something is going to be.
KILLERS = [
    ("auth", "certificate for auth.internal expires in {h} hours",
     "certificate renewal job last succeeded {d} days ago"),
    ("postgres", "replication slot standby2 is retaining {gb}GB of WAL",
     "standby2 last streamed {h} hours ago"),
    ("payments", "settlement file for {d} not acknowledged by the bank",
     "acknowledgement usually arrives within 30 minutes"),
    ("billing", "disk usage on billing-data at {pc}%, growing {gb}GB per day",
     "last successful archive job was {d} days ago"),
]


def ts(i, offset=0):
    """A timestamp inside window `i`, `offset` seconds in. Arithmetic only — see START."""
    return (START + dt.timedelta(seconds=i * WINDOW_S + offset)).strftime("%Y-%m-%dT%H:%M:%SZ")


def build():
    rng = random.Random(SEED)
    events, windows = [], []

    def emit(i, offset, service, level, message):
        events.append({"ts": ts(i, offset), "service": service, "level": level,
                       "message": message})

    def fill(i, skip=()):
        """The ordinary traffic every window carries. `skip` is how a service goes silent."""
        for svc in SERVICES:
            if svc in skip:
                continue
            # `deploy` is a pipeline, not a request path — it is quiet most of the time, which is
            # what makes its INFO line meaningful when it does appear.
            n = rng.randint(0, 2) if svc == "deploy" else rng.randint(5, 9)
            for _ in range(n):
                tmpl = rng.choice(NORMAL[svc])
                emit(i, rng.randint(0, WINDOW_S - 1), svc, "INFO",
                     tmpl.format(n=rng.randint(1000, 99999), ms=rng.randint(4, 320)))

    # ── the running order ─────────────────────────────────────────────────────────────────────────
    # ⚠︎ TRAPS ARE PLACED BEFORE ANY EVENT IS WRITTEN, so that "one trap per window" is a property of
    # the plan rather than something hoped for afterwards. Multi-window traps claim consecutive
    # slots, because an incident that starts at 22:07 does not politely end at 22:10.
    plan = {}

    def claim(kind, n_windows, span, lo=12, hi=N_WINDOWS):
        """Place `n_windows // span` incidents of `span` consecutive windows each."""
        placed = 0
        while placed < n_windows:
            start = rng.randrange(lo, hi - span)
            if any((start + k) in plan for k in range(-1, span + 1)):
                continue          # never adjacent: a gap keeps each incident its own story
            for k in range(span):
                plan[start + k] = (kind, k, start)
            placed += span

    # The three that page, first, so they get the room they need.
    claim("cascade", N_CASCADE, 2)
    claim("silence", N_SILENCE, 2)
    claim("quiet-killer", N_QUIET_KILLER, 2)
    claim("deploy", N_DEPLOY, 2)
    claim("retry-storm", N_RETRY, 2)
    claim("flapping", N_FLAPPING, 1, lo=0)

    killer_of = {}
    silent_of = {}
    for i in sorted(k for k, v in plan.items() if v[0] == "quiet-killer" and v[1] == 0):
        killer_of[i] = KILLERS[len(killer_of) % len(KILLERS)]
    for i in sorted(k for k, v in plan.items() if v[0] == "silence" and v[1] == 0):
        # Never `deploy` — it is legitimately quiet, so its absence signals nothing and a corpus
        # that labelled it as an incident would be teaching the model a false rule.
        silent_of[i] = ["payments", "search", "orders", "billing"][len(silent_of) % 4]

    for i in range(N_WINDOWS):
        kind, step, start = plan.get(i, ("quiet", 0, i))
        skip = ()
        if kind == "silence":
            skip = (silent_of[start],)
        fill(i, skip=skip)

        # Ordinary WARN traffic, everywhere, including inside the loud traps.
        if rng.random() < 0.22:
            svc = rng.choice(SERVICES)
            emit(i, rng.randint(0, WINDOW_S - 1), svc, "WARN",
                 BENIGN_WARN[svc].format(n=rng.randint(1000, 99999), ms=rng.randint(400, 2400)))

        if kind == "flapping":
            # ⚑ 47 IDENTICAL LINES, WHICH IS WHY THE WINDOW CUTTER DEDUPLICATES. A probe every six
            # seconds that has timed out for nine days. The count is the trap and the message is
            # the tell: a rule engine sees 47 errors, a person sees the same error 47 times.
            for k in range(47):
                emit(i, k * 6, "checkout", "ERROR", "healthz timeout after 2000ms")
        elif kind == "retry-storm":
            back = 1
            for k in range(48):
                emit(i, k * 6, "search", "ERROR",
                     "upstream 429, backing off %ds" % back)
                back = min(back * 2, 32)
            if step == 1:
                emit(i, 240, "search", "INFO", "recovered after 96 attempts, upstream healthy")
        elif kind == "deploy":
            if step == 0:
                emit(i, 3, "deploy", "INFO", "release 4.18.%d rolling out to 12 of 12 pods" % (i % 9))
            for k in range(16):
                emit(i, 20 + k * 15, "orders", "ERROR", "connection reset by peer")
            if step == 1:
                emit(i, 270, "orders", "INFO", "healthy, 12 of 12 pods ready")
                emit(i, 275, "deploy", "INFO", "release complete, no rollback")
        elif kind == "quiet-killer":
            svc, warn, info = killer_of[start]
            emit(i, 62, svc, "WARN",
                 warn.format(h=47 - step * 5, d=62 + step, gb=31 + step * 2, pc=91 + step))
            emit(i, 63, svc, "INFO",
                 info.format(h=19 + step, d=62 + step, gb=31, pc=91))
        elif kind == "cascade":
            if step == 0:
                emit(i, 4, "postgres", "FATAL", "the database system is shutting down")
                emit(i, 5, "postgres", "FATAL", "could not write to WAL, device reports no space")
            for k in range(52):
                svc = ["orders", "billing", "checkout", "payments"][k % 4]
                emit(i, 6 + k * 5, svc, "ERROR", "could not connect to server: connection refused")
            if step == 1:
                emit(i, 290, "postgres", "ERROR", "recovery in progress, 3 of 9 segments replayed")
        elif kind == "silence":
            pass                   # the trap IS the fill() above declining to write anything

        label = "page" if kind in ("quiet-killer", "cascade", "silence") else "hold"
        windows.append({"id": "w%03d" % i, "start": ts(i), "label": label, "trap": kind,
                        "silent_service": silent_of.get(start) if kind == "silence" else None})

    events.sort(key=lambda e: (e["ts"], e["service"], e["message"]))
    return events, windows


def audit(events, windows):
    """The census, asserted. A number in the README that no code checks is a number that goes wrong."""
    problems = []
    counts = {}
    for w in windows:
        counts[w["trap"]] = counts.get(w["trap"], 0) + 1
    want = {"quiet": N_QUIET, "flapping": N_FLAPPING, "retry-storm": N_RETRY, "deploy": N_DEPLOY,
            "quiet-killer": N_QUIET_KILLER, "silence": N_SILENCE, "cascade": N_CASCADE}
    for k, v in sorted(want.items()):
        if counts.get(k, 0) != v:
            problems.append("trap %r produced %d window(s), the constants say %d"
                            % (k, counts.get(k, 0), v))
    if len(windows) != N_WINDOWS:
        problems.append("%d windows, expected %d" % (len(windows), N_WINDOWS))

    # ⚑ THE CHECK THAT MATTERS MOST ON THIS CORPUS: AN ACCIDENTAL SILENCE IS A PLANTED SILENCE
    # NOBODY PLANTED. The whole `silence` trap is "a service that was talking has stopped", so a
    # quiet window where `search` happened to draw zero lines would be an unlabelled instance of
    # the hardest trap in the set — indistinguishable from the real one to the gate, to the rules
    # and to the model, and scored as though the correct answer were `hold`. This is the exact
    # shape of UC010's 117 accidental duplicates, in the one place it would do the most damage.
    per = {}
    for e in events:
        key = (e["ts"][:19], e["service"])
        per.setdefault(key, 0)
    seen = {}
    for e in events:
        i = (dt.datetime.strptime(e["ts"], "%Y-%m-%dT%H:%M:%SZ")
             .replace(tzinfo=dt.timezone.utc) - START).total_seconds() // WINDOW_S
        seen.setdefault(int(i), set()).add(e["service"])
    for n, w in enumerate(windows):
        active = seen.get(n, set())
        missing = sorted(set(SERVICES) - active - {"deploy"})
        if w["trap"] == "silence":
            if w["silent_service"] not in missing:
                problems.append("%s is labelled silence for %r, which did emit lines"
                                % (w["id"], w["silent_service"]))
            elif len(missing) > 1:
                problems.append("%s is labelled silence for %r and %d other service(s) are also "
                                "silent — the trap is not the only signal in its own window"
                                % (w["id"], w["silent_service"], len(missing) - 1))
        elif missing:
            problems.append("%s (%s) has an UNPLANTED silence: %s emitted nothing"
                            % (w["id"], w["trap"], ", ".join(missing)))

    # One trap per window, and every window accounted for.
    if len({w["id"] for w in windows}) != len(windows):
        problems.append("duplicate window ids")

    page = sum(1 for w in windows if w["label"] == "page")
    return problems, {"events": len(events), "windows": len(windows), "page": page,
                      "hold": len(windows) - page, "traps": counts}


def main():
    events, windows = build()
    problems, census = audit(events, windows)

    print("CORPUS — seed %d, deterministic, no clock read\n" % SEED)
    print("  events             %d" % census["events"])
    print("  windows            %d   (%d page / %d hold)"
          % (census["windows"], census["page"], census["hold"]))
    print("  balance            %.0f%% page — stated, because a triager scored on a mostly-hold set"
          % (100.0 * census["page"] / census["windows"]))
    print("                     looks excellent by never waking anybody, and misses every incident")
    print("\n  planted traps")
    for k, v in sorted(census["traps"].items()):
        print("    %-14s %3d" % (k, v))

    if problems:
        print("\nAUDIT FAILED — %d problem(s). The corpus does not say what the README says it says:"
              % len(problems))
        for p in problems[:12]:
            print("  - %s" % p)
        raise SystemExit(1)
    print("\n  audit              clean — one trap per window, and every silence is one we planted")

    with open(EVENTS, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["ts", "service", "level", "message"])
        w.writeheader()
        for e in events:
            w.writerow(e)
    with open(LABELS, "w", encoding="utf-8") as fh:
        for win in windows:
            fh.write(json.dumps(win, sort_keys=True) + "\n")
    print("\nwrote data/events.csv and data/labelled.jsonl")


if __name__ == "__main__":
    main()
