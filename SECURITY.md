# Security policy

Skillrot performs static file analysis. The runtime CLI does not execute audited skill
instructions, contact a model/service, install dependencies or change audited skills.
`--svg` writes the explicitly requested output file. Installation/building may use
package registries or Git; this is separate from offline auditing.

Local transcripts can contain private work. Usage scanning reads supported invocation
records and reports counts; it does not reproduce transcript content. JSON and SVG
reports can disclose skill names and paths. Review a report before sharing it. Use
`--no-usage` to skip transcript scanning entirely.

Manifest-controlled component paths are bounded to their owning root. This is not a
sandbox for arbitrary files supplied directly on the CLI, nor a replacement for a
skill security scanner. Auditing attacker-controlled libraries should happen in an
appropriate isolated environment. Filesystem permissions remain the user's control.

For a vulnerability, use the repository's GitHub private vulnerability reporting
feature if it is enabled. Otherwise contact the maintainer through their public
GitHub profile and arrange private reporting before posting sensitive details.
General reproducible bugs belong in GitHub Issues with version, platform, command,
sanitized input and expected/actual exit status. Do not upload private transcripts.

Use a matching tagged release from the repository's Releases page. Fixes in a newer
checkout are not automatically available to users of an older installed release;
include the exact CLI version in a report.
