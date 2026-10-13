# Contributing

Keep the CLI as one source file with no runtime dependencies. Changes to parsing,
discovery, accounting, findings or exit behavior need a regression that exercises the
user-visible behavior. Cite a host/specification requirement for a normative rule and
label heuristics as heuristics.

## Source checks

```bash
python -m unittest discover -s tests -v
python skillrot.py SKILL.md --portable --no-usage --fail-on error
```

CI also runs `mypy==2.2.0` on Python 3.13. Type checking and packaging tools are developer
dependencies; the shipped CLI has none.

## Distribution checks

In a development environment with the `build` frontend installed:

```bash
python -m pip install build
python -m build
python scripts/smoke_package.py dist
```

Use a clean distribution output directory, or pass a new directory to `python -m build
--outdir` and the same path to the smoke runner. The runner expects exactly one wheel and
one source archive. It creates a temporary virtual environment, installs the local wheel
without network access or dependencies, and runs the installed command outside the
checkout. Checks cover version/help, JSON, SVG, finding/budget gates, missing inputs,
invalid numeric options and Unicode output through a legacy encoding.

The source-distribution smoke also extracts the sdist, runs its included source tests,
and builds both skill profiles from that extracted tree. A wheel that runs while its
sdist omits delivery resources is an incomplete source release.

`python -m build` builds the wheel from the generated source archive, so both delivery
formats are exercised. The platform matrix includes Linux, macOS and Windows on Python
3.9, 3.12, 3.13 and 3.14. Python 3.9 receives compatible versions of build-time tooling
from pip's resolver; it remains the CLI's minimum runtime version.

## Compatibility and evidence

Preserve existing JSON fields and rule identifiers where practical. Record changed
semantics in `CHANGELOG.md`; consumers use `schema_version` and should tolerate additive
fields. Keep exit 0 for a completed passing audit, exit 1 for an opted-in finding/budget
gate, and exit 2 for usage/operational failures.

For public examples, record target/tool commits, options and a UTC timestamp. The live
audit workflow captures these in a `.provenance.json` artifact. GitHub artifact retention
is finite, so preserve the compact provenance beside any permanent published numbers.
Do not present a modeled budget or lexical heuristic as a measured runtime result.

## Skill archives and audit documentation

```bash
python scripts/build_skill_bundle.py --profile local --output-dir dist
python scripts/build_skill_bundle.py --profile agensi --output-dir dist
python scripts/source_atlas.py
```

The bundle tests extract the actual local archive and run its CLI outside the checkout.
Archives use explicit text-resource allowlists, fixed ZIP metadata and SHA256 manifests.
The Agensi workflow uses a separately installed public CLI because MCP delivery does
not guarantee local supporting files. Test connector activation separately before
claiming live agent compatibility.

The source atlas is generated documentation, not a runtime dependency or proof of
correctness. Rebuild it after changing source files; its inventory hashes and line
counts must describe the delivered tree. Human algorithm analysis is maintained in
`docs/CORE_REVERSE_ENGINEERING.md` and `docs/DELIVERY_REVERSE_ENGINEERING.md`.

Do not publish a release or marketplace listing with references to an unavailable
version. Release preparation, remote CI, artifact publication and Agensi review are
separate states described in `docs/RELEASE.md`.
