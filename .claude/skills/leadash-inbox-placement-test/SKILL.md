---
name: leadash-inbox-placement-test
description: Run an inbox placement test on a Leadash sending fleet using MailReach seeds - one Leadash test campaign per sender pool, production-shaped copy, the raw 4-way placement split, and a segment-aware KILL/MARGINAL/KEEP verdict per pool. Use when the user says "placement test", "inbox placement", "are we landing in spam", "spam test", "check deliverability", "MailReach test", "should we kill these inboxes", "/leadash-inbox-placement-test", or when Leadash reply rates drop and list quality is already ruled out. Leadash steps are done in the Leadash app; MailReach steps are scripted.
argument-hint: "[Leadash workspace name]"
---

# Leadash Inbox Placement Test

Adapted from `inbox-placement-test` (EmailBison + MailReach) for Leadash. The
method, MailReach API calls and scoring are unchanged. What changed:

- **Leadash steps run through the Leadash MCP connector** (`leadash` in
  `.mcp.json`, https://www.leadash.com/api/mcp) when it is connected and
  authorized. Find its tools with ToolSearch ("leadash"), read each tool's
  schema before calling it, and never guess a tool or field. Every create,
  update or launch call needs the operator's explicit go first. If the
  connector is not authorized, do the same steps manually in the Leadash app.
- **One script** (`scripts/placement.py`) runs the MailReach side: create
  tests, write the seed upload CSV, poll, score.

For the full method and every gotcha behind it, read
`../inbox-placement-test/reference/sop.md`. Where it says "Bison", read
"Leadash"; skip its Bison API calls.

## Step 1 - ask the operator (all in one message, never guess)

1. **Which Leadash workspace**, and confirm you will build test campaigns there.
2. **Which MailReach account** to bill (if several keys exist). Credits are
   spent only once a test actually receives mail: one per pool per round.
3. **Which inboxes are in scope**, grouped into pools. Split by vendor and auth
   type: blended pools hide which vendor is failing.
4. **Each pool's segment**: `GW` if it sends to Google recipients in
   production, `M365` if Microsoft. Confirm from the live Leadash campaigns
   (which inboxes send which campaigns). Guessing here inverts the verdict.
5. **Full seed set or work seeds only?** Work-only is faster on small pools;
   personal Gmail/Outlook seeds never change the verdict.
6. **Which copy**: production-shaped (default) or fingerprint-isolation (fresh
   copy, needs sign-off). See Step 3.
7. **Where results go**: a Google Sheet (which sheet and tab), or just the chat.

## Step 2 - set up the run (outside the repo)

```bash
export PLACEMENT_RUN_DIR=~/placement-runs/<workspace>-<date>
mkdir -p "$PLACEMENT_RUN_DIR"
cp env.example "$PLACEMENT_RUN_DIR/.env"            # operator fills in the MailReach key
cp config.example.json "$PLACEMENT_RUN_DIR/config.json"
```

Fill `config.json`: one entry per pool with `name`, `segment`, `inboxes`.
Keep run files outside the repo: the seed CSV and keys must never be committed.

## Step 3 - choose the copy

- **Production-shaped (default):** the real Email 1, every variable except
  first name replaced with a sensible static rendering, one route picked,
  spintax kept. Same copy in every pool; only the tag differs.
- **Fingerprint-isolation:** fresh copy sharing no phrasing with any live
  campaign, spintaxed at phrase level. Use when a whole fleet fails on
  production copy, to separate burned copy from dead inboxes. Get sign-off first.

Avoid cliche subjects ("quick question", "worth a look"). No em dashes.
First name is the only variable: seeds have no company or role.

## Step 4 - create the MailReach tests

```bash
python scripts/placement.py create            # dry run
python scripts/placement.py create --create   # one test per pool
```

This saves each pool's `mlrch-` tag to `.placement_state.json` and writes
`leadash_seed_upload.csv` (email, first_name; blank first names backfilled).
Same `seedlist` for every pool, so every campaign gets the same seeds.

## Step 5 - build one Leadash campaign per pool

Via the Leadash connector if authorized (show the operator each campaign's
settings before creating it), otherwise walk the operator through the app pool
by pool. Record each campaign name or ID in `config.json` under
`leadash_campaign`. Mirror the Bison test settings:

| Setting | Value | Why |
|---|---|---|
| Name | `Inbox Placement Test - <date> - <pool>` | One campaign per pool |
| Sequence | 1 step only | Only Email 1 is tested |
| Body | Approved copy, then the pool's `mlrch-` tag on its own line | MailReach matches by tag |
| Format | Plain text, no HTML | Match production sending |
| Open tracking | Off | No pixel |
| Link tracking | Off, and no links in the body | No tracked links |
| Unsubscribe link or footer | Off for this test | Seeds, not prospects |
| Senders | Only this pool's inboxes; no inbox in two pools | Overlap confounds results |
| Leads | Upload `leadash_seed_upload.csv`; map `normalized_first_name` to the custom variable of the same name | Every seed gets one email |
| Daily new-lead limit | At least the seed count | All seeds go out in one pass |
| Lead priority | New leads first, if Leadash offers it | Step 1 fires immediately |
| Send window | Starts now, 60+ min, weekdays | Each inbox needs time per round |
| Warm-up | Leave as it is in production | Test real conditions |

**Leadash syntax** (from our production copy):

- Spintax: single braces, pipe-separated: `{Hi|Hello}`, `{Best|Cheers}`.
- Variables: double braces with the `custom:` prefix: `{{custom:normalized_first_name}}`.
- First name: `{{custom:normalized_first_name}}`. The seed CSV's
  `normalized_first_name` column maps to it on upload.
- Never put a `custom:` variable the seeds lack (company, first line, jargon)
  in the test copy: render those as static text.

Example test body:

```
{Hi|Hello} {{custom:normalized_first_name}},

<static line 1 with {spintax|variants}>

<static line 2 with {spintax|variants}>

{Best|Cheers},
<signature>

mlrch-XXXXXXXX
```

## Step 6 - QA gate, then the operator's launch gate

Check every campaign before launch and report a PASS/FAIL table per pool:

- Spintax braces balanced, no empty options, no unknown variables; preview 5 leads in Leadash.
- Each pool's tag appears exactly once, in its own campaign only; all tags unique.
- Same seed count in every campaign, no blank first names, no duplicates.
- Settings match the table above; sender counts match the pool sizes.
- Every sender shows connected and healthy in Leadash. A disconnected inbox sends nothing and drags the pool down: exclude and flag it.

**STOP.** Show the table and rendered copy. Launch only on the operator's
explicit go. Then hands off: do not pause and resume to "unstick" a campaign.

## Step 7 - poll, then score

```bash
python scripts/placement.py poll       # exits when every test is final and stable
python scripts/placement.py results    # writes results.json
```

Rules: personal inboxes are diagnostic only; score each pool only against the
segment it serves. Verdict, in-segment: **KILL** under ~50%, **MARGINAL**
~50-80%, **KEEP** ~80%+. Seeds can take 30-60 min to scan after sending.

## Step 8 - write it up

Give a per-pool table (segment, in-segment, off-segment, score, verdict) and a
short diagnosis. If the operator keeps a sheet, add a block below the previous
round in the same tab with identical formatting. Ask before writing to it.
After the run, pause or archive the test campaigns in Leadash (operator's call).

## If a pool fails

Diagnose before recommending a rebuild: check sender health in Leadash, send
counts per inbox, whether all seeds actually went out, and whether the copy is
fingerprinted (rerun in fingerprint-isolation mode). See SOP Steps 14 to 14.7.

## Notes

- Never reuse a MailReach tag or a prior run's seed list.
- Never commit `.env`, the seed CSV or results; keep them in `PLACEMENT_RUN_DIR`.
- Leadash settings names may differ from the table; confirm each with the operator.
