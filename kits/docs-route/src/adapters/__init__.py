"""SEAM 1 — the model. Swapping provider or model is .env plus the same run again.

THIS IS THE TEACHING POINT OF THE KIT, not the app above it. It makes one claim checkable that
everybody asserts and nobody demonstrates: swapping models is a one-line change, and knowing
whether you should is an eval run.

WHY RAW HTTP FOR EVERY PROVIDER, INCLUDING ANTHROPIC.
Each vendor ships an excellent official SDK, and for a single-vendor application you should use
it. This is not a single-vendor application. A forker runs this on whichever provider they already
hold a key for, so giving one vendor its SDK and the rest a hand-rolled client would bake a
preference into the exact file whose purpose is not having one -- and it would make `pip install`
pull a client for a vendor most forkers will never call. The wire format for a single completion
is small enough that stdlib is honestly the right size, and it keeps the fork test to one install.

Adding a provider is one function and one entry in PROVIDERS. It must return the same shape,
including token counts -- lens 05 publishes them and lens 07 prices them, so a provider that
returns no usage cannot be published.
"""
import json
import time
import urllib.error
import urllib.request

from .. import budget


class AdapterError(RuntimeError):
    """`status` is the HTTP code when there was one, else None — so a caller can tell a provider
    being BUSY from a request being WRONG without parsing an error string."""

    def __init__(self, msg, status=None):
        super().__init__(msg)
        self.status = status


# ⚑ TRANSIENT vs TERMINAL. 429 and 5xx mean "ask again shortly"; 400/401/403/404 mean "asking
# again will fail identically and cost you the same". Retrying the second kind is how a bad key
# turns into a rate-limit ban.
TRANSIENT = {408, 429, 500, 502, 503, 504}
RETRIES = 4


def _post(url, headers, payload, timeout=120):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"content-type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # The body carries the actual reason. Raising the status alone turns "your key is for a
        # different model" into "400", which is the kind of error message that costs an afternoon.
        raise AdapterError("%s %s: %s" % (e.code, e.reason, e.read().decode("utf-8", "replace")),
                           status=e.code)


def openai_compatible(cfg, system, user, max_tokens, thinking=None):
    """Covers every provider that speaks the OpenAI chat-completions shape -- OpenAI itself,
    DeepSeek, Groq, Together, Mistral, xAI, and any local server (Ollama, LM Studio, vLLM).
    BASE_URL is what selects between them, which is why it is in .env rather than in here.

    `thinking` is sent ONLY when the caller passes one, and is passed through verbatim. Omitted,
    the request is byte-identical to what it was before this parameter existed -- so every run
    already recorded stays comparable to a future run that also omits it.
    """
    payload = {"model": cfg["model"], "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system},
                            {"role": "user", "content": user}]}
    # ⚑ NOT A DEFAULT, AND NOT GUESSED AT. See the note on `token_details` below for why this knob
    # was deliberately absent until now, and `complete()` for the shape the docs confirm.
    if thinking is not None:
        payload["thinking"] = thinking
    body = _post(cfg["base_url"].rstrip("/") + "/chat/completions",
                 {"authorization": "Bearer " + cfg["api_key"]}, payload)
    usage = body.get("usage") or {}
    choice = body["choices"][0]
    return {"text": choice["message"]["content"],
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            # ⚑ THE PROVIDER SAYS WHY IT STOPPED — RECORD IT. 2026-08-05: run r001 lost 36 of 42
            # briefs to replies that did not parse, and diagnosing it meant noticing that every
            # failure's output_tokens was 4000 against a cap of 4000 while every success was
            # strictly below. The provider had said "length" in this field the whole time and
            # nothing read it, so a one-word answer was reconstructed from arithmetic.
            "finish_reason": choice.get("finish_reason"),
            # ⚑ AND HOW THE OUTPUT BUDGET WAS ACTUALLY SPENT — added after run r002, 2026-08-05.
            # Raising the ceiling 4000 -> 8000 took the yield from 6 briefs to 27, so the cap was
            # real; but all 15 remaining failures came back at exactly 8000 with finish_reason
            # "length", and ELEVEN of them returned zero characters of visible text. A reply that
            # spends 8,000 output tokens and returns nothing has spent them somewhere the `content`
            # field does not show, and on a reasoning model that somewhere is reasoning.
            #
            # ⚠︎ THAT IS STILL AN INFERENCE, AND THIS FIELD IS HOW IT STOPS BEING ONE. The
            # OpenAI-compatible shape reports the split in usage.completion_tokens_details
            # (`reasoning_tokens`), so the next run MEASURES it instead of arguing from a silence.
            # Recorded as whatever the provider sends, with no shape assumed: a provider that omits
            # it yields None, which is an honest absence rather than a fabricated zero.
            #
            # ⚠︎ THE REQUEST-SIDE KNOB WAS WITHHELD UNTIL BOTH ITS PRECONDITIONS WERE MET, AND ON
            # 2026-08-05 THEY WERE. This note used to end "Measure first, then send a parameter the
            # docs confirm exists." Both halves are now done, in that order:
            #
            #   MEASURED — run r003 carried this field. Across its 13 failures the reasoning share
            #   of the 8,000-token ceiling ran 78% to 100%, median 100%, and 8 of the 13 spent the
            #   whole budget reasoning and returned zero visible characters. The inference above is
            #   now a number, and reasoning is confirmed as the binding constraint.
            #
            #   CONFIRMED — DeepSeek's API documents `thinking` as an object that turns the
            #   reasoning pass on or off, and notes it DEFAULTS TO ENABLED on Flash. Every run this
            #   kit has made carried a reasoning pass nobody asked for. The shape is taken from the
            #   vendor's own request example, `{"type": "disabled"}`, and is not constructed here.
            #
            # It is still not a default: `thinking` is None unless a caller passes one, so an
            # untouched run is byte-identical to every run already recorded.
            "token_details": (usage.get("completion_tokens_details")
                              or usage.get("output_tokens_details")),
            "raw": body}


