# CLAUDE.md: Meta4 Solutions GTM Context OS

## Company
Meta4 Solutions (createyourmeta-iv.com), launching "Ready-made Awards" for the Q4 / -ember season. [Fill in one line after research, with source.]

## How this folder works
- `.claude/skills/`: reusable Claude skills for this GTM work. Read when a task matches a skill.
- `context/icp/`: ideal customer profiles and buyer personas. Read before any targeting, list building or copy.
- `context/positioning/`: positioning, category, differentiators, competitors. Read before writing any messaging.
- `context/messaging/`: approved messaging, value props, objection handling. Read before writing copy.
- `context/brand-kit/`: logos, colors, fonts, tone of voice. Read before producing any visual or written asset.
- `context/docs/research/`: raw research with sources. Read when you need a fact; add here when you find one.
- `knowledge-base/playbooks/`: repeatable GTM processes. Read before running a campaign or motion.
- `knowledge-base/learnings/`: what worked and what did not. Read before planning; add after each result.
- `meetings/`: meeting notes, named YYYY-MM-DD-topic.md. Read for decisions and context from calls.
- `output/campaigns/`: finished campaign assets, one folder per campaign. Write final deliverables here.
- `tools/`: scripts and tool configs. Read before automating anything.
- `weekly-priorities/`: one file per ISO week (YYYY-Www.md). Read at the start of every session.
- `work-log/`: one file per ISO week, matching weekly-priorities. Append an entry after every change.

## Rules
- Cite a source for every company fact (link or file path in context/docs/research/).
- Never invent numbers. If a number is unknown, write [TBD] and flag it.
- No em dashes in any copy.
- Ask before sending or publishing anything.
- Log every change in this week's work log (work-log/YYYY-Www.md).

## Skills (.claude/skills/, from bolaji-ships/gtm-starter-kit; credits in THIRD-PARTY.md)
- Strategy: `signal-matrix` (ICP/signal matrix), `campaign-strategy` (15-25 campaign ideas), `build-workflow-spec` (approved workflow spec, no copy).
- Copy: `campaign-copy` (cold email and LinkedIn DM copy, gated on an approved spec), `prompt-builder` (per-row AI prompts).
- Clay build: `campaign-contract` -> `design-clay-table-json` -> `import-clay-table` -> `save-clay-schema`; `build-clay` (build or audit a full workbook).
- Clay cost and data: `calculate-costs`, `workspace-cost-audit`, `export-tables` (to local CSV, gitignored).
- QA and deliverability: `campaign-qa` (Leadash via exports, Option L), `leadash-inbox-placement-test` (Leadash + MailReach; use this), `inbox-placement-test` (Bison original, reference only).
- Research and visuals: `crawl4ai` (crawl sites to Markdown), `agent-browser` (drive a browser), `miro-gtm-flowchart` (needs Miro connected).

## Tools
- Clay: enrichment, list building and AI columns. Most skills above run on it.
- Leadash: cold email sending. No verified public API docs, so Leadash steps run in the app or from CSV exports. Add docs to context/docs/research/ to unlock an API path.
- Google Sheets: shared lists and reporting.
- `tools/rex/`: unofficial Clay API client (uses your browser session) plus the ClayLens cost extension. Keep session files out of Git.
- `tools/crawl4ai/`, `tools/agent-browser/`: setup notes for the local crawler and browser tools.
