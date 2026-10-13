# skillrot: public product copy

## Marketplace description

Audit your agent's skill library before adding another skill.

skillrot estimates Claude Code listing pressure, finds conflicting command names
and frontmatter problems, and checks available local invocation evidence. Compare
an edit using JSON or SVG reports, or add finding and budget gates to CI.

One Python file. Zero runtime dependencies. Python 3.9+. MIT license.
The audit reads local files and uses no model or network service.

The Agensi workflow requires a separately installed skillrot CLI 0.4+ and a local
shell. Its setup instructions are included in the skill. For Codex, Cursor or another
agent, supply an explicit skill directory; the budget model still uses Claude Code
assumptions. MCP delivery alone does not grant access to local files.

## Short listing

> Find skill-library conflicts, frontmatter problems and estimated Claude Code
> listing pressure. Offline Python audit with JSON, SVG and CI gates.

Suggested category: Prompt & Skill Engineering. Suggested tags: Claude Code,
agent skills, context, linting, code quality, CI, Python, offline.

The initial marketplace workflow is Free. The CLI and both delivery profiles remain
MIT software; the marketplace workflow supplies guided setup and interpretation.

## Example and limits

The [controlled before/after example](docs/examples/README.md) changes requested
listing estimates from 339 to 46 tokens under the same deliberately small 80-token
example budget. It removes a duplicate command and narrows repeated descriptions.
The inputs, commands and source hashes are recorded with the reports. Skillrot does
not edit the library automatically, measure live routing, or convert these estimates
into measured spending or customer savings.

Predicted name-only entries retain their names and may still be invoked. A clean
portable audit checks the supported specification subset; it does not guarantee
marketplace acceptance or skill quality.

## Launch post

> Before adding another Claude Code skill, check what your library asks the listing
> budget to hold. skillrot finds estimated listing pressure, command conflicts and
> frontmatter problems using local files. Offline Python, zero runtime dependencies,
> JSON/SVG reports and CI gates.
>
> Source and setup: https://github.com/Galactic717/skillrot

Use the matching published release instructions. [docs/RELEASE.md](docs/RELEASE.md)
describes artifact verification and publication. Historical September demo media
uses an earlier model and is not evidence for current results.
