"""Assemble the pre-load check prompt. One prompt per check sheet, all ten fields in it.

⚠︎ THE GUARDED FIELD OF THIS KIT IS `verdict`, AND IT IS A FOUR-CHECK LOOKUP WITH A STOPPING
ORDER. It is stated in full, and THE MATRIX ITSELF IS SENT WITH IT, because a compatibility
decision is a lookup and a model cannot look up a table it has never been shown. The alternative --
letting the model answer from whatever it knows about chemistry -- is exactly the failure this kit
exists to measure: the shipped matrix is the authority for this decision, and a reading that
disagrees with it is wrong here even where the chemistry is arguable.

Four things are spelled out that a model left to its own reading gets wrong:

  1. THE CERTIFICATE GOVERNS, NOT THE LOG LINE. `wash_performed` is the tank log's own claim about
     what was done; `wash_certified_for` is what a certificate actually covers. When they disagree
     the tank is credited with the CERTIFICATE's regime -- and on this corpus they disagree often,
     with the log always claiming the more thorough one.
  2. A PREDECESSOR BAN IS NOT A CLEANING PROBLEM. methanol before a food-grade load is water-
     miscible, non-reactive and trivially rinsed out, and it is banned anyway. Cleaning does not
     cure a ban, and no cleaning record makes a banned predecessor acceptable.
  3. FOOD GRADE AND HIGH PURITY READ TWO CARGOES BACK. An entirely innocuous prior cargo can sit
     in front of a banned one, and for those two grades the one behind still disqualifies the tank.
  4. THE INSPECTOR'S NOTE IS A FIELD TO COPY, NOT EVIDENCE. A note that sounds worried does not
     make a compatible pair incompatible, and a note that sounds relaxed does not clear a tank.
     Only the matrix and the certificate decide.

⚑ ONE CALL PER SHEET, NOT ONE PER FIELD -- same reasoning as every sibling extraction kit.

⚠︎ AND THE VERDICT IS A PROPOSAL. The prompt says so, the UI says so and the kit's own pages say
so: nothing here authorises a load. A qualified person does, against the product's safety data
sheet and the tank's real cleaning record.
"""
import json

from .matrix import M, WASH_LADDER

SYSTEM = (
    "You read a bulk-tank PRE-LOAD COMPATIBILITY CHECK SHEET and extract structured fields from "
    "it. You return JSON and nothing else.\n"
    "\n"
    "You are PROPOSING a verdict for a qualified person to authorise. You never authorise a load, "
    "and your verdict is not a substitute for the incoming product's safety data sheet or for a "
    "competent person's assessment.\n"
    "\n"
    "RULES, in order of importance:\n"
    "1. If the sheet does not state a field, return null for it. Do not infer it and do not use "
    "what you know about the world.\n"
    "2. `verdict` is decided ONLY by the COMPATIBILITY MATRIX given below, applied to five values "
    "-- incoming_product, incoming_grade, prior_cargo, two_back_cargo and wash_certified_for. "
    "Work through these four checks IN ORDER and STOP at the first one that fires:\n"
    "   a. NOT KNOWN. If the sheet does not record a prior cargo, or if the incoming product or "
    "either recorded cargo is not listed in the matrix, answer 'undetermined'. Never guess a class "
    "for a cargo the matrix does not carry.\n"
    "   b. REACTIVE PAIR. If the prior cargo's class and the incoming product's class are listed "
    "as a reactive pair, answer 'refuse'. The pair is symmetric, and no cleaning regime clears it.\n"
    "   c. RESTRICTED PREDECESSOR. Read the look-back depth for the incoming grade. Technical "
    "grade reads the prior cargo only. Food grade and high purity read the prior cargo AND the "
    "two-back cargo. If ANY cargo in that chain is banned for this grade -- by its class or by "
    "name -- answer 'refuse'. A BAN IS NOT A CLEANING PROBLEM: cleaning does not cure it, however "
    "thorough the certificate is.\n"
    "   d. MINIMUM CERTIFIED WASH. Take the minimum wash for the PRIOR cargo's class, then raise "
    "it one rung if the incoming grade is food_grade or high_purity (capped at the top of the "
    "ladder). Compare it against what the CERTIFICATE names. Meets or exceeds it: answer "
    "'accept'. Falls short: answer 'clean_then_load'.\n"
    "3. THE CERTIFICATE GOVERNS, NOT THE TANK LOG. `wash_performed` is what the log claims was "
    "done and it is NEVER an input to the verdict. `wash_certified_for` is what a certificate "
    "actually covers, and it is the only wash the tank is credited with. When the two disagree, "
    "use the certificate. A tank with no certificate on file is credited with NO wash at all, "
    "whatever its log says.\n"
    "4. THE INSPECTOR'S NOTE IS A FIELD TO COPY, NOT EVIDENCE ABOUT COMPATIBILITY. A note that "
    "sounds worried does NOT make a compatible pair incompatible, and a note that sounds relaxed "
    "does NOT clear a tank. The matrix and the certificate decide; the note is one person's remark "
    "and may disagree with them.\n"
    "5. Copy cargo and product names verbatim from the sheet, in the lower case it states them. "
    "Where the sheet says the prior cargo is 'not recorded', return null for prior_cargo rather "
    "than the words. Where it says the tank was recertified and has no cargo before the prior "
    "one, return null for two_back_cargo.\n"
    "6. Use the exact allowed value for a field that lists them.\n"
    "7. Return every field named in the schema, even when the answer is null."
)


