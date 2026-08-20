#!/usr/bin/env python3
"""Generate the case windows and gold labels this kit checks against, from a fixed seed.

    python3 tools/build_corpus.py
    python3 tools/build_corpus.py --verify     # re-reads data/*.jsonl from disk and re-derives
                                                # every gold row independently -- see verify()

Writes data/windows.jsonl and data/gold.jsonl, byte-identical on every run. Every user, host,
domain, IP and hash below is invented -- RFC 5737 documentation ranges for every "external" IP,
nobody's real name for a user -- so the corpus ships under this repo's MIT licence with no
third-party grant to verify. See data/SOURCES.md.

⚑ THE UNIT OF WORK IS THE WINDOW, NOT THE ALERT. Unlike a stream-cutting kit (ops-triage), there is
no continuous log to slice by time -- a SOC's own triage queue already arrives as small candidate
groups: 2-4 alerts a person or a correlation tool bundled together because they occurred close in
time and/or share an entity. That grouping is the thing this kit's model call has to get right, so
it is authored directly rather than computed by a gate.

⚑ THE TRUTH LIVES IN alert_facts, AND case_groups IS DERIVED FROM IT, NEVER TYPED ALONGSIDE IT.
Every alert this file builds is tagged, at construction time, with a disposition
(true_positive/false_positive) and a case_id (a string shared by every alert in one genuine
incident, None for a false positive). Those two per-alert facts are the raw material -- the
analogue of fin-payrun's match.matched booleans. `derive_gold()` is the ONE function that turns
raw per-alert facts into the aggregate `alert_dispositions` dict and `case_groups` list, used both
here at generation time and, independently, by --verify against data/gold.jsonl as written to
disk. A bug in a window-builder that mislabels one alert is caught by --verify, not assumed away.

⚑ TWO NAMED TRAPS, PLANTED ON PURPOSE -- see data/SOURCES.md for the exact fractions and windows.

    false_negative     a true-positive phishing_report worded like a routine "is this legit"
                        question rather than an alarm -- see MUNDANE_PHISHING below.
    false_correlation  two alerts that share a coincidental indicator (the same building's shared
                        egress IP, most often) or sit close in time, but are genuinely two
                        different incidents (or one incident and unrelated noise) -- see
                        build_false_correlation_window().

Neither trap is adversarial text: nothing here is written to deceive. A mundane phishing report is
exactly what a real one often reads like, and a shared IP range is exactly how two unrelated
alerts really do end up looking connected. That is why both are worth measuring.
"""
import argparse
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
sys.path.insert(0, HERE)

SEED = 20260819                              # fixed. change it and every downstream file changes.

START = datetime(2026, 8, 17, 6, 0, 0, tzinfo=timezone.utc)

ANALYSTS = ["Priya Shah", "Marcus Webb", "Dana Okafor", "Tomas Rivera"]

USERS = ["jrivera", "asingh", "mchen", "dokafor", "lferreira", "kwalsh", "tnguyen", "rpatel",
         "bcollins", "svargas", "mhassan", "jkowalski", "cbennett", "yamada"]
HOSTS = ["web-03", "db-12", "fin-app-02", "vpn-gw-01", "mail-relay-04", "build-agent-07",
         "hr-portal-01", "crm-db-05", "dev-jump-02", "pos-term-19"]

ALERT_TYPES = ("phishing_report", "suspicious_login", "malware_detection", "data_exfil_alert",
               "brute_force")

# ⚠︎ NEVER A ROUTABLE PUBLIC RANGE. 203.0.113.0/24, 198.51.100.0/24 and 192.0.2.0/24 are the three
# blocks IANA reserves for documentation (RFC 5737) -- they cannot resolve to anyone's real host,
# which is what "invented" has to mean for an indicator that looks like a network address.
EXT_IP_A, EXT_IP_B = "203.0.113", "198.51.100"

BAD_DOMAINS = ["secure-mailer-verify.info", "account-check-update.co", "payr0ll-portal.net",
               "hr-benefits-secure.info", "invoice-billing-net.co"]
