"""The two baselines a routing kit has to publish, and neither of them calls a model.

⚑ THE FIRST ROW OF THE BOARD IS ALWAYS THE NULL, NEVER A FOOTNOTE — the kit standard is explicit,
and on a balanced 3-class set the arithmetic is unforgiving: answering the same queue every time
scores 33.3%. Put that first and a model's 78% reads as what it is. Bury it and 78% reads as good.

⚑ AND THE SECOND BASELINE IS THE ONE THAT MAKES THIS KIT WORTH PUBLISHING: A KEYWORD CLASSIFIER.
Thirty lines of if-statements over words the document already contains. It costs nothing, it runs
in microseconds, and on documents whose `ACTION:` line literally reads "Final rule." it is going to
be right. The question an AI product manager actually has to answer is not "is the model good" but
"is the model worth its bill against the boring thing" — and this kit answers it with a number
instead of an opinion, on the same 120 documents, scored by the same scorer.

⚠︎ IF THE KEYWORD BASELINE WINS, THAT IS THE FINDING AND IT GETS PUBLISHED. This file exists to
make that outcome possible to discover. A kit whose baselines are chosen so the model beats them
is an advert with a methodology section.

⚠︎ THE KEYWORD RULES WERE WRITTEN FROM THE TAXONOMY, NOT FROM THE CORPUS. They name the phrases a
person would guess before seeing the data — "final rule", "proposed rule", "notice of". Tuning
them against these 120 documents until they beat the model, or until they lost to it, would make
the comparison a measurement of my tuning. They were written once and not revised after scoring.
"""
import re

from src import taxonomy as TX

NULL_QUEUE = TX.ORDER[0]


def null_score(n_per_class):
    """What answering the majority class every time earns. On a balanced set that is 1/len(ORDER),
    and stating it as arithmetic rather than as a measured run keeps it honest when the set is
    rebuilt at a different size."""
    total = sum(n_per_class.values()) or 1
    return round(100.0 * max(n_per_class.values(), default=0) / total, 2)


def null_predict(_doc_text):
    """The null router: the same queue, every time, whatever it reads."""
    return {"queue": NULL_QUEUE, "confidence": None, "state": "ok", "rule": "always-%s" % NULL_QUEUE}


# Ordered, and the order IS the rule: "proposed rule" must be tested before "rule", because every
# proposed rule contains the word rule. A dict would have made this ordering invisible and the
# first refactor would have broken it silently.
KEYWORDS = [
    ("proposed", [r"\bproposed rule\b", r"\bnotice of proposed rulemaking\b", r"\bNPRM\b",
                  r"\bwe propose\b", r"\bis proposing\b", r"\bproposes to\b",
                  r"\brequest for comment", r"\bcomments? must be received\b"]),
    ("rule", [r"\bfinal rule\b", r"\binterim final rule\b", r"\bdirect final rule\b",
              r"\bthis rule amends\b", r"\beffective date\b.*\brule\b", r"\bis adopting\b"]),
    ("notice", [r"\bnotice of\b", r"\bmeeting\b", r"\bthis notice announces\b",
                r"\bapplication\b", r"\bavailability\b", r"\bsolicitation\b"]),
]

_COMPILED = [(q, [re.compile(p, re.I) for p in pats]) for q, pats in KEYWORDS]


def keyword_predict(doc_text):
    """The boring router. Returns the same shape a model reply parses into, so `evals/score.py`
    scores it through exactly one code path — a baseline scored by a second scorer is two
    measurements being differenced."""
    text = doc_text or ""
    for queue, patterns in _COMPILED:
        for pat in patterns:
            if pat.search(text):
                return {"queue": queue, "confidence": None, "state": "ok",
                        "rule": pat.pattern}
    # ⚑ NO MATCH IS AN ABSTENTION, NOT A GUESS. Falling back to the majority class would quietly
    # fold the null baseline into this one and make the keyword rules look better than they are.
    return {"queue": None, "confidence": None, "state": "abstained", "rule": "no keyword matched"}


BASELINES = {
    "null": (null_predict, "answer %s every time" % TX.label_of(NULL_QUEUE)),
    "keyword": (keyword_predict, "%d regular expressions over the document text"
                % sum(len(p) for _, p in KEYWORDS)),
}
