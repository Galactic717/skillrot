---
name: skillrot
description: Use when the user wants to review installed agent skills, compare estimated Claude Code listing costs, inspect local invocation evidence, find command conflicts, or check SKILL.md files before publishing a library.
license: MIT
allowed-tools: Bash Read
---

# skillrot

Run an offline audit and explain which findings warrant a change.
Requires Python 3.9+ and access to local files through a shell.

## Run it

Locate `skillrot.py` beside this `SKILL.md` using the skill's verified filesystem
location. In Claude Code, `${CLAUDE_SKILL_DIR}` may identify that directory; verify
that the file exists. Other harnesses should use the actual installation location.
Quote the absolute script path and library path, then run:

```bash
python "/verified/path/to/skillrot/skillrot.py" "/path/to/skills" --no-usage --json
```

Replace the example paths with real paths before running. Use `python3` if needed.
For the user's installed Claude Code inventory, omit the library path. For Codex,
Cursor or another harness, supply the library directory explicitly. If local shell
or files are unavailable, explain the setup requirement and provide the command for
the user to run; do not invent a report. Runtime auditing uses no network service.

Use `--portable` for supported Agent Skills constraints. The example skips transcripts;
when invocation evidence is requested, remove `--no-usage` or select `--transcripts`.
Transcripts remain local. Use `--fail-on error --fail-over-budget` to gate CI. Check the process exit code:
0 means the requested gates passed, 1 means a finding/budget gate failed, and 2 means an
argument or operational error. A completed audit can return JSON even when a gate fails.

## Interpret the report

`budget.requested_tokens` estimates the eligible listing before budget pressure.
`budget.always_on_tokens` estimates retained names and descriptions. `budget.overflows`
means the requested listing exceeds the modeled budget. SR030 predicts that an entry's
description would be omitted; its name can still be visible and direct invocation may
still work. The tool does not inspect a live session's routing decisions.

`budget.body_tokens` estimates potential body load size, not a measured recurring bill.
Per-entry `listing_tokens` is requested cost and `retained_listing_tokens` is modeled
retained cost. `invocations: 0` means none were observed in available local transcripts;
null means scanning was disabled or no usable invocation evidence was available.

## Report back

1. Lead with estimated listing pressure and the model settings used.
2. Address errors, then conflicts and large entries with clear improvement options.
3. Explain SR030 as a prediction of reduced routing information. Avoid describing a
   name-only skill as impossible to invoke or claiming a description is already absent
   from the user's live session.
4. Use invocation evidence alongside requested and retained cost. State that a recent
   installation can explain zero observations and unavailable history makes counts unknown.
5. Treat description-overlap and trigger-language findings as review prompts. Confirm
   what each skill is intended to do before recommending a rewrite or removal.
6. Explain that `--portable` checks a supported subset of the specification. SR009 may
   report valid YAML outside the parser's supported subset; consult a full YAML/host
   validator instead of asserting that the host rejects it.

No-path discovery is for Claude Code. Explicit paths for Codex, Cursor or other harnesses
still use Claude listing assumptions, so describe those results as a library estimate.

Do not delete or edit any skill without the user asking for that specific change.

Read `docs/RULES.md` in this directory before explaining a finding you are unsure about.
