# Rules

Every rule exists because of documented behaviour, not taste. Each entry below says what
the rule catches, why it matters, and where the behaviour is specified.

Sources:

- **CC** — Claude Code skills reference, <https://code.claude.com/docs/en/skills>
- **AS** — Agent Skills open standard, <https://agentskills.io>

---

## Errors

### SR001 — frontmatter missing or not on line 1

> Claude Code reads the frontmatter only when the opening `---` is the file's first line.
> Otherwise it treats the whole file, `---` markers included, as skill content. — CC

A single blank line or a stray comment above the `---` turns a working skill into a
description-less blob. It still loads, still costs context, and never fires. This is the
most expensive one-character mistake in the format.

### SR002 — no `description`

> If omitted, uses the first paragraph of markdown content. — CC

The fallback is rarely written to be routed on. Whatever your first paragraph happens to
say becomes the trigger text.

### SR003 — listing text past the cap

> The combined `description` and `when_to_use` text is truncated at 1,536 characters in
> the skill listing to reduce context usage. — CC

Text past the cutoff never reaches the router. If your trigger phrasing is at the end of a
long description, it does not exist as far as skill selection is concerned. Put the
trigger first.

### SR004 — unreachable skill

> `disable-model-invocation`: Set to `true` to prevent Claude from automatically loading
> this skill. — CC
>
> `user-invocable`: Set to `false` when only Claude should invoke the skill: Claude Code
> hides it from the `/` menu and doesn't run it when you type `/name`. — CC

Set both and nothing can run the skill: the model is blocked from auto-loading it and you
are blocked from typing it. It is a file that only costs context.

### SR006 — unterminated frontmatter

An opening `---` with no closing `---`. The parser has no frontmatter block to read.

### SR007 — unreadable file

Permissions or encoding. Reported rather than crashing the run.

### SR008 — symlink checked out as a plain file

Repositories that share skills between directories with git symlinks check out as
one-line text files containing a relative path on systems without symlink support —
Windows, most commonly. The file exists, the skill does not. Distinguished from SR001
because the fix is different: re-clone with symlinks enabled.

### SR010 — non-spec frontmatter field (`--portable` only)

> If you include any field the spec doesn't allow, packaging or upload fails with a hard
> error instead of ignoring the field. — CC

The claude.ai upload path, the Skills API and `package_skill.py` accept exactly six
fields: `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`.
Claude Code accepts many more, so a skill can work perfectly on your machine and fail the
moment you try to share it. Off by default, since Claude Code-only skills are legitimate.

---

## Warnings

### SR005 — non-boolean value in a boolean field

> Boolean fields accept `yes`, `no`, `on`, `off`, `1`, and `0` in any letter case, in
> addition to `true` and `false`. — CC

Anything outside that set is not a boolean, and the field does not do what you think.

### SR011 — `compatibility` over 500 characters (`--portable` only)

> Accepts a string of up to 500 characters. — CC / AS

### SR020 — two skills, one command

> With a `deploy` skill in both `~/.claude/skills/` and your project's `.claude/skills/`,
> `/deploy` runs the personal one. — CC

Shadowing is defined and deterministic, which is exactly why it is easy to miss: the
skill you meant to run is simply never the one that runs.

### SR021 — near-identical descriptions

The router picks a skill by comparing your request to description text. Two skills
describing the same job in the same words make that a coin flip. Install several
marketplace bundles and this happens on its own, without anyone deciding it should.

skillrot groups the whole overlapping set into one finding rather than reporting every
pair, and compares only skills that share discriminating words, so a 4,500-skill library
still finishes in seconds. Tune the threshold with `--similarity`.

### SR022 — description without a trigger

> `description`: What the skill does **and when to use it**. Claude uses this to decide
> when to apply the skill. — CC

"A tool for formatting tables" tells the router what the skill is. It does not tell it
when to reach for one. The heuristic looks for trigger language ("use when", "when the
user", and similar); it is a lint, not a proof, and a description can be well-targeted
without those exact words.

### SR023 — oversized body

> Once a skill loads, its content stays in context across turns, so every line is a
> recurring token cost. — CC

A 600-line skill that fires once early in a session is charged to every turn afterwards.
Supporting files the skill reads on demand cost nothing until they are read.

### SR025 — description too thin

Under 15 characters cannot carry both what a skill does and when to use it.

---

## Info

### SR012 — unrecognized frontmatter field

> `metadata`: Free-form YAML map for your own key-value data ... Don't reuse frontmatter
> field names such as `paths` as keys. — CC

Custom top-level keys like `tags:` or `author:` are not part of either the Claude Code
set or the spec. They are usually harmless, sometimes a typo of a real field, and belong
under `metadata:`.

### SR024 — never invoked

Counted from `"name":"Skill"` tool calls in local Claude Code transcripts under
`~/.claude/projects/`. Evidence of absence in *your* history, not proof a skill is
useless: a skill installed yesterday has not fired yet either. Read it alongside the
listing cost — a cheap skill that never fires is fine, an expensive one is rent.

Transcripts are read locally and never leave the machine. Turn the scan off with
`--no-usage`.

### SR030 — listed name-only (description dropped from the budget)

> Claude Code loads a listing of skill names and descriptions into context... The
> listing always contains every skill name, but if you have many skills, Claude Code
> drops some descriptions to fit the listing's character budget... The budget scales at
> 1% of the model's context window. When the listing overflows, Claude Code drops
> descriptions starting with the skills you invoke least. — CC

This is the failure that bites big libraries: not that a single skill is malformed, but
that the *collection* overflows the listing budget, so Claude Code lists some skills by
name only. A name-only skill has no description in context, so the router cannot match it
to a request by keyword — it is installed, it costs its name in tokens on every message,
and it is effectively unroutable.

skillrot models the same budget Claude Code applies: names are always kept, then
descriptions fill the remaining budget most-used first (the least-used are dropped). The
budget is 1% of the context window by default; change it with `--budget-fraction` (to
match `skillListingBudgetFraction`) or `--context-window`.

This is the total-listing counterpart to SR003: SR003 catches one skill whose own
description runs past the 1,536-character *per-entry* cap; SR030 catches skills whose
descriptions do not fit the *whole-listing* budget once every other skill is counted. A
real-world instance: a widely-used library shipped 46 skills whose descriptions summed to
roughly three times the budget, and Claude Code silently dropped most of them at session
start.
