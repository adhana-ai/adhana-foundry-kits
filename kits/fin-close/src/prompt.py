"""Assemble the one prompt this kit sends, and parse the one reply it gets back.

ONE CALL PER CLOSE CYCLE, NOT PER CHECK. All four checks are decided in a single call that receives
the drafted journal entry, the reconciliation worksheet numbers, and the recurring entry's basis
document together. The basis document is the expensive token payload here — it is prose, not a
lookup table — so batching the four checks into one call is what keeps this kit from re-sending the
same basis document four times for four separate answers.

⚠︎ THE MODEL IS ASKED FOR A VERDICT AND A CITATION, AND THE CITATION IS NOT DECORATION. A verdict on
its own cannot be checked by a reader — "defect" with no fact or sentence beside it is an assertion.
Requiring the model to name the value it compared against also does real work on the model's side:
it is harder to confabulate a violation, or a clean bill, without producing the number that decides
it.

⚠︎ THE THIRD VERDICT IS THE ONE THAT MATTERS MOST. `unverifiable` exists because the basis document
is sometimes silent on the exact fact a check needs — a recurring entry whose calculation method was
never written down, an account whose reconciliation materiality band was never documented. A model
that guesses `clean` there lets a silently-changed basis or an unexplained residual through with a
tick on it; a model that guesses `defect` sends a preparer chasing a violation of a rule that was
never written. Unverifiable is never a pass, and it is never a silent fail either — it is its own
answer, same discipline this kit's guardrail states about materiality: an unexplained residual above
threshold is never characterized as immaterial, and an undocumented threshold is never characterized
as anything at all.

⚠︎ THIS KIT NEVER DRAFTS A POSTING OR A CLEARANCE. Every check below produces a verdict for a
preparer/reviewer to act on — it never marks an entry approved, never clears a reconciling item, and
never speaks for the reviewer. See src/close.py's module docstring for where that boundary is
enforced in code, not just in this prompt.
"""
import json

CHECKS = ("account", "amount", "basis", "residual")

VERDICTS = ("clean", "defect", "unverifiable")

VERDICT_MEANINGS = {
    "clean": {
        "means": "The drafted value satisfies what the basis document states for this check.",
        "costs": "Wrong here is the expensive direction: a FALSE CLEAN ships a silently-changed "
                 "basis, a misposted account, or an unexplained residual with a tick on it.",
    },
    "defect": {
        "means": "The basis document states a fact for this check, and the drafted value "
                 "violates it.",
        "costs": "A false alarm sends a clean close cycle back for rework, and a preparer who "
                 "stops trusting the queue after the second one.",
    },
    "unverifiable": {
        "means": "The basis document never states the fact this check needs — no documented "
                 "calculation method, or no documented materiality band. There is nothing to "
                 "compare against.",
        "costs": "Called clean, a genuinely unchecked entry disappears — nobody re-checks a line "
                 "the pack said was fine. Called defect, a preparer is sent chasing a violation "
                 "of a rule that was never written.",
    },
}

CHECK_MEANINGS = {
    "account": "the drafted entry's posting account against the account the basis document "
               "states for this recurring template",
    "amount": "the drafted entry's amount against the prior-period APPROVED amount the basis "
              "document states, allowing normal fluctuation and nothing more",
    "basis": "the drafted entry's stated calculation method against the method the basis "
             "document describes for this recurring template",
    "residual": "the reconciliation residual (GL balance less supporting schedule) against the "
                "materiality band the basis document states for this account",
}

_DEFS = "".join("  %-14s %s\n" % (name, VERDICT_MEANINGS[name]["means"])
                for name in VERDICTS)
_CHECKS_TXT = "".join("  %-10s %s\n" % (c, CHECK_MEANINGS[c]) for c in CHECKS)