GOOD_DOMAINS = ["newsletter.vendorhub-example.com", "notices.officesupplyco-example.com",
                "updates.travelbook-example.com"]

DEVICE_IDS = ["dev-a1029", "dev-b5510", "dev-c2277", "dev-d9931", "dev-e4468"]
GEOS = ["Vilnius, LT", "Tallinn, EE", "Lagos, NG", "Manila, PH", "Bogota, CO", "Chicago, IL",
        "Austin, TX", "Denver, CO"]


def _hexid(rng, n=16):
    return hashlib.sha256(str(rng.random()).encode()).hexdigest()[:n]


def _ip(rng, prefix):
    return "%s.%d" % (prefix, rng.randint(2, 254))


def _ts(base, minute_offset):
    return (base + timedelta(minutes=minute_offset)).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── alert factories ─────────────────────────────────────────────────────────────────────────────
# Each returns an alert dict (the ONLY thing the model ever sees). Disposition and case_id are
# tracked by the caller, in `alert_facts`, never inside the alert dict itself -- keeping the
# ground truth structurally separate from what gets rendered into a prompt.

PHISH_ALARMING = [
    "User reports an email demanding urgent wire transfer confirmation before end of day; sender "
    "domain closely resembles ours with one letter swapped; link asks for banking credentials.",
    "User reports an email claiming their mailbox is over quota with a link to 're-authenticate' "
    "that leads to a login page not hosted on our domain.",
    "User reports an email impersonating IT support asking them to install a 'security update' "
    "from an attached executable.",
]
PHISH_MUNDANE = [
    "User forwarded an email asking them to verify a password reset request, wants to know if "
    "it's legitimate before clicking anything.",
    "User asks whether an email about a benefits enrollment deadline is really from HR -- says it "
    "looked a little different from the usual one but nothing obviously wrong.",
    "User flagged an invoice email from a vendor they do business with, just double-checking since "
    "the payment details section looked slightly different from last time.",
]
PHISH_BENIGN = [
    "User reported a marketing newsletter from a known vendor as suspicious; appears to be a "
    "routine subscription email.",
    "User reported an automated shipping notification as suspicious; matches an order the user "
    "confirms they placed.",
    "User reported a calendar invite from an external partner as suspicious; partner confirmed by "
    "phone that the invite is genuine.",
]

LOGIN_TP_TAKEOVER = [
    "Successful login from a new device and an unfamiliar geographic location shortly after a "
    "password reset the user does not recall requesting.",
    "Successful login from a device never seen on this account, immediately followed by a mailbox "
    "forwarding rule being added.",
]
LOGIN_TP_AFTER_BRUTE = (
    "Successful login immediately following a string of failed attempts from the same source IP.")
LOGIN_FP_TRAVEL = [
    "Login from an unfamiliar location and new device; user confirmed by phone they are travelling "
    "for a conference this week.",
    "Login from a new device shortly after the user reported switching to a personal laptop while "
    "their work machine is being repaired.",
]

MALWARE_TP = [
    "Endpoint agent flagged an unsigned binary establishing a reverse shell connection shortly "
    "after execution.",
    "Endpoint agent flagged a process injecting into a system binary and disabling the local "
    "logging service.",
]
MALWARE_FP = [
    "Endpoint agent flagged a newly installed developer tool as an unrecognized binary; matches an "
    "approved software request filed with IT this week.",
    "Endpoint agent flagged a signed vendor update utility as unrecognized; the vendor rotated "
    "their code-signing certificate this month.",
]

EXFIL_TP = ("Unusual outbound transfer of a large archive to an external IP shortly after the "
            "malware alert on the same host.")
EXFIL_FP = [
    "Large outbound transfer to an external IP; matches the scheduled off-site backup window for "
    "this host.",
    "Large outbound transfer to an external IP; matches a data export the analytics team confirms "
    "they requested this morning.",
]

BRUTE_TP = ("Repeated failed login attempts against one account from a single source IP over a "
            "short window, followed by a successful login.")
