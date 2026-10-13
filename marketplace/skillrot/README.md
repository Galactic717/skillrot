# skillrot: Agensi workflow

This MIT package helps an agent interpret an offline skill-library audit. It contains
instructions and a rule reference. The CLI is a separate, public MIT project:
[Galactic717/skillrot](https://github.com/Galactic717/skillrot).

The workflow requires Python 3.9+, skillrot CLI 0.4+, and a shell with access to the
user's local library. An Agensi MCP resource does not imply executable installation
or filesystem access. If local execution is unavailable, run the audit on your own
computer and share the resulting report with the agent.

## Version and setup

This workflow targets CLI version 0.4.0. Install the matching release from the
public repository using the pinned Git tag below. Releases before 0.4 do not contain
these contracts. Git installation requires the tag to exist and does not use a
PyPI package named skillrot.

Create and activate a virtual environment, then install the matching public release:

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install "git+https://github.com/Galactic717/skillrot.git@v0.4.0"
skillrot --version
skillrot "/path/to/skills" --no-usage --json
```

Use `python3` where that is the Python command. From a source checkout, run
`python -m pip install .` in the directory containing `pyproject.toml`. A downloaded
release wheel can be installed directly without Git. Initial setup may need Git,
build-time packaging tools and a network connection. Auditing uses no model,
account or network service. Verify `skillrot --version` reports 0.4 or newer.

## Scope and privacy

No-path discovery models installed Claude Code entries. Supply other agents' skill
directories explicitly; their reports still use estimated Claude listing assumptions.
`--no-usage` skips transcript access. When requested, invocation scanning reads selected
Claude JSONL histories locally and sends nothing to a service. JSON reports include
local paths; review them before sharing.

The workflow explains frontmatter problems, command conflicts, listing estimates,
unknown versus zero usage, and practical changes. It does not measure live routing,
guarantee savings, validate every host or automatically edit a user's library.

`references/RULES.md` explains each finding. `LICENSE` grants MIT terms. Resource
hashes and delivery version are recorded in `manifest.json`; this is integrity metadata,
not a cryptographic signature. Installation and marketplace approval remain separate
from a successful local audit.