SYSTEM = (
    "You draft a review of one month-end close cycle: a recurring journal entry and its account "
    "reconciliation, checked against the recurring entry's documented basis. You are given the "
    "drafted entry, the reconciliation worksheet numbers, and the basis document's full text. For "
    "each of the four checks below, decide which of exactly three verdicts applies, using ONLY the "
    "basis document -- never outside knowledge, never a typical value for a fact like this.\n\n"
    "THE FOUR CHECKS\n" + _CHECKS_TXT + "\n"
    "THE THREE VERDICTS\n" + _DEFS + "\n"
    "Read the basis document for the fact each check needs. If it states the fact, compare the "
    "drafted value against it and answer clean or defect. If the basis document is silent on the "
    "fact a check needs, the answer is unverifiable -- do not infer a typical figure and do not "
    "default to clean because nothing looked wrong. Silence is not a pass, and an unexplained "
    "residual above a documented materiality band is never clean.\n\n"
    "For clean and defect, cite the exact sentence or clause from the basis document you relied "
    "on, verbatim, plus the expected value it states and the drafted entry's actual value. For "
    "unverifiable the citation MUST be an empty string and expected MUST be null -- do not offer "
    "the nearest clause, because a citation that does not decide the check reads as evidence and "
    "is not.\n\n"
    "You are drafting a review for a preparer and reviewer to act on. You never post, approve or "
    "clear anything -- you only produce verdicts and citations for the sign-off chain."
)

DEFAULT_PROMPT = "v1"
SYSTEMS = {"v1": SYSTEM}


def _cycle_block(cycle):
    return (
        "CLOSE CYCLE %s (recurring template %s, period %s)\n"
        "Drafted entry: account %s (%s), amount $%.2f\n"
        "Drafted basis note: %s\n"
        "Reconciliation worksheet: GL balance $%.2f, supporting balance $%.2f, residual $%.2f\n"
        % (cycle["close_id"], cycle["rje_id"], cycle["period"],
           cycle["je_account_id"], cycle["je_account_name"], cycle["je_amount"],
           cycle["je_basis_note"],
           cycle["recon_gl_balance"], cycle["recon_supporting_balance"], cycle["recon_residual"])
    )


def build(cycle, basis_text, prompt=DEFAULT_PROMPT):
    """Return (messages, parts). `parts` is the decomposition the LLM lens publishes — every
    part's text occurs verbatim in what is actually sent, in this order."""
    if prompt not in SYSTEMS:
        raise ValueError("unknown prompt %r -- known: %s" % (prompt, ", ".join(sorted(SYSTEMS))))
    system = SYSTEMS[prompt]
    cycle_block = _cycle_block(cycle)
    user = (
        "Check the close cycle below against its recurring template's basis document.\n\n"
        "Return a JSON object with one key, \"checks\", a list with exactly four entries, one "
        "per check in this order: %s. Each entry: {\"check\": <name>, "
        "\"verdict\": <one of: %s>, \"citation\": <verbatim clause from the basis document, or "
        "\"\">, \"expected\": <the value the basis document states, or null>, "
        "\"actual\": <the drafted entry's corresponding value>}.\n\n"
        "%s\nBASIS DOCUMENT\n--------------\n%s\n" % (", ".join(CHECKS), ", ".join(VERDICTS),
                                                       cycle_block, basis_text)
    )
    parts = [
        {"name": "system", "text": system},
        {"name": "cycle", "text": cycle_block},
        {"name": "basis", "text": basis_text},
    ]
    return ([{"role": "system", "content": system}, {"role": "user", "content": user}], parts)


def parse(raw):
    """Pull the four-check verdict list out of a model reply, tolerantly but never creatively.

    A reply that does not parse yields an all-None result — read as "this call produced no
    answer", never as evidence about the close cycle — never a regex fallback that scrapes
    plausible-looking verdicts out of raw text. That would silently turn a broken call into a
    mediocre checker.
    """
    out = {c: None for c in CHECKS}
    if not raw:
        return out
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return out
    try:
        obj = json.loads(text[start:end + 1])
    except ValueError:
        return out
    for entry in (obj.get("checks") or []):
        if not isinstance(entry, dict):
            continue
        check = str(entry.get("check", "")).strip().lower().replace(" ", "_").replace("-", "_")
        if check not in CHECKS:
            continue
        verdict = str(entry.get("verdict", "")).strip().lower().replace(" ", "_").replace("-", "_")
        if verdict not in VERDICTS:
            continue
        out[check] = {"verdict": verdict, "citation": str(entry.get("citation", "") or ""),
                      "expected": entry.get("expected"), "actual": entry.get("actual")}
    return out