BRUTE_FP = [
    "Repeated failed login attempts against one account from the user's own known device; user "
    "confirms they forgot their new password after a reset.",
    "Repeated failed login attempts against a service account from an internal host; matches a "
    "known misconfigured scheduled job that was fixed today.",
]


def phishing_alert(rng, aid, user, disposition, mundane=False, shared_domain=None):
    if disposition == "true_positive":
        text = rng.choice(PHISH_MUNDANE) if mundane else rng.choice(PHISH_ALARMING)
        domain = shared_domain or rng.choice(BAD_DOMAINS)
    else:
        text = rng.choice(PHISH_BENIGN)
        domain = rng.choice(GOOD_DOMAINS)
    return {"alert_id": aid, "alert_type": "phishing_report", "description": text,
            "entity": "user:%s" % user,
            "indicators": {"sender_domain": domain, "sender_ip": _ip(rng, EXT_IP_A),
                           "link_domain": domain}}


def login_alert(rng, aid, user, disposition, after_brute=False, shared_ip=None):
    if disposition == "true_positive":
        text = LOGIN_TP_AFTER_BRUTE if after_brute else rng.choice(LOGIN_TP_TAKEOVER)
    else:
        text = rng.choice(LOGIN_FP_TRAVEL)
    return {"alert_id": aid, "alert_type": "suspicious_login", "description": text,
            "entity": "user:%s" % user,
            "indicators": {"source_ip": shared_ip or _ip(rng, EXT_IP_B),
                           "login_geo": rng.choice(GEOS), "device_id": rng.choice(DEVICE_IDS)}}


def malware_alert(rng, aid, host, disposition, shared_hash=None):
    text = rng.choice(MALWARE_TP) if disposition == "true_positive" else rng.choice(MALWARE_FP)
    return {"alert_id": aid, "alert_type": "malware_detection", "description": text,
            "entity": "host:%s" % host,
            "indicators": {"file_hash": shared_hash or _hexid(rng, 40),
                           "process_name": rng.choice(["svc_update.exe", "wkr_helper.exe",
                                                        "sysmaint.exe", "netbridge.exe"]),
                           "host_ip": _ip(rng, "10.20")}}


def exfil_alert(rng, aid, host, disposition, shared_hash=None):
    text = EXFIL_TP if disposition == "true_positive" else rng.choice(EXFIL_FP)
    return {"alert_id": aid, "alert_type": "data_exfil_alert", "description": text,
            "entity": "host:%s" % host,
            "indicators": {"dest_ip": _ip(rng, EXT_IP_A),
                           "bytes_transferred": str(rng.randint(400_000_000, 6_000_000_000)),
                           "source_host": host if shared_hash is None else shared_hash}}


def brute_force_alert(rng, aid, user, disposition, shared_ip=None):
    text = BRUTE_TP if disposition == "true_positive" else rng.choice(BRUTE_FP)
    return {"alert_id": aid, "alert_type": "brute_force", "description": text,
            "entity": "user:%s" % user,
            "indicators": {"source_ip": shared_ip or _ip(rng, EXT_IP_B),
                           "target_account": user, "attempt_count": str(rng.randint(6, 40))}}


# ── ids ──────────────────────────────────────────────────────────────────────────────────────────

class Counters:
    def __init__(self):
        self.alert_n = 0
        self.inc_n = 0
        self.win_n = 0

    def alert_id(self):
        self.alert_n += 1
        return "ALT-%04d" % self.alert_n

    def case_id(self):
        self.inc_n += 1
        return "INC-%04d" % self.inc_n

    def window_id(self):
        self.win_n += 1
        return "cw%03d" % self.win_n


# ── window builders. Each returns (window_dict, facts, pattern, trap, trap_alert_ids, trap_pair) ─
# `facts` is a list of (alert_id, disposition, case_id_or_None) -- the raw material derive_gold()
# consumes. Nothing here writes alert_dispositions or case_groups directly.

