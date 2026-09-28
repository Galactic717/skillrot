---
name: skillrot
description: Audits an agent skill library for context cost, dead skills and broken SKILL.md frontmatter. Use when the user asks why their agent is slow or bloated, wants to prune installed skills, asks what their skills cost in tokens, or wants a SKILL.md checked before publishing it.
license: MIT
allowed-tools: Bash Read
---

# skillrot

Audit a skill library: what it costs per message, what can never fire, what is broken.

## Run it

```bash
python ${CLAUDE_SKILL_DIR}/skillrot.py --json
```

Add a path to audit somewhere specific:

```bash
python ${CLAUDE_SKILL_DIR}/skillrot.py ./skills --json
```

Useful flags: `--portable` (check a skill will survive a claude.ai upload), `--no-usage`
(skip the transcript scan), `--fail-on error` (CI), `--full` (every finding).

## Reading the output

`budget.always_on_tokens` is paid on every request. `budget.overflows` is true when the
listing wants more than `budget.listing_budget` (1% of the window): Claude Code then lists
the least-used skills name-only, and skillrot flags each with SR030 — they can't be matched
by keyword. `budget.body_tokens` is what loads when skills fire and then squats in context
for the rest of the session. Findings carry a rule id, a severity and a fix.

## Reporting back

1. Lead with the always-on number and what share of the context window it takes.
2. Name the worst offenders by listing cost, marking any with `invocations: 0`.
3. List errors before warnings. Errors mean a skill is broken, not merely expensive.
4. For a prune recommendation, rank by listing cost among skills that have never fired.
   Say plainly that "never fired" is evidence from local history, not proof a skill is
   useless — a recently installed skill has not fired yet either.
5. If the listing is over budget (SR030), lead with that: naming which skills are already
   name-only is more urgent than a merely expensive skill, because the router is blind to
   them right now.

Do not delete or edit any skill without the user asking for that specific change.

## Rules

`docs/RULES.md` in this directory documents every rule and cites the behaviour it catches.
Read it before explaining a finding you are unsure about.
