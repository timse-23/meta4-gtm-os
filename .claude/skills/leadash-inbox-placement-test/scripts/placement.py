#!/usr/bin/env python3
"""Leadash + MailReach inbox placement test: the MailReach half, automated.

Leadash has no public API documentation we could verify, so every Leadash step
(campaign build, settings, senders, seed upload, launch) is done by the operator
in the Leadash app, following SKILL.md. This script does only the parts that run
against MailReach's documented API, adapted from inbox-placement-test/scripts.

Stdlib only. Every command that spends or creates is dry-run unless armed.

    python placement.py create            # dry run: shows the tests it would create
    python placement.py create --create   # one MailReach test per pool + seeds CSV
    python placement.py poll              # wait until every test is final
    python placement.py results           # 4-way split + segment-aware verdict

Run files live in PLACEMENT_RUN_DIR (config.json, .env, state, seeds, results).
"""
import csv
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.expanduser(os.environ.get("PLACEMENT_RUN_DIR") or "."))
CONFIG_PATH = os.path.join(ROOT, "config.json")
STATE_PATH = os.path.join(ROOT, ".placement_state.json")
ENV_PATH = os.path.join(ROOT, ".env")
SEEDS_CSV = os.path.join(ROOT, "leadash_seed_upload.csv")
RESULTS_PATH = os.path.join(ROOT, "results.json")

MR_BASE = "https://api.mailreach.co/api/v1/spam_tests"
# MailReach sits behind Cloudflare and rejects requests without a browser UA.
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# MailReach `desc` -> scoring bucket. Lowercased lookups: MailReach mixes case.
DESC_BUCKETS = {
    "google workspace": "gw",
    "google workspace with smart features": "gw",
    "google workspace without smart features": "gw",
    "gmail account with smart features": "gmail",
    "gmail account": "gmail",
    "office 365": "m365",
    "hotmail account": "outlook",
    "outlook account": "outlook",
}
SEG_KEY = {"GW": "gw", "M365": "m365"}


# ---------------------------------------------------------------- helpers
def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load_env():
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH) as fh:
        for line in fh:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def mr_key():
    load_env()
    name = os.environ.get("MAILREACH_KEY_VAR", "MAILREACH_API_KEY")
    key = os.environ.get(name, "").strip()
    if not key:
        die(f"{name} is empty. Put it in {ENV_PATH} (never paste it in chat).")
    return key


def load_json(path, what):
    if not os.path.exists(path):
        die(f"No {what} at {path}.")
    with open(path) as fh:
        return json.load(fh)


def save_state(state):
    with open(STATE_PATH, "w") as fh:
        json.dump(state, fh, indent=1)


