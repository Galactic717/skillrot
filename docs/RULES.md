# Rules

Rules combine documented host/specification constraints with review heuristics. A finding
is evidence for the check described below; it is not a measurement of a live model's
routing or proof that every host will reject a file.

References checked on 2026-10-08:

- [Claude Code skills reference](https://code.claude.com/docs/en/skills) — Claude-specific
  fields, invocation controls and listing behavior.
- [Agent Skills specification](https://agentskills.io/specification) — portable field
  requirements, types, limits and recommended body structure.

The parser supports a bounded YAML subset. SR009 distinguishes unsupported input from a
successful parse. A valid construct outside that subset needs a full YAML/host validator.

## Frontmatter and input

### SR001 — frontmatter missing or not on line 1 · error

The audit requires opening `---` on the first line. This makes metadata explicit and
avoids interpreting a body as intended frontmatter. A host may fall back to body text;
this finding does not establish that the skill is impossible to invoke.

### SR002 — missing or empty description · warn; portable error

Claude Code can use the first non-empty body line when `description` is omitted. A warning
prompts you to supply deliberate routing text. The Agent Skills specification requires a
non-empty description, so `--portable` raises the same finding to an error.

### SR003 — listing text beyond the modeled entry cap · error

The Claude Code reference documents truncation of combined `description` and
`when_to_use` listing text at 1,536 characters. Place useful trigger text before that
cutoff. This is separate from the portable 1,024-character description limit in SR014.

### SR004 — both invocation controls disabled · error

Combining `disable-model-invocation: true` with `user-invocable: false` disables the
normal automatic and direct user invocation paths. Review whether one of those paths
should remain available. Disabled automatic invocation also keeps the description out
of the modeled listing; this is not a claim that a disabled skill costs listing tokens.

### SR005 — invalid boolean field · warn

The invocation fields need boolean values. The parser recognizes the supported boolean
spellings; other values do not express a reliable enabled/disabled intent. Prefer
`true` and `false` for clarity.

### SR006 — unterminated frontmatter · error

The opening delimiter has no closing `---`. Repair the block before relying on any
metadata analysis.

### SR007 — unreadable skill · error

The file could not be read, for example due to permissions or encoding. The finding
reports the unavailable input instead of silently omitting its content.

### SR008 — possible symlink checkout stub · error

A path-only file can be the text representation of a Git symlink checked out without
symlink support. The heuristic distinguishes it from ordinary missing frontmatter.
Verify the Git entry and target; if it is a symlink, restore or re-clone with symlinks
supported. A path-only body is not definitive proof of a checkout problem.

### SR009 — invalid or unsupported YAML subset · error

The parser cannot safely interpret the frontmatter. Causes include invalid syntax,
duplicate keys, and constructs outside the supported scalar/list/map subset. Do not use
partially parsed fields as proof of validity or estimated listing cost. Simplify the
frontmatter or use a full YAML parser and the target host's validator. This rule can
report valid YAML that the target host supports.

## Portable checks (`--portable`)

### SR010 — unsupported top-level field · error

The Agent Skills specification defines `name`, `description`, `license`, `compatibility`,
`metadata` and `allowed-tools`. Other top-level fields fail this portable check, including
quoted keys. Claude-specific invocation controls remain legitimate in a Claude-only
skill; move custom authoring data under `metadata` when portability matters.

### SR011 — compatibility exceeds 500 characters · error

The optional `compatibility` scalar has a 500-character limit in the Agent Skills
specification. Keep environment requirements concise.

### SR013 — invalid portable name · error

A portable `name` is required, is 1–64 characters, uses lowercase letters/digits and
hyphens, has no leading/trailing/consecutive hyphens, and matches the containing skill
directory. This is a publishing constraint, not a requirement to rename every
Claude-specific command.

### SR014 — field type or limit violation · error

The core `name`, `description` and `when_to_use` fields must be strings in both audit
modes. With `--portable`, `license`, `compatibility` and `allowed-tools` also require
scalar strings. The required description must be non-empty and at most 1,024 characters;
provided compatibility text must be non-empty. `metadata` is a map with string values.
Claude-specific list forms may be valid for the host while failing portable constraints.

These checks cover supported frontmatter requirements. They do not validate complete
upload archives, referenced resources, every YAML construct, or runtime behavior. Passing
`--portable` should be followed by the intended host's validation.

## Library review

### SR012 — unrecognized top-level field · info

A field outside the supported Claude/specification set can be a typo or custom metadata.
Inspect it and place custom values under `metadata` when appropriate.

### SR020 — conflicting command names · warn

Multiple entries resolve to the same command. Claude Code documents precedence between
personal, project and plugin skills. The audit reports the conflict so you can confirm
which entry should win; it does not know which duplicate you intended to invoke.

### SR021 — similar descriptions · warn

A lexical overlap heuristic groups descriptions that may need clearer distinctions.
Similar descriptions do not prove random routing or an invocation failure. Review each
entry's scope and sharpen its trigger if necessary. `--similarity` sets the threshold.
Exact non-empty word sets are preserved at any collection size. Candidate pruning
can miss non-identical pairs whose overlap consists only of very common words; a
clean result is not proof that every description has a distinct purpose.

### SR022 — trigger language absent · warn

Descriptions should communicate both the task and when it applies. The heuristic looks
for phrases such as “use when”; a useful description can express its trigger differently.
Treat the finding as a writing review prompt.

### SR023 — body over the line threshold · warn

A large body can cost more context when loaded. The default threshold is 500 non-blank lines,
consistent with the specification's progressive-disclosure guidance. Use supporting
files for material needed only on demand, or adjust `--body-lines` to your workflow.
This does not measure how long the body remains in a session after compaction.

### SR024 — no observed invocation · info

The audit scans available Claude JSONL transcripts for recognized `Skill` tool calls and
user-typed commands. Zero observations can mean a recent install, missing/incomplete
history, a format the scanner does not recognize, or no use. It is not proof the skill is
useless. Reads stay local; `--no-usage` disables them. When no usable invocation evidence
is available, JSON reports null invocations and SR024 is not emitted.

### SR025 — description under 15 characters · warn

Very short descriptions rarely provide enough task and trigger information. This is a
length heuristic, not a host/specification minimum or proof that routing cannot work.

### SR030 — modeled name-only entry · info

The Claude Code reference documents a listing budget defaulting to 1% of the context
window, with names retained and less-used descriptions omitted when it overflows.
skillrot estimates a retained listing under those assumptions. It excludes automatically
hidden entries, honors supported overrides, deduplicates command names, and accounts for
commands sharing the listing. `name-only` overrides also retain only a name.

SR030 marks descriptions predicted not to fit. Without usage evidence, ordering is a
deterministic model choice, not the live session's exact list. A retained name can still
inform selection and direct invocation may remain possible. Use `--context-window`,
`--budget-fraction` and `--chars-per-token` to match your assumptions. `--fail-over-budget`
turns estimated overflow into a CI gate; SR030 itself is informational.
