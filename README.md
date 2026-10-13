# skillrot

**Audit a Claude Code skill library before it grows beyond its listing budget.**

skillrot estimates listing pressure, finds command conflicts and frontmatter problems,
and counts invocations in available local transcripts. Run it on your installed Claude
Code skills, a library you are reviewing, or a pull request. It reads files locally and
uses no model or network service.

One Python file. Zero runtime dependencies. Python 3.9+.

This README documents version `0.4.0`. Find published tags and artifacts in
[GitHub Releases](https://github.com/Galactic717/skillrot/releases), compatibility
changes in [CHANGELOG.md](CHANGELOG.md), and build/publication steps in
[docs/RELEASE.md](docs/RELEASE.md).

## Try it

From a checkout of this repository:

```bash
python skillrot.py ./skills --no-usage
python skillrot.py ./skills --no-usage --json
python skillrot.py ./skills --no-usage --svg budget.svg
```

To install this checkout into a virtual environment:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install .
skillrot --version
skillrot ./skills --no-usage
```

To install the matching tagged release:

```bash
python -m pip install "git+https://github.com/Galactic717/skillrot.git@v0.4.0"
skillrot --version
```

Use the checkout instructions above during release preparation; the pinned command
requires the matching public tag. Releases before 0.4 do not contain the 0.4 changes.
Installing from Git needs Git and build-time packaging tools. A downloaded release
wheel can instead be installed with `python -m pip install /path/to/skillrot-0.4.0-py3-none-any.whl`.
Once installed, the CLI has no third-party runtime dependencies. On systems where
Python is named `python3`, use that command in the examples.

## Use it as a Claude Code skill

From this checkout, copy `SKILL.md`, `skillrot.py`, and `docs/RULES.md` into a personal
skill directory. On Linux/macOS or Git Bash:

```bash
mkdir -p ~/.claude/skills/skillrot/docs
cp SKILL.md skillrot.py ~/.claude/skills/skillrot/
cp docs/RULES.md ~/.claude/skills/skillrot/docs/
```

In Windows PowerShell:

```powershell
$skillrotDir = Join-Path $env:USERPROFILE '.claude\skills\skillrot'
New-Item -ItemType Directory -Force -Path (Join-Path $skillrotDir 'docs') | Out-Null
Copy-Item SKILL.md, skillrot.py -Destination $skillrotDir
Copy-Item docs/RULES.md -Destination (Join-Path $skillrotDir 'docs')
```

Start a new Claude Code session and invoke `/skillrot`. The skill uses the same CLI;
its instructions explain how to interpret estimates and incomplete usage evidence.

For a verified standalone archive, build the local delivery profile:

```bash
python scripts/build_skill_bundle.py --profile local --output-dir dist
```

Unpack `skillrot-0.4.0-local.zip` into the agent's skill directory. Its single `skillrot/`
folder includes the CLI, instructions, rules, README, license and SHA256 manifest.
For other harnesses, locate the bundled script through its real absolute path and
supply an explicit library path; the budget remains a Claude Code estimate.

Agensi now also delivers instructions through MCP, which does not guarantee local
supporting files. Build the separate upload profile with `--profile agensi`. It uses a
separately installed public CLI and documents the Python/local-shell requirements.
See [marketplace/skillrot/README.md](marketplace/skillrot/README.md). The connector's live
execution and marketplace review are separate checks; this checkout does not claim
they have passed.

## Read the report

Claude Code documents a skill listing budget that defaults to 1% of the model's context
window. It retains names and can omit descriptions when the listing exceeds the budget,
starting with less-used skills. skillrot models that behavior using estimated tokens.
[Claude Code skills reference](https://code.claude.com/docs/en/skills).

The report separates three quantities:

- **Requested listing:** eligible names and descriptions before budget pressure.
- **Estimated retained listing:** names plus descriptions predicted to fit. SR030 marks
  entries predicted to be listed by name only; the name remains available to the model.
- **Body size:** content that may load when a skill is invoked. This is a potential load
  size, not a measured session bill or a guarantee about later context retention.

If the library exceeds the budget, inspect SR030 and the heaviest descriptions. Shorten
descriptions while preserving their triggers, remove accidental duplicates, or use Claude
Code's invocation controls and `skillOverrides` for entries you want to hide or invoke
manually. Re-run with the same options to compare the result. A name-only prediction is
evidence of reduced routing information, not proof that a skill can never be invoked.

## Usage

```bash
skillrot                          # discover installed Claude Code entries
skillrot ./skills                 # recursively audit a directory
skillrot ./skills/notes/SKILL.md   # audit a single file
skillrot ./marketplace            # respect local plugin/marketplace manifests
skillrot ./repo --all             # recursive scan, ignoring manifest file selection
skillrot --no-usage               # skip transcript scanning
skillrot --transcripts ./history  # use a selected transcript directory
skillrot --context-window 1000000 # model a different context window
skillrot --budget-fraction 0.02   # model a different listing fraction
skillrot --portable               # check supported Agent Skills constraints
skillrot --json                   # structured report on stdout
skillrot --svg budget.svg         # export a shareable SVG
skillrot --full                   # show every finding in the text report
skillrot --fail-on error          # gate error findings
skillrot --fail-over-budget       # gate estimated listing overflow
```

With no paths, discovery uses Claude Code's personal and project `.claude/skills`, legacy
`.claude/commands`, and enabled plugins resolved through the local installation cache or
directory marketplaces. Project discovery walks from the working directory to the Git
root. Settings influence listing overrides and budget configuration. Bundled skills and
skills synced from claude.ai may be unavailable on disk and are not counted.
This inventory is a supported profile, not a complete replica of the runtime loader.
The shallow skill-directory scan omits `@skills-dir` plugins stored as a plugin root
inside `.claude/skills` with nested `skills/` entries, including such synced wrappers.
Pass that plugin root explicitly to inspect its local manifest, or use `--all` for a
recursive library audit. Managed settings, additional directories supplied at launch,
and session-dependent skills are outside the default inventory.

`--all` bypasses manifest selection of skill files, while ownership manifests may
still be read and validated to determine command namespaces. It is not a bypass for
malformed plugin ownership metadata.

Inventory directory read errors are operational failures (exit 2), so an inaccessible
subtree cannot silently pass as a complete library audit. Recursive scans skip child
directory symlinks and Windows reparse points; an explicitly supplied linked root is
followed. The shallow installed-skill profile also supports linked skill directories.

Ambiguous registry records pointing to different existing plugin installations return
exit 2; use an explicit plugin path to select the intended version. Marketplace
`skills`/`commands` extensions alongside `plugin.json` are diagnosed as unsupported
rather than omitted. A `strict:false` component conflict is an operational error.

Other harnesses' directories can be audited explicitly, for example
`skillrot ~/.codex/skills --no-usage`. Their files are linted and modeled using **Claude
Code's** listing assumptions; this is not a measurement of Codex or Cursor's runtime.

Explicit paths are library audits and do not inherit local Claude settings. Use
`--budget-fraction` and `--context-window` to model the intended deployment. The
`SLASH_COMMAND_TOOL_CHAR_BUDGET` environment variable is honored unless an explicit
budget fraction is supplied.

## Estimates and evidence

Token estimates use four characters per token by default; adjust `--chars-per-token` if
needed. They are useful for comparing library sizes and finding large entries. Exact
tokenization, model window size, loader behavior, and missing on-disk entries can change
the result. skillrot does not inspect a live Claude session or measure invocation quality.

The listing entry cap is modeled at 1,536 characters. A local
`skillListingMaxDescChars` setting that changes that cap is an unsupported profile and
returns exit 2, rather than silently applying the wrong cap.

The same files, settings, usage evidence, environment and options produce the same
report. With `--no-usage`, the model has no invocation evidence and uses a deterministic
ordering for descriptions. This cannot identify the exact descriptions a live session
would omit.

Usage scanning reads `~/.claude/projects/**/*.jsonl` by default. Zero counted invocations
means none were observed in the available history; recent installs, missing transcripts,
and other harnesses' histories can all explain it. When no usable invocation evidence is
available, counts are unknown (null in JSON) and SR024 is not emitted. No usage data leaves
the machine.

An explicitly requested `--transcripts` path must be an existing directory unless
`--no-usage` disables scanning. Missing default history remains unknown evidence.

## Frontmatter and portability

The parser supports a bounded YAML subset: scalar fields, quoted strings, block scalars,
and supported field-specific lists/maps. Invalid syntax and valid YAML outside that
subset produce SR009, rather than a confident report from partially parsed frontmatter.
SR009 asks you to simplify the frontmatter or validate it with a full YAML/host validator.
Finding severities are audit policies. Claude Code can load plain Markdown or ignore
invalid frontmatter and use defaults; an error finding here does not always mean the
host refuses to load the file.

`--portable` checks the supported Agent Skills requirements for names, descriptions,
field types and limits. It does not validate every packaging rule, every resource
reference, or the behavior of a skill. Passing is not an upload guarantee. Use the host's
validator before distributing a skill. The
[Agent Skills specification](https://agentskills.io/specification) is the reference for
portable constraints.

| Rule | Default severity | What it checks |
| --- | --- | --- |
| SR001 | error | Missing frontmatter or opening delimiter not on line 1 |
| SR002 | warn; error with `--portable` | Missing/empty description; Claude can use a body fallback |
| SR003 | error | Listing text beyond the modeled 1,536-character entry cap |
| SR004 | error | Both automatic and direct user invocation disabled |
| SR005 | warn | Non-boolean invocation field |
| SR006–SR009 | error | Unterminated/unreadable file, symlink stub, invalid or unsupported YAML |
| SR010, SR011, SR013 | error with `--portable` | Allowed fields, compatibility limit and names |
| SR014 | error | Core string field types; additional portable types and limits with `--portable` |
| SR012 | info | Unrecognized top-level field |
| SR020 | warn | Conflicting command names |
| SR021 | warn | Similar descriptions; heuristic review prompt |
| SR022 | warn | Trigger language absent; heuristic review prompt |
| SR023 | warn | Body exceeds the configured line threshold |
| SR024 | info | No invocation observed in available history |
| SR025 | warn | Very short description |
| SR030 | info | Description predicted to be omitted from the modeled listing |

[docs/RULES.md](docs/RULES.md) explains each rule and its limits.

## JSON and CI

```bash
python skillrot.py .claude/skills --portable --no-usage --json --fail-on error --fail-over-budget
```

Exit status is part of the CLI contract:

| Exit | Meaning |
| ---: | --- |
| 0 | Audit completed; requested finding/budget gates passed |
| 1 | Audit completed; a requested finding or budget gate failed |
| 2 | Invalid arguments, unavailable inputs, or failed output operation |

`--json` writes one report to stdout when an audit completes; diagnostics go to stderr.
Argument and operational failures may produce no JSON. Check the exit status before
using a report. JSON string escapes keep reports portable through legacy output encodings.

SVG output refuses aliases of discovered skill/command files, including hardlinks.
Other explicitly requested output paths remain ordinary filesystem writes; choose a
report filename. This is not a general filesystem sandbox.

The JSON contract has `schema_version: 1`, the tool `version`, `model`, `budget`, `skills`
and `findings`. `model` records the Claude Code assumption, estimated status, token
divisor and whether usable invocation evidence is available. `budget.skills` counts discovered entries
including commands; `budget.commands` is the command subset. Per-entry `listing_tokens`
describes eligible requested cost, and `retained_listing_tokens` describes estimated cost
after deduplication and budget pressure. Hidden entries cost zero in the listing.
`invocations` is null when usage scanning is disabled or no usable evidence is available.
Findings contain `rule`, `severity`,
`command`, `path`, `message` and `fix`. Consumers should tolerate additive fields and
check `schema_version` before relying on the contract. JSON includes estimates and file
paths, not a complete listing string for a tokenizer.

CI runs source tests and installed-package smoke checks on Linux, macOS and Windows.
The weekly [live audit workflow](.github/workflows/live-audit.yml) reports findings on
five public libraries and saves text, JSON, SVG and provenance with target/tool commits,
options and a UTC timestamp. Findings are reports; operational failures fail the job.

## Related tools

[skillscore](https://github.com/sayed3li97/skillscore) also provides offline skill linting,
token estimates, conflict checks and CI reports. skillrot focuses on a Python file with
no runtime dependencies, a Claude listing-budget model, local discovery and transcript
evidence. Choose the reporting format and authoring checks your workflow needs.

Claude Code's `/skill-doctor`, `claude plugin validate`, and `claude plugin eval` provide
host-specific diagnostics, validation and evaluation. Availability depends on your
Claude Code version. They complement this offline audit; use runtime evaluation to test
whether a skill actually fires and performs the intended task.
[Claude Code skills reference](https://code.claude.com/docs/en/skills).

## Historical examples

The [current controlled example](docs/examples/README.md) includes before/after fixtures,
JSON/text/SVG reports and file hashes under `docs/runs/current-example/`. It demonstrates
listing estimates and duplicate cleanup with the same model options in both cases.
It does not measure live routing or customer savings.

The [September 28 audit](docs/runs/live-audit-2026-09-28.md) and
[explainer assets](docs/demo/explainer.html) were generated for v0.3.0 using its earlier
model. They are retained as historical examples, not current output or evidence of
actual session routing. The original target commits were not recorded, so those figures
cannot be reproduced exactly from the report alone. New workflow runs preserve provenance.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for tests and packaging checks, and
[CHANGELOG.md](CHANGELOG.md) for compatibility changes. [docs/RELEASE.md](docs/RELEASE.md)
describes the release process. [SECURITY.md](SECURITY.md) covers data handling and
issue reporting. MIT — [LICENSE](LICENSE).
