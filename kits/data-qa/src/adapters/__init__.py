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
import http.client
import json
import time
import urllib.error
import urllib.request

from .. import budget


class AdapterError(RuntimeError):
    """`status` is the HTTP code when there was one, else None — so a caller can tell a provider
    being BUSY from a request being WRONG without parsing an error string.

    `transport` is True when the request never got far enough to HAVE a status: a connection reset,
    a socket timeout, a DNS failure, a half-read body. See the TRANSPORT note below — that
    distinction is the difference between a busy provider and a lost document.
    """

    def __init__(self, msg, status=None, transport=False):
        super().__init__(msg)
        self.status = status
        self.transport = transport


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
    # ⚑ A DROPPED CONNECTION IS NOT A FAILED DOCUMENT EITHER.
    #
    # ⚠︎ THE RETRY LOOP IN `complete` ONLY EVER SAW `AdapterError`, AND ONLY EVER LOOKED AT ITS
    # STATUS. A transport failure -- a TLS handshake that timed out, a connection reset, a DNS
    # failure, a body that died mid-read -- raises a bare OSError out of urlopen, which is not an
    # AdapterError at all. It flew straight past four perfectly good backoff attempts and out to
    # the harness, which recorded it as a failed document on a run where the model was right.
    # Two sibling kits each lost documents of a paid run to exactly this before the branch existed.
    #
    # `urllib.error.URLError`, `TimeoutError` and `ConnectionResetError` are all OSError
    # subclasses, and HTTPError -- which IS a URLError -- is caught above, so this cannot swallow a
    # real status. `http.client.HTTPException` covers a body that died mid-read
    # (RemoteDisconnected, IncompleteRead), which returns no completion and is billed for none,
    # exactly like a 503.
    #
    # ⚠︎ THIS BRANCH POSTDATES EVERY PUBLISHED RUN IN THIS KIT AND NO PUBLISHED NUMBER WAS
    # CHANGED TO MATCH IT. A run that lost a document to a transport failure still reports that
    # loss on the page. The fix changes what the NEXT run does; it does not retroactively repair a
    # finished result file, and re-firing one document into one would be the dishonest half of
    # this change rather than the honest half.
    except (OSError, http.client.HTTPException) as e:
        raise AdapterError("transport failure talking to the provider: %s" % e, transport=True)


def openai_compatible(cfg, system, user, max_tokens):
    """Covers every provider that speaks the OpenAI chat-completions shape -- OpenAI itself,
    DeepSeek, Groq, Together, Mistral, xAI, and any local server (Ollama, LM Studio, vLLM).
    BASE_URL is what selects between them, which is why it is in .env rather than in here."""
    body = _post(cfg["base_url"].rstrip("/") + "/chat/completions",
                 {"authorization": "Bearer " + cfg["api_key"]},
                 {"model": cfg["model"], "max_tokens": max_tokens,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]})
    usage = body.get("usage") or {}
    return {"text": body["choices"][0]["message"]["content"],
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
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
            "raw": body}


PROVIDERS = {"openai-compatible": openai_compatible, "anthropic": anthropic}


def complete(cfg, system, user, max_tokens=1024):
    name = cfg.get("provider")
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
            return PROVIDERS[name](cfg, system, user, max_tokens)
        except AdapterError as exc:
            # ⚑ `or exc.transport` IS THE HALF THAT WAS MISSING. A reset connection and a socket
            # timeout have no status to test, so `exc.status not in TRANSIENT` was True for both
            # and the loop re-raised on the first attempt instead of backing off like a 503.
            if not (exc.status in TRANSIENT or exc.transport) or attempt == RETRIES:
                raise
            last = exc
            time.sleep(2 ** attempt)
    raise last