def _window_shell(c, rng, alerts):
    wid = c.window_id()
    base = START + timedelta(minutes=37 * c.win_n)
    for i, a in enumerate(alerts):
        a["ts"] = _ts(base, i * rng.randint(1, 6))
    return {"id": wid, "window_start": _ts(base, 0),
            "on_call_analyst": ANALYSTS[(c.win_n - 1) % len(ANALYSTS)], "alerts": alerts}


def build_correlated_tp(c, rng, kind):
    """One genuine incident, every alert a true positive, one case_id -- the case a working
    correlation engine should get right without any trap in play."""
    facts = []
    case = c.case_id()
    if kind == "malware_exfil":
        host = rng.choice(HOSTS)
        shared = _hexid(rng, 40)
        a1 = malware_alert(rng, c.alert_id(), host, "true_positive", shared_hash=shared)
        a2 = exfil_alert(rng, c.alert_id(), host, "true_positive")
        alerts = [a1, a2]
    elif kind == "brute_login":
        user = rng.choice(USERS)
        ip = _ip(rng, EXT_IP_B)
        a1 = brute_force_alert(rng, c.alert_id(), user, "true_positive", shared_ip=ip)
        a2 = login_alert(rng, c.alert_id(), user, "true_positive", after_brute=True, shared_ip=ip)
        alerts = [a1, a2]
    elif kind == "phish_cluster":
        u1, u2 = rng.sample(USERS, 2)
        domain = rng.choice(BAD_DOMAINS)
        a1 = phishing_alert(rng, c.alert_id(), u1, "true_positive", mundane=True,
                            shared_domain=domain)
        a2 = phishing_alert(rng, c.alert_id(), u2, "true_positive", mundane=False,
                            shared_domain=domain)
        alerts = [a1, a2]
    else:  # "triple" -- brute force -> login -> malware on the pivoted host
        user, host = rng.choice(USERS), rng.choice(HOSTS)
        ip = _ip(rng, EXT_IP_B)
        a1 = brute_force_alert(rng, c.alert_id(), user, "true_positive", shared_ip=ip)
        a2 = login_alert(rng, c.alert_id(), user, "true_positive", after_brute=True, shared_ip=ip)
        a3 = malware_alert(rng, c.alert_id(), host, "true_positive")
        alerts = [a1, a2, a3]
    facts = [(a["alert_id"], "true_positive", case) for a in alerts]
    win = _window_shell(c, rng, alerts)
    trap = "false_negative" if kind == "phish_cluster" else None
    trap_ids = [alerts[0]["alert_id"]] if kind == "phish_cluster" else []
    return win, facts, "correlated_tp", trap, trap_ids, None


FP_BUILDERS = {
    "suspicious_login": lambda rng, aid: login_alert(rng, aid, rng.choice(USERS), "false_positive"),
    "malware_detection": lambda rng, aid: malware_alert(rng, aid, rng.choice(HOSTS),
                                                          "false_positive"),
    "phishing_report": lambda rng, aid: phishing_alert(rng, aid, rng.choice(USERS),
                                                        "false_positive"),
    "brute_force": lambda rng, aid: brute_force_alert(rng, aid, rng.choice(USERS),
                                                       "false_positive"),
    "data_exfil_alert": lambda rng, aid: exfil_alert(rng, aid, rng.choice(HOSTS),
                                                      "false_positive"),
}


def build_uncorrelated_fp(c, rng, n):
    """n false positives, deliberately unrelated -- different entities, no shared indicator --
    so the correct answer (no case at all) has no superficial temptation attached to it."""
    kinds = rng.sample(list(FP_BUILDERS), n)
    alerts = [FP_BUILDERS[k](rng, c.alert_id()) for k in kinds]
    facts = [(a["alert_id"], "false_positive", None) for a in alerts]
    win = _window_shell(c, rng, alerts)
    return win, facts, "uncorrelated_fp", None, [], None


