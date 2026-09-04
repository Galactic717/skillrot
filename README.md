# skillrot

**Every skill you install is a tax on every message you send.** Whether it fires or not.

`skillrot` reads your agent's skill library and tells you what it actually costs, which
skills can never run, and which SKILL.md mistakes are silently breaking the ones you care
about.

Zero dependencies. One file. Python 3.9+.

```
$ skillrot

skillrot 0.1.0

  Context bill
    45 skills discovered
    ~4,713 tokens in the always-on listing  (2.4% of a 200,000-token window)
    ~137,728 tokens of skill bodies waiting to load
    3.0MB on disk

  Heaviest listings  (paid on every message)
      231 tok  /project-artifact:project-artifact  never fired
      218 tok  /figma:figma-generate-design       never fired
      209 tok  /video-interaction-mapper          never fired

  Findings

  WARN
    SR021 /discord:access
      3 skills share a near-identical description (80%+ word overlap):
      /discord:access, /imessage:access, /telegram:access.
      The router picks between them on a coin flip.
      fix: Differentiate the triggers, or merge them into one skill.

    SR022 /frontend-design:frontend-design
      Description never says *when* to use the skill, only what it is.
      fix: Append a trigger clause: 'Use when the user asks to ...'.

  0 error(s), 12 warning(s), 45 skill(s) never fired
```

Point it at one of the 5,000-skill mega-collections people install wholesale and the
number stops being cute:

```
$ skillrot ./some-awesome-skills-collection

    4542 skills discovered
    ~204,946 tokens in the always-on listing  (102.5% of a 200,000-token window)
```

That library does not fit in the context window it is supposed to leave room for.

## Install

```bash
curl -O https://raw.githubusercontent.com/Galactic717/skillrot/main/skillrot.py
python skillrot.py
```

Or:

```bash
pip install git+https://github.com/Galactic717/skillrot
skillrot
```

## Usage

```bash
skillrot                      # audit every skill installed on this machine
skillrot ./skills             # audit a directory
skillrot ./skills/x/SKILL.md  # audit one skill
skillrot --portable           # check it will survive a claude.ai / Skills API upload
skillrot --json               # machine-readable, for scripts and CI
skillrot --fail-on error      # non-zero exit when something is broken
skillrot --full               # print every finding, not the first 20 per rule
skillrot --no-usage           # skip the transcript scan
```

By default it looks in `~/.claude/skills`, `~/.claude/plugins`, `~/.codex/skills`,
`~/.cursor/skills`, `~/.config/agent-skills` and `./.claude/skills`. Anywhere else, pass
the path.

## What it measures

**The always-on bill.** A skill's name and description sit in the model's context on
every request so it can decide whether to reach for the skill. The body only loads when
the skill fires — but once it does, it stays there for the rest of the session. skillrot
separates the two, because they are very different kinds of expensive.

**Which skills have actually fired.** skillrot reads your local Claude Code transcripts
(`~/.claude/projects/**/*.jsonl`) and counts real invocations. A skill you installed six
months ago and never triggered once is charging you rent on every message. Nothing leaves
your machine.

**Whether a skill can fire at all.** A description with no trigger clause, a description
past the 1,536-character cap, frontmatter that doesn't start on line 1, or the
`disable-model-invocation` + `user-invocable: false` combination that locks a skill out
of both invocation paths.

**Whether two skills are fighting.** Install four marketplace bundles and you end up with
several skills whose descriptions are near-identical. The router picks one. It is not
necessarily the one you wanted.

## Rules

| Rule | Severity | What it catches |
| --- | --- | --- |
| SR001 | error | Frontmatter missing, or not starting on line 1 |
| SR002 | error | No `description` |
| SR003 | error | `description` + `when_to_use` past the 1,536-char listing cap |
| SR004 | error | `disable-model-invocation: true` **and** `user-invocable: false` — unreachable |
| SR006 | error | Frontmatter opens but never closes |
| SR007 | error | File cannot be read |
| SR008 | error | Git symlink checked out as a plain text file |
| SR010 | error | Frontmatter field outside the Agent Skills spec (`--portable`) |
| SR011 | warn | `compatibility` over 500 characters (`--portable`) |
| SR005 | warn | Non-boolean value in a boolean field |
| SR020 | warn | Two skills answering to the same command |
| SR021 | warn | Near-identical descriptions competing for the same trigger |
| SR022 | warn | Description says what a skill is, never when to use it |
| SR023 | warn | Oversized body that squats in context once loaded |
| SR025 | warn | Description too thin to route on |
| SR012 | info | Unrecognized frontmatter field |
| SR024 | info | Never invoked in any local transcript |

[docs/RULES.md](docs/RULES.md) has the reasoning and the spec citation behind each one.

## Token numbers are estimates

skillrot has no dependencies, which means no tokenizer. It estimates at 4 characters per
token — close enough to rank offenders and size the problem, not exact. Tune it with
`--chars-per-token`, or pipe `--json` into a real tokenizer if you need precision. The
ranking is what matters; the absolute number is a good-enough approximation.

Exact context accounting also varies between harnesses and versions. skillrot measures
the text the Agent Skills spec says goes into the listing, truncated the way the spec
says it is truncated.

## Use it in CI

```yaml
- run: python skillrot.py .claude/skills --portable --no-usage --fail-on error
```

Catches the frontmatter mistakes that silently ship a dead skill, and the non-spec fields
that make a `claude.ai` upload fail outright.

## Use it as a skill

`SKILL.md` in this repo makes skillrot available to your agent. Drop the repo in
`~/.claude/skills/skillrot/` and ask it to audit your library.

## Contributing

New rules are welcome, with two requirements: a citation for the behaviour it catches,
and a test. Run the suite with:

```bash
python -m unittest discover -s tests
```

## License

MIT