def request(method, url, body=None):
    headers = {"X-Api-Key": f"Bearer {mr_key()}", "User-Agent": BROWSER_UA,
               "Content-Type": "application/json"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            return exc.code, {"__error": exc.read().decode("utf-8", "replace")[:400]}
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < 3:
                time.sleep(2 * (attempt + 1))
                continue
            return 0, {"__error": str(exc)}
    return 0, {"__error": "exhausted retries"}


def bare_id(value):
    return (value or "").strip().removeprefix("mlrch-")


def get_test(public_id):
    status, payload = request("GET", f"{MR_BASE}/{bare_id(public_id)}")
    if status != 200:
        die(f"MailReach {public_id} failed ({status}): {payload.get('__error')}")
    return payload


def first_name_for(seed):
    """Every seed needs a first name (it is the copy's only variable). Backfill
    from the address prefix: rita.johnson2r@... -> Rita."""
    name = (seed.get("first_name") or "").strip()
    if name:
        return name
    prefix = (seed.get("email") or "").split("@")[0].split(".")[0]
    prefix = re.sub(r"[\d_+-].*$", "", prefix)
    return prefix.capitalize() or "There"


def is_work(seed):
    return DESC_BUCKETS.get((seed.get("desc") or "").strip().lower()) in ("gw", "m365")


def bucket_counts(test):
    counts = {b: {"inbox": 0, "spam": 0, "other": 0, "total": 0}
              for b in ("gw", "gmail", "m365", "outlook", "unknown")}
    for row in test.get("results") or []:
        b = DESC_BUCKETS.get((row.get("desc") or "").strip().lower(), "unknown")
        placed = (row.get("received_in") or "").strip().upper()
        counts[b]["total"] += 1
        counts[b]["inbox" if placed == "INBOX" else "spam" if placed == "SPAM" else "other"] += 1
    return counts


def verdict(inbox, total):
    if not total:
        return "NO DATA"
    ratio = inbox / total
    return "KEEP" if ratio >= 0.80 else "MARGINAL" if ratio >= 0.50 else "KILL"


def scanned_count(test):
    return len([r for r in (test.get("results") or []) if r.get("received_in")])


# ---------------------------------------------------------------- commands
def cmd_create():
    cfg = load_json(CONFIG_PATH, "config.json")
    pools = cfg.get("pools") or die("config.json has no pools.")
    for p in pools:
        if p.get("segment") not in SEG_KEY:
            die(f"Pool {p.get('name')}: segment must be GW or M365 (confirm from live campaigns).")
    if os.path.exists(STATE_PATH):
        die(f"{STATE_PATH} already exists. Start a new run dir; never reuse MailReach tags.")
    seedlist = int(cfg.get("seedlist", 1))
    print(f"Will create {len(pools)} MailReach test(s), seedlist={seedlist}:")
    for p in pools:
        print(f"  - {p['name']} (segment {p['segment']})")
    if "--create" not in sys.argv:
        print("\n[DRY RUN] nothing created. Pass --create to create the tests.")
        return

    state = {"created": datetime.datetime.now().isoformat(timespec="seconds"),
             "seedlist": seedlist, "pools": []}
    seeds = None
    for p in pools:
        status, t = request("POST", MR_BASE, {"seedlist": seedlist})
        if status not in (200, 201):
            save_state(state)
            die(f"Create failed for {p['name']} ({status}): {t.get('__error')}")
        results = t.get("results") or []
        emails = sorted(r.get("email") for r in results)
        if seeds is None:
            seeds = results
        elif emails != sorted(r.get("email") for r in seeds):
            print(f"  WARNING: {p['name']} got a different seed list. Upload its own list.")
        state["pools"].append({**p, "tag": t.get("public_full_id"),
                               "public_id": t.get("public_id"),
                               "seed_emails": emails})
        print(f"  {p['name']}: {t.get('public_full_id')} ({len(results)} seeds)")
        time.sleep(0.4)  # stay well under MailReach's ~20 req/s guidance
    save_state(state)

    work_only = bool(cfg.get("work_seeds_only"))
    rows = [s for s in seeds if is_work(s)] if work_only else seeds
    with open(SEEDS_CSV, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["email", "first_name"])
        for s in rows:
            w.writerow([s.get("email"), first_name_for(s)])
    print(f"\nSaved tags to {STATE_PATH}")
    print(f"Wrote {len(rows)} seeds to {SEEDS_CSV} for upload to every Leadash test campaign.")
    print("Paste each pool's mlrch- tag, on its own line, into that pool's campaign body only.")


def cmd_poll():
    state = load_json(STATE_PATH, "run state (run `create --create` first)")
    interval = int(sys.argv[sys.argv.index("--interval") + 1]) if "--interval" in sys.argv else 300
    hours = float(sys.argv[sys.argv.index("--max-hours") + 1]) if "--max-hours" in sys.argv else 4.0
    deadline = time.time() + hours * 3600
    tests = [(p["name"], bare_id(p["tag"])) for p in state["pools"]]
    done, prev, stable = set(), {}, {}
    while time.time() < deadline:
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        for name, pid in tests:
            if pid in done:
                continue
            t = get_test(pid)
            scanned = scanned_count(t)
            # completed=true alone is NOT final: an untouched test also reports it.
            stable[pid] = stable.get(pid, 0) + 1 if prev.get(pid) == scanned else 0
            prev[pid] = scanned
            ready = (bool(t.get("completed")) and t.get("score") is not None
                     and scanned > 0 and stable[pid] >= 2)
            if ready:
                done.add(pid)
            print(f"[{stamp}] {name:22s} scanned {scanned}/{len(t.get('results') or [])} "
                  f"score {t.get('score')}{' DONE' if ready else ''}")
        if len(done) == len(tests):
            print(f"\nAll {len(tests)} tests final. Run `results`.")
            return
        time.sleep(interval)
    print(f"\nTimed out with {len(done)}/{len(tests)} final.")
    raise SystemExit(3)


def cmd_results():
    state = load_json(STATE_PATH, "run state")
    out = []
    for p in state["pools"]:
        t = get_test(p["tag"])
        scanned = scanned_count(t)
        if scanned == 0 or t.get("score") is None:
            die(f"{p['name']}: nothing scanned yet. Scoring now would report KILL "
                "on healthy inboxes. Keep polling.")
        c = bucket_counts(t)
        seg = p["segment"]
        off = "M365" if seg == "GW" else "GW"
        s, o = c[SEG_KEY[seg]], c[SEG_KEY[off]]
        row = {
            "pool": p["name"], "segment": seg, "tag": p["tag"],
            "leadash_campaign": p.get("leadash_campaign", ""),
            "inboxes": p.get("inboxes"), "scanned": scanned,
            "gw": f"{c['gw']['inbox']}/{c['gw']['total']}",
            "m365": f"{c['m365']['inbox']}/{c['m365']['total']}",
            "gmail": f"{c['gmail']['inbox']}/{c['gmail']['total']}",
            "outlook": f"{c['outlook']['inbox']}/{c['outlook']['total']}",
            "in_segment": f"{s['inbox']}/{s['total']}",
            "off_segment": f"{o['inbox']}/{o['total']}",
            "score": t.get("score"),
            "verdict": verdict(s["inbox"], s["total"]),
            "completed": bool(t.get("completed")),
            "unknown_desc": c["unknown"]["total"],
        }
        out.append(row)
    hdr = f"{'pool':22s} {'seg':>5s} {'in-seg':>8s} {'off-seg':>8s} {'score':>6s}  verdict"
    print("\n" + hdr + "\n" + "-" * len(hdr))
    for r in out:
        print(f"{r['pool']:22s} {r['segment']:>5s} {r['in_segment']:>8s} "
              f"{r['off_segment']:>8s} {str(r['score']):>6s}  {r['verdict']}")
        if r["unknown_desc"]:
            print(f"    NOTE: {r['unknown_desc']} seeds had an unknown provider; add it to DESC_BUCKETS.")
        if not r["completed"]:
            print("    NOTE: test not marked completed; numbers may still move.")
    with open(RESULTS_PATH, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"\nWrote {RESULTS_PATH}. The verdict uses the in-segment column only; "
          "personal Gmail/Outlook and off-segment are diagnostic.")


if __name__ == "__main__":
    cmds = {"create": cmd_create, "poll": cmd_poll, "results": cmd_results}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        raise SystemExit(2)
    cmds[sys.argv[1]]()