def anthropic(cfg, system, user, max_tokens):
    """Anthropic's Messages API. Three things differ from the shape above and all three bite:
    the key rides `x-api-key` rather than a bearer header, `anthropic-version` is required, and
    the system prompt is its own top-level field instead of a message with role 'system'."""
    body = _post((cfg.get("base_url") or "https://api.anthropic.com").rstrip("/") + "/v1/messages",
                 {"x-api-key": cfg["api_key"], "anthropic-version": "2023-06-01"},
                 {"model": cfg["model"], "max_tokens": max_tokens, "system": system,
                  "messages": [{"role": "user", "content": user}]})
    usage = body.get("usage") or {}
    text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
    return {"text": text,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            # Anthropic spells the same fact "max_tokens" rather than "length". Normalised here so
            # a caller can test one value across both providers, which is this module's whole job.
            "finish_reason": {"max_tokens": "length"}.get(body.get("stop_reason"),
                                                          body.get("stop_reason")),
            "raw": body}


PROVIDERS = {"openai-compatible": openai_compatible, "anthropic": anthropic}


# The one shape this kit will send, taken verbatim from DeepSeek's own request example for
# deepseek-v4-flash. Named rather than spelled inline at the call site so there is exactly one
# place a provider's documented field lives, and so a run record can say which one it used.
THINKING_OFF = {"type": "disabled"}


def complete(cfg, system, user, max_tokens=1024, thinking=None):
    """`thinking` is passed through to the provider untouched, or omitted entirely when None.

    ⚠︎ PROVIDER-SPECIFIC, AND NOT SILENTLY SWALLOWED. Only the OpenAI-compatible path accepts it,
    because that is the only shape whose documentation this kit has read. Sending it to Anthropic
    would be inventing a field on a provider nobody checked — so it is refused loudly rather than
    dropped, which would leave a run believing it had disabled something it had not.
    """
    name = cfg.get("provider")
    if thinking is not None and name != "openai-compatible":
        raise AdapterError(
            "thinking=%r was requested but provider %r has no documented field for it in this "
            "kit. Dropping it silently would let a run record claim a setting it never sent."
            % (thinking, name))
    if name not in PROVIDERS:
        raise AdapterError("unknown PROVIDER %r -- known: %s. Add one in src/adapters/__init__.py"
                           % (name, ", ".join(sorted(PROVIDERS))))
    if not cfg.get("api_key"):
        raise AdapterError("no API_KEY set. Copy .env.example to .env -- or run the offline path, "
                           "which needs no key and renders the recorded results.")
    if not cfg.get("model"):
        raise AdapterError("no MODEL set. There is no default on purpose: a kit that picks a model "
                           "for you has picked your bill and your latency too.")
    # ⚑ A BUSY PROVIDER IS NOT A FAILED DOCUMENT — added 2026-08-03, mid-run, after a live
    # 503 "Service is too busy" dropped a document from a paid run of 57.
    #
    # ⚠︎ THIS DOES NOT WEAKEN "RUN ONCE". Run-once is a claim about how many times the TASK was
    # attempted and published, not about how many TCP requests it took to get one answer. A 503
    # returns no completion, so nothing was extracted and nothing was billed; asking again is
    # finishing the first attempt, not taking a second one. What would break the claim is
    # re-running a document that already answered, and that is not what happens here.
    #
    # Bounded and backed off, because the failure mode on the other side is a provider under load:
    # 1s, 2s, 4s, 8s, then give up and let the caller RECORD the failure as it does today.
    # ⚑ THE DAILY CAP IS CHECKED HERE, NOT IN THE RUN HARNESS — added 2026-08-04.
    #
    # One key funds every kit, and this is the only line all of them go through: the eval harness,
    # the local app, a screenshot script, and whatever a forker writes next. Putting the guard in
    # `evals/run.py` would cap the run that already prints what it is about to spend and leave
    # every other caller uncapped — including the app, which spends one call per click with
    # nothing counting them at all. A second place to remember is a place to forget.
    #
    # It is checked ONCE per completion rather than once per HTTP attempt, because a retried 503
    # returns no completion and is billed for none: charging the budget for it would make a busy
    # provider look like spending, which is exactly the confusion the retry comment above settles.
    budget.check(1)
    budget.record(cfg.get("model"))

    last = None
    for attempt in range(RETRIES + 1):
        try:
            if thinking is not None:
                return PROVIDERS[name](cfg, system, user, max_tokens, thinking=thinking)
            return PROVIDERS[name](cfg, system, user, max_tokens)
        except AdapterError as exc:
            if exc.status not in TRANSIENT or attempt == RETRIES:
                raise
            last = exc
            time.sleep(2 ** attempt)
    raise last