def matrix_block(m=None):
    """The matrix, rendered for the prompt out of data/matrix.json.

    ⚑ RENDERED, NEVER RETYPED. A second prose copy of the table inside this module is a copy that
    drifts from the file the corpus generator and the scorer both read -- which would make the
    model's instructions and the gold labels disagree about the same lookup, silently, and the
    disagreement would score as a model failure.
    """
    m = m or M
    lines = ["COMPATIBILITY MATRIX (the authority for `verdict`; this is an ILLUSTRATIVE matrix "
             "shipped with this kit, not an industry chart)", "",
             "CARGO CLASSES"]
    for cls in sorted(m["classes"]):
        lines.append("  %-12s %s" % (cls + ":", ", ".join(m["classes"][cls])))
    lines += ["", "REACTIVE PAIRS -- refuse outright, symmetric, no cleaning clears them"]
    for p in m["reactive_pairs"]:
        lines.append("  %s + %s" % (p["a"], p["b"]))
    lines += ["", "LOOK-BACK DEPTH, by incoming grade"]
    for g in ("technical", "food_grade", "high_purity"):
        n = m["lookback"][g]
        lines.append("  %-12s %d cargo%s back (%s)"
                     % (g + ":", n, "" if n == 1 else "es",
                        "the prior cargo only" if n == 1
                        else "the prior cargo AND the cargo before it"))
    lines += ["", "BANNED PREDECESSORS -- refuse; cleaning does not cure a ban"]
    for g in ("technical", "food_grade", "high_purity"):
        cls = m["banned_predecessor_classes"].get(g) or []
        names = m["banned_predecessor_cargoes"].get(g) or []
        bits = []
        if cls:
            bits.append("any cargo of class " + ", ".join(cls))
        if names:
            bits.append("plus by name: " + ", ".join(names))
        lines.append("  %-12s %s" % (g + ":", "; ".join(bits) if bits else "none"))
    lines += ["", "WASH LADDER, weakest to strongest",
              "  " + " < ".join(WASH_LADDER), "",
              "MINIMUM CERTIFIED WASH, by the PRIOR cargo's class (then raise one rung for a "
              "food_grade or high_purity load, capped at the top of the ladder)"]
    for cls in sorted(m["minimum_wash"]):
        lines.append("  %-12s %s" % (cls + ":", m["minimum_wash"][cls]))
    return "\n".join(lines)


MATRIX_TEXT = matrix_block()


def field_schema(fields):
    out = []
    for f in fields:
        line = "- %s (%s)" % (f["name"], f["type"])
        if f.get("values"):
            line += " one of: %s" % ", ".join(f["values"])
        line += " -- %s" % f.get("hint", "")
        out.append(line)
    return "\n".join(out)


def build(doc_text, secs, fields, selector):
    names = [f["name"] for f in fields]
    wanted, seen = [], set()
    for name in names:
        for s in selector.for_field(secs, name):
            if s["start"] not in seen:
                seen.add(s["start"])
                wanted.append(s)
    wanted.sort(key=lambda s: s["start"])
    context = "\n\n".join(s["text"].strip() for s in wanted)

    schema = field_schema(fields)
    user = ("%s\n\n"
            "Extract these fields:\n%s\n\n"
            "Return a JSON object with exactly these keys: %s\n"
            "Use null for any field the sheet does not state.\n\n"
            "PRE-LOAD CHECK SHEET\n--------------------\n%s\n"
            % (MATRIX_TEXT, schema, ", ".join(names), context))

    parts = [
        {"name": "system", "text": SYSTEM},
        {"name": "compatibility matrix", "text": MATRIX_TEXT},
        {"name": "field schema", "text": schema},
        {"name": "check sheet sections", "text": context},
    ]
    return ([{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user}],
            parts,
            [s["name"] for s in wanted])


def parse(raw, fields):
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        s = s.rsplit("```", 1)[0]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return {}
    try:
        obj = json.loads(s[i:j + 1])
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    return {f["name"]: obj.get(f["name"]) for f in fields}
