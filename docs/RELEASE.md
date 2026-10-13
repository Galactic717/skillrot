# Release process

Skillrot ships an offline Python CLI and two Agent Skill delivery profiles.
This process targets version 0.4.0. Publish the matching CLI before listing the
Agensi workflow, which requires that separately installed CLI. During release
preparation, install from the source checkout with `python -m pip install .`.

## Validate source and distributions

Run from the checkout in a development virtual environment:

```bash
python -m unittest discover -s tests -v
python skillrot.py SKILL.md --portable --no-usage --fail-on error
python skillrot.py marketplace/skillrot/SKILL.md --portable --no-usage --fail-on error
python -m pip install build
python -m build --outdir dist/release-0.4.0
python scripts/smoke_package.py dist/release-0.4.0
python scripts/build_skill_bundle.py --profile local --output-dir dist/release-0.4.0
python scripts/build_skill_bundle.py --profile agensi --output-dir dist/release-0.4.0
python -m unittest discover -s tests -p test_skill_bundle.py -v
```

Use a clean output directory containing exactly one wheel and one source archive
for the smoke runner. It checks the installed CLI outside the checkout, extracts
the sdist, runs its source tests, and builds both skill profiles. The bundle suite
checks exact resources, deterministic bytes, hashes, extracted execution and portable
frontmatter. CI covers Linux, macOS and Windows with Python 3.9, 3.12, 3.13 and 3.14.
Developer build/type tools are separate from the CLI's zero runtime dependencies.

## Verify examples and publish

The [controlled example](examples/README.md) uses identical options before and after.
Its compact [provenance](runs/current-example/provenance.json) identifies the inputs,
CLI hash, assumptions, commands and observed outputs. Recreate it when the source or
fixtures change; do not advertise historical output as new evidence.

1. Review an explicit source-file list, commit it, and run the remote CI matrix.
2. Tag the verified source commit, then publish the GitHub release with the wheel,
   sdist, local skill ZIP and Agensi workflow ZIP. Attach SHA256 checksums and metadata
   describing the actual artifact bytes and source state.
3. Update release/setup wording to describe the real published version. Rebuild
   artifacts if a packaged README or wrapper changes; do not retain old checksums.
4. Verify the version-pinned public installation from outside the checkout and confirm
   the installed version before submitting the marketplace archive.
5. Submit the Agensi workflow, then verify marketplace review and actual delivery
   separately. Claim host compatibility only after a real host acceptance run.

Published source tags and uploaded assets must identify the same implementation.
The marketplace price does not change the project's MIT license.

## Consumer installation

Install the matching public tag in an activated Python virtual environment:

```bash
python -m pip install "git+https://github.com/Galactic717/skillrot.git@v0.4.0"
skillrot --version
skillrot "/path/to/skills" --no-usage --json
```

Git installation needs Git and build-time packaging tools. The release wheel is a
Git-free alternative: download it from the real GitHub release and install its local
path with pip. Initial installation can use the network; auditing remains local.

The standalone local ZIP carries the CLI beside `SKILL.md`. The Agensi ZIP carries
instructions, references and license only: MCP resources are not guaranteed executable
local files. A host without a local shell needs the user to run the audit and provide
the report. See [the Agensi workflow README](../marketplace/skillrot/README.md).