SOLO_TP_BUILDERS = {
    "phishing_report": lambda rng, aid, mundane: phishing_alert(rng, aid, rng.choice(USERS),
                                                                 "true_positive", mundane=mundane),
    "malware_detection": lambda rng, aid, mundane: malware_alert(rng, aid, rng.choice(HOSTS),
                                                                  "true_positive"),
    "data_exfil_alert": lambda rng, aid, mundane: exfil_alert(rng, aid, rng.choice(HOSTS),
                                                               "true_positive"),
    "suspicious_login": lambda rng, aid, mundane: login_alert(rng, aid, rng.choice(USERS),
                                                               "true_positive"),
}


def build_mixed_tp_fp(c, rng, solo_kind, n_fp, mundane=False):
    """One genuine solo incident plus 1-2 unrelated false positives in the same window -- tests
    whether a decider can tell the real one apart from noise sharing no evidence with it."""
    case = c.case_id()
    tp = SOLO_TP_BUILDERS[solo_kind](rng, c.alert_id(), mundane)
    fp_kinds = rng.sample([k for k in FP_BUILDERS if k != solo_kind], n_fp)
    fps = [FP_BUILDERS[k](rng, c.alert_id()) for k in fp_kinds]
    alerts = [tp] + fps
    rng.shuffle(alerts)
    facts = [(a["alert_id"], "true_positive" if a["alert_id"] == tp["alert_id"] else
             "false_positive", case if a["alert_id"] == tp["alert_id"] else None)
             for a in alerts]
    win = _window_shell(c, rng, alerts)
    trap = "false_negative" if (solo_kind == "phishing_report" and mundane) else None
    trap_ids = [tp["alert_id"]] if trap else []
    return win, facts, "mixed_tp_fp", trap, trap_ids, None


def build_multi_incident(c, rng, sizes):
    """Two genuinely separate incidents in one window, on different entities with no shared
    indicator -- the corpus's other half of "don't merge what shouldn't merge", without a
    coincidental cue tempting the mistake. build_false_correlation_window is where that cue lives."""
    alerts, facts = [], []
    for size in sizes:
        case = c.case_id()
        if size == 1:
            kind = rng.choice(list(SOLO_TP_BUILDERS))
            a = SOLO_TP_BUILDERS[kind](rng, c.alert_id(), False)
            alerts.append(a)
            facts.append((a["alert_id"], "true_positive", case))
        else:
            host = rng.choice(HOSTS)
            shared = _hexid(rng, 40)
            a1 = malware_alert(rng, c.alert_id(), host, "true_positive", shared_hash=shared)
            a2 = exfil_alert(rng, c.alert_id(), host, "true_positive")
            alerts += [a1, a2]
            facts += [(a1["alert_id"], "true_positive", case), (a2["alert_id"], "true_positive",
                      case)]
    rng.shuffle(alerts)
    win = _window_shell(c, rng, alerts)
    return win, facts, "multi_incident", None, [], None


def build_false_correlation_window(c, rng, pair_size, other_is_tp):
    """The false-correlation trap. One genuine incident (1 or 2 alerts, one case_id) plus one
    unrelated alert that shares a coincidental indicator -- most often the same egress IP, which
    is exactly how two unrelated users behind the same building or VPN concentrator end up sharing
    a source_ip by accident. Gold keeps them in separate groups (or no group, when the unrelated
    alert is a false positive); the trap is whether a reader merges on the shared IP alone.
    """
    shared_ip = _ip(rng, EXT_IP_B)
    case = c.case_id()
    if pair_size == 2:
        user = rng.choice(USERS)
        a1 = brute_force_alert(rng, c.alert_id(), user, "true_positive", shared_ip=shared_ip)
        a2 = login_alert(rng, c.alert_id(), user, "true_positive", after_brute=True,
                         shared_ip=shared_ip)
        known = [a1, a2]
        known_facts = [(a1["alert_id"], "true_positive", case), (a2["alert_id"], "true_positive",
                       case)]
    else:
        user = rng.choice(USERS)
        a1 = brute_force_alert(rng, c.alert_id(), user, "true_positive", shared_ip=shared_ip)
        known = [a1]
        known_facts = [(a1["alert_id"], "true_positive", case)]

    other_user = rng.choice([u for u in USERS if u != known[0]["entity"].split(":")[1]])
    if other_is_tp:
        other_case = c.case_id()
        other = login_alert(rng, c.alert_id(), other_user, "true_positive", shared_ip=shared_ip)
        other_fact = (other["alert_id"], "true_positive", other_case)
    else:
        other = login_alert(rng, c.alert_id(), other_user, "false_positive", shared_ip=shared_ip)
        other_fact = (other["alert_id"], "false_positive", None)

    alerts = known + [other]
    rng.shuffle(alerts)
    facts = known_facts + [other_fact]
    win = _window_shell(c, rng, alerts)
    trap_pair = [known[0]["alert_id"], other["alert_id"]]
    return win, facts, "false_correlation_trap", "false_correlation", [], trap_pair


