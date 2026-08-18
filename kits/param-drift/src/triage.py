"""SEAM 1 -- the AI layer. Loads the corpus, builds one prompt per parameter, calls the model,
parses the reply, and always computes the deterministic corrected value alongside it -- whether or
not anything flagged the parameter. Swapping provider or model is .env plus the same run again.
"""
import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")

from src import aggregate as A                       # noqa: E402
from src import formulas as F                          # noqa: E402
from src import prompt as P                              # noqa: E402


def load_parameters():
    with open(os.path.join(DATA, "parameters.jsonl"), encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def load_labels():
    with open(os.path.join(DATA, "labelled.jsonl"), encoding="utf-8") as f:
        return [json.loads(l) for l in f]


def parameters_by_id():
    return {p["parameter_id"]: p for p in load_parameters()}


def labels_by_id():
    return {l["parameter_id"]: l for l in load_labels()}


def windows():
    """{parameter_id: [reading, ...]}, cut once."""
    return A.cut(A.load_readings())


def check(cfg, param, window, complete=None, thinking=None):
    """One parameter, one call (unless `complete` is supplied -- a stub for --stub/--dry-run).

    Always returns the floor's verdict and the deterministic proposed value alongside whatever the
    model said, so a caller never has to make a second pass to get the free comparison.
    """
    from src.adapters import complete as real_complete
    do_complete = complete or real_complete

    fx = A.facts(window)
    messages, parts = P.build(param, window, fx)
    system, user = messages[0]["content"], messages[1]["content"]
    got = do_complete(cfg, system, user, max_tokens=P.MAX_TOKENS, **({"thinking": thinking}
                                                                     if thinking is not None else {}))
    parsed = P.parse(got["text"])

    floor_verdict, floor_reasons = F.decide_floor(param["category"], param["configured_value"],
                                                  fx["stats"])
    proposed_value = F.corrected_value(param["category"], fx["stats"])

    return {
        "parameter_id": param["parameter_id"], "category": param["category"],
        "verdict": parsed["verdict"], "reason": parsed["reason"],
        "replied": parsed["verdict"] is not None,
        "floor_verdict": floor_verdict, "floor_reasons": floor_reasons,
        "proposed_value": proposed_value,
        "deviation": F.deviation(param["category"], param["configured_value"], fx["stats"]),
        "facts": fx,
        "parts": parts, "prompt": user,
        "raw_text": got.get("text", ""), "finish_reason": got.get("finish_reason"),
        "input_tokens": got.get("input_tokens"), "output_tokens": got.get("output_tokens"),
        "reasoning_chars": got.get("reasoning_chars"),
    }
