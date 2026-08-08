"""A cap on live calls, shared by every kit on this machine. No dependency, no service.

⚠︎ WHY THIS EXISTS. One key funds every kit here — that is the whole point of the shared `.env`,
and it is also the hole in it. Before this, nothing anywhere counted: a loop with a bad exit
condition, a `--limit` left off, a run started twice in two terminals, or simply a corpus larger
than the person starting the run remembered, and the first sign of trouble is the provider's
dashboard tomorrow. Each kit's harness prints what it is *about* to spend, which protects you from
the run you are watching and not at all from the one you forgot.

⚑ IT COUNTS CALLS, NOT DOLLARS, AND THAT IS DELIBERATE. A dollar cap needs a price for the model
you are pointed at, and the kit does not know it: rate cards move, a forker may be on a local
server that is free or an enterprise contract nobody here can see, and a cap that silently reads
the wrong card is worse than none. A call is a thing this file can count with certainty. Multiply
by your own rate card if you want a number in money — the ledger records the model on every line.

⚑ WHERE THE CAP AND THE LEDGER LIVE — the same precedence config.py uses, for the same reason.
The cap is read from the shared `.env`, then this kit's own, then the real environment; the
ledger sits beside whichever `.env` is the shared one, so every kit under that root counts against
one budget. That is what makes it a cap on the KEY rather than a cap per kit, which would be no
cap at all when the kits share a key.

⚠︎ NO CAP CONFIGURED FALLS BACK TO THE HARD CEILING, NOT TO UNLIMITED. A forker who clones one kit
has no repo root above it and must still get a working kit, so absence of MAX_CALLS_PER_DAY is not
an error — but it is also never silently infinite. Absence, and any unparseable value, both land on
HARD_CEILING below, the one number this file will not go past no matter what `.env` says.

⚑ THE HARD CEILING IS A SEPARATE NUMBER FROM MAX_CALLS_PER_DAY, ON PURPOSE. `.env` sets the day's
working cap and is meant to move — raised for a real run, reverted after. HARD_CEILING is the number
`.env` can never push past, because `.env` is a file whoever is operating this kit (including an
agent) can edit on its own judgment mid-run, and a "raise the cap?" / "yes" exchange is not the same
as a decision made by opening this file and changing this constant. Set 2026-08-07 by the operator
at 300 calls/day — raising it means editing HARD_CEILING here directly, never via `.env`, never on
a chat "yes."

    MAX_CALLS_PER_DAY=200          # in <repo>/.env — all kits, rolling calendar day, local time

The ledger is append-only and one line per call, written BEFORE the call is made. A crash mid-call
therefore over-counts by one rather than under-counting, which is the direction a spend guard
should round.
"""
import json
import os
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.basename(HERE)
# kits/<slug> -> kits -> the repo root, resolved exactly as config.py resolves it.
ROOT = os.path.dirname(os.path.dirname(HERE))
SHARED_ENV = os.path.join(ROOT, ".env")
# Beside the shared .env when there is one, else inside the kit — a lone fork still counts itself.
LEDGER = os.path.join(ROOT if os.path.exists(SHARED_ENV) else HERE, ".calls-ledger.jsonl")

# The absolute ceiling MAX_CALLS_PER_DAY can ever effectively reach, no matter what .env or the
# real environment says. Never edited by an agent operating this kit — raising it is a decision
# made by a person opening this file, not one granted in a chat turn. See the docstring above.
HARD_CEILING = 300


class BudgetExceeded(RuntimeError):
    """Raised INSTEAD of making a call. Nothing was sent and nothing was billed."""


def cap():
    """The configured ceiling, clamped to HARD_CEILING. Absence and anything unparseable both land
    on HARD_CEILING too — a typo'd or missing cap must never silently mean "unlimited," which is
    the failure this file exists to prevent."""
    raw = None
    for path in (SHARED_ENV, os.path.join(HERE, ".env")):
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("MAX_CALLS_PER_DAY") and "=" in line:
                raw = line.split("=", 1)[1].strip().strip('"').strip("'")
    raw = os.environ.get("MAX_CALLS_PER_DAY", raw)
    if raw in (None, ""):
        return HARD_CEILING
    try:
        n = int(raw)
    except ValueError:
        print("  !! MAX_CALLS_PER_DAY=%r is not a number — treating it as the hard ceiling (%d)"
              % (raw, HARD_CEILING))
        return HARD_CEILING
    if n <= 0:
        return HARD_CEILING
    return min(n, HARD_CEILING)


def _today():
    return time.strftime("%Y-%m-%d")


def spent_today():
    """How many live calls this key has already made today, across every kit under this root."""
    if not os.path.exists(LEDGER):
        return 0
    day, n = _today(), 0
    with open(LEDGER, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                if json.loads(line).get("day") == day:
                    n += 1
            except ValueError:
                continue          # a torn line is not a reason to stop counting the rest
    return n


def remaining():
    """Never negative — a ledger ahead of the cap reads as 0 left, not as debt."""
    return max(0, cap() - spent_today())


def check(n=1):
    """Refuse BEFORE spending. Raises BudgetExceeded; returns the remaining count."""
    left = remaining()
    if n > left:
        raise BudgetExceeded(
            "daily call cap reached: %d of %d used today across every kit under %s (hard ceiling "
            "%d). This call was NOT made and nothing was billed. Raise MAX_CALLS_PER_DAY in %s up "
            "to the hard ceiling, or edit HARD_CEILING in this file yourself to go further — never "
            "on a chat 'yes' — or wait for the day to roll over."
            % (spent_today(), cap(), ROOT, HARD_CEILING, SHARED_ENV))
    return left


def record(model, kit=None):
    """One line, appended, before the call. O_APPEND so two runs in two terminals interleave
    cleanly rather than truncating each other — the shared key is exactly the case where that
    happens."""
    line = json.dumps({"day": _today(), "ts": int(time.time()),
                       "kit": kit or KIT, "model": model or ""}) + "\n"
    fd = os.open(LEDGER, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fh.write(line)


def plan(n, model):
    """The line a harness prints before a run — always a real number now, never "no cap"."""
    return ("about to make %d live call(s) with model %r — %d of %d used today, %d left "
            "(hard ceiling %d)"
            % (n, model, spent_today(), cap(), remaining(), HARD_CEILING))