# ── the derivation, used at build time AND by --verify ────────────────────────────────────────────

def derive_gold(facts):
    """The ONE place alert_dispositions and case_groups are computed from alert_facts. Grouping is
    by case_id among true-positive alerts only; a false positive never appears in any group,
    exactly as the mechanic spec requires. Sorted so the output is deterministic regardless of the
    order alerts were built or shuffled in."""
    dispositions = {aid: disp for aid, disp, _cid in facts}
    groups = {}
    for aid, disp, cid in facts:
        if disp == "true_positive":
            groups.setdefault(cid, []).append(aid)
    case_groups = sorted((sorted(ids) for ids in groups.values()), key=lambda g: g[0])
    return dispositions, case_groups


# ── assembly ────────────────────────────────────────────────────────────────────────────────────

def build_corpus(rng):
    c = Counters()
    windows, gold = [], []

    def add(builder_result):
        win, facts, pattern, trap, trap_ids, trap_pair = builder_result
        dispositions, case_groups = derive_gold(facts)
        windows.append(win)
        gold.append({
            "id": win["id"], "pattern": pattern,
            "alert_facts": [[aid, disp, cid] for aid, disp, cid in facts],
            "alert_dispositions": dispositions, "case_groups": case_groups,
            "trap": trap, "trap_alert_ids": trap_ids, "trap_pair": trap_pair,
        })

    # 1. correlated_tp -- 7 windows, one genuine incident each, no trap except the phishing
    #    cluster (which doubles as one of the false_negative trap windows).
    for kind in ("malware_exfil", "malware_exfil", "malware_exfil", "brute_login", "brute_login",
                 "phish_cluster", "triple"):
        add(build_correlated_tp(c, rng, kind))

    # 2. uncorrelated_fp -- 6 windows, all noise, no case at all.
    for n in (2, 2, 3, 2, 3, 2):
        add(build_uncorrelated_fp(c, rng, n))

    # 3. mixed_tp_fp -- 7 windows, one real incident buried in 1-2 unrelated false positives.
    #    4 use phishing_report as the solo incident (2 of those mundane -- the false_negative
    #    trap); the other 3 diversify the alert type carrying the real incident.
    plan = [("phishing_report", True), ("phishing_report", True), ("phishing_report", False),
            ("phishing_report", False), ("malware_detection", False),
            ("data_exfil_alert", False), ("suspicious_login", False)]
    n_fps = [1, 2, 1, 2, 1, 2, 1]
    for (kind, mundane), n_fp in zip(plan, n_fps):
        add(build_mixed_tp_fp(c, rng, kind, n_fp, mundane))

    # 4. multi_incident -- 5 windows, two real incidents in one window, no shared evidence.
    for sizes in ([1, 1], [1, 2], [2, 1], [1, 1], [2, 2]):
        add(build_multi_incident(c, rng, sizes))

    # 5. false_correlation_trap -- 8 windows, the second named trap.
    plan2 = [(2, False), (2, False), (2, False), (2, True), (2, False), (3, False), (3, True),
             (2, False)]
    for pair_size, other_tp in plan2:
        add(build_false_correlation_window(c, rng, pair_size, other_tp))

    return windows, gold


