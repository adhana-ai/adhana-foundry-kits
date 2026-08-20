"""Read .env. No dependency, and no key ever leaves this machine.

python-dotenv is a fine library and this is eight lines, so the kit does not ask a forker to
install one to read five variables. The file is gitignored from the first commit; this repo has
never held a credential and is not able to.

⚑ CONFIGURE ONCE, NOT ONCE PER KIT — added 2026-08-03.

A kit used to read only its own `.env`, which is fine when there is one kit and absurd when there
are a hundred: every new use case meant copying a provider, a base URL, a key and a model into a
fresh file before it could do anything. The setup cost grew with the number of kits, and the whole
premise of a kit is that the next one is cheap.

So there are two places now, and the kit-local one is the OVERRIDE rather than the source:

    <repo>/.env            the shared connection. Set it once. Every kit inherits it, including
                           every kit that does not exist yet.
    <repo>/kits/<slug>/.env  optional, per-kit. Only for pointing ONE kit at a different model --
                           a tier comparison, a local server, a provider you are trying out.
    real environment       still wins over both, unchanged, so CI and containers override without
                           editing any file.

⚠︎ NEITHER FILE IS REQUIRED AND A MISSING ONE IS NOT AN ERROR. A forker who clones a single kit
has no repo root above it and must still get a working kit -- so the shared path is read when it is
there and ignored when it is not. That is what keeps each kit independently forkable, which is the
point of shipping them at all.
"""
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(HERE, ".env")
# kits/<slug> -> kits -> the repo root. Resolved, not guessed, so a symlinked checkout behaves.
SHARED_ENV = os.path.join(os.path.dirname(os.path.dirname(HERE)), ".env")

VARS = ("PROVIDER", "BASE_URL", "API_KEY", "MODEL", "EMBED_MODEL")


def _read(path):
    """One .env into a dict. A missing file is {} — absence is a normal state here, not a failure."""
    out = {}
    if not os.path.exists(path):
        return out
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load():
    """Shared, then this kit's own, then the real environment. Last writer wins, and the order is
    the point: the thing that is most specific to what you are doing right now wins."""
    cfg = {}
    cfg.update(_read(SHARED_ENV))
    # ⚠︎ MERGED KEY BY KEY, NOT FILE BY FILE. A kit-local .env holding only MODEL overrides the
    # model and keeps the shared provider, base URL and key — which is the common case by far:
    # "same account, different model". Replacing the whole config would silently blank the key and
    # produce "no API_KEY configured" on a kit whose .env looks perfectly complete.
    cfg.update(_read(ENV))
    cfg.update({k: v for k, v in os.environ.items() if k in VARS})
    return {"provider": cfg.get("PROVIDER", "openai-compatible"),
            "base_url": cfg.get("BASE_URL", ""),
            "api_key": cfg.get("API_KEY", ""),
            "model": cfg.get("MODEL", ""),
            "embed_model": cfg.get("EMBED_MODEL", "")}


def sources():
    """Which files actually contributed, for a UI or a startup line to print. Never values —
    'where is this key coming from' must be answerable without anyone reading a key aloud."""
    return [("shared", SHARED_ENV, os.path.exists(SHARED_ENV)),
            ("kit", ENV, os.path.exists(ENV))]


def has_key(cfg=None):
    """The kit must render real recorded results with no key configured. Everything that needs one
    checks here first and says so plainly rather than failing at the HTTP layer."""
    return bool((cfg or load()).get("api_key"))


WRITABLE = ("PROVIDER", "BASE_URL", "API_KEY", "MODEL", "EMBED_MODEL")


def save(values):
    """Write the named variables into .env, preserving every other line, and lock the file to 0600.

    WHY THE APP WRITES THIS FILE AT ALL. Editing .env by hand is the step that goes wrong, and it
    goes wrong invisibly: a heredoc that pastes placeholder text, an editor that never saved, a
    key with a trailing space. All three produce a kit that starts cleanly and then says "no
    API_KEY configured", which reads as the kit being broken rather than the file being empty.
    app.py already knows the difference — has_key() is a boolean it prints at startup — so the
    place to fix it is the place that already detects it.

    IT REWRITES LINES, IT DOES NOT REGENERATE THE FILE. .env.example ships with comments explaining
    each variable and a forker may have added their own; a writer that emits five clean lines would
    delete all of that on first use. A key whose variable is absent is appended at the end.

    0600 BEFORE THE WRITE, NOT AFTER. os.open with the mode set means the file never exists, even
    for an instant, at the default umask — which on a shared machine is the whole window that
    matters. Returns the path so a caller can tell the operator exactly what changed.
    """
    values = {k: v for k, v in values.items() if k in WRITABLE and v is not None}
    lines = open(ENV, encoding="utf-8").read().splitlines() if os.path.exists(ENV) else []
    seen = set()
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k = s.split("=", 1)[0].strip()
        if k in values:
            lines[i] = "%s=%s" % (k, values[k])
            seen.add(k)
    for k, v in values.items():
        if k not in seen:
            lines.append("%s=%s" % (k, v))

    fd = os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip("\n") + "\n")
    os.chmod(ENV, 0o600)                        # in case the file already existed, looser
    return ENV