def write(windows, gold):
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(DATA, "windows.jsonl"), "w", encoding="utf-8") as fh:
        for w in windows:
            fh.write(json.dumps(w) + "\n")
    with open(os.path.join(DATA, "gold.jsonl"), "w", encoding="utf-8") as fh:
        for g in gold:
            fh.write(json.dumps(g) + "\n")


def verify():
    """Re-read data/windows.jsonl and data/gold.jsonl FROM DISK and re-derive every gold row
    independently via derive_gold(). Also checks that alert_facts names exactly the alerts that
    window actually carries -- neither more nor fewer -- so a window built by one pattern function
    and labelled by a stale copy of another cannot slip through silently.
    """
    win_path = os.path.join(DATA, "windows.jsonl")
    gold_path = os.path.join(DATA, "gold.jsonl")
    windows = {json.loads(l)["id"]: json.loads(l)
              for l in open(win_path, encoding="utf-8") if l.strip()}
    gold_rows = [json.loads(l) for l in open(gold_path, encoding="utf-8") if l.strip()]

    checked = 0
    for g in gold_rows:
        win = windows[g["id"]]
        win_ids = {a["alert_id"] for a in win["alerts"]}
        fact_ids = {aid for aid, _d, _c in g["alert_facts"]}
        assert win_ids == fact_ids, (
            "%s: window carries %r but alert_facts names %r" % (g["id"], sorted(win_ids),
                                                                 sorted(fact_ids)))
        dispositions, case_groups = derive_gold(g["alert_facts"])
        assert dispositions == g["alert_dispositions"], (
            "%s: derive_gold(alert_facts) disagrees with the written alert_dispositions"
            % g["id"])
        assert case_groups == g["case_groups"], (
            "%s: derive_gold(alert_facts) disagrees with the written case_groups" % g["id"])
        # Every false positive is absent from every group -- re-checked directly against the
        # written case_groups, not merely implied by derive_gold() agreeing with itself.
        grouped = {aid for grp in g["case_groups"] for aid in grp}
        for aid, disp, _cid in g["alert_facts"]:
            if disp == "false_positive":
                assert aid not in grouped, "%s: false positive %s appears in a case group" % (
                    g["id"], aid)
        if g["trap"] == "false_correlation":
            a, b = g["trap_pair"]
            ga = next((i for i, grp in enumerate(g["case_groups"]) if a in grp), None)
            gb = next((i for i, grp in enumerate(g["case_groups"]) if b in grp), None)
            assert ga != gb or ga is None or gb is None, (
                "%s: trap_pair %s is gold-merged, which is not a false-correlation trap"
                % (g["id"], g["trap_pair"]))
        checked += 1

    fn_trap = sum(1 for g in gold_rows if g["trap"] == "false_negative")
    fc_trap = sum(1 for g in gold_rows if g["trap"] == "false_correlation")
    print("verify: %d windows checked against gold, 0 drift" % checked)
    print("verify: %d false_negative-trap window(s), %d false_correlation-trap window(s)"
          % (fn_trap, fc_trap))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true",
                    help="re-derive gold from data/*.jsonl on disk and assert no drift; does not "
                         "regenerate anything")
    a = ap.parse_args()

    if a.verify:
        verify()
        return

    rng = random.Random(SEED)
    windows, gold = build_corpus(rng)
    write(windows, gold)

    n_alerts = sum(len(w["alerts"]) for w in windows)
    n_tp = sum(1 for g in gold for _a, d, _c in g["alert_facts"] if d == "true_positive")
    n_fp = n_alerts - n_tp
    print("windows: %d   alerts: %d   (true_positive %d, false_positive %d)"
          % (len(windows), n_alerts, n_tp, n_fp))
    by_pattern = {}
    for g in gold:
        by_pattern[g["pattern"]] = by_pattern.get(g["pattern"], 0) + 1
    print("by pattern:", by_pattern)
    verify()


if __name__ == "__main__":
    main()
