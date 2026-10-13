# Changelog

## 0.4.0 — 2026-10-13

Production review on 2026-10-13 additionally:

- Reject scalar continuation after flow sequences and non-string YAML mapping keys;
  preserve collection type evidence in boolean validation. Correct folded block tails.
- Escape C0/C1 terminal controls in reports and all diagnostic channels.
- Reject unavailable explicitly requested transcript directories; `--no-usage` still
  skips evidence scanning. Refuse SVG outputs aliasing discovered audited source files,
  including hardlinks and symlinks.
- Fail inventory enumeration errors with exit 2 instead of silently passing incomplete
  recursive or shallow scans. Skip recursive child directory links/reparse points while
  supporting explicitly requested linked roots and shallow linked installations.
- Avoid counting supporting files repeatedly through Windows junction cycles or child
  directory links. Turn discovered-file symlink resolution loops into operational errors.
- Describe overlapping-description groups as transitive clusters rather than implying
  every pair meets the configured threshold.
- Add deterministic, allowlisted local and Agensi MCP workflow ZIPs with resource hashes,
  extraction/execution tests, and transparent local Python/CLI requirements.
- Include skill delivery resources in the source distribution and verify that its
  extracted tree can run the source suite and build both delivery profiles.
- Add a line-by-line source atlas, detailed reverse-engineering reports, current
  reproducible fixtures/charts, marketplace research and a ready-to-paste launch kit.

- Default discovery audits Claude Code entries. Codex, Cursor and other directories
  require explicit paths and use documented Claude listing assumptions.
- Reject invalid arguments and unavailable requested inputs with exit 2. A partial scan
  or failed SVG export cannot report success. JSON supports paths through legacy output
  encodings.
- Add `schema_version: 1` and model assumptions to JSON. Per-entry requested and retained
  listing costs account for visibility, deduplication and actual modeled retention.
- Parse supported transcript records instead of matching JSON text. Avoid attributing
  ambiguous bare command calls to multiple plugins. Preserve exact duplicate groups
  at larger inventory sizes and render control characters safely in reports.
- Reject invalid or unsupported YAML frontmatter with SR009. Check core string-field
  types with SR014; portable checks add name and further type/limit constraints, enforce the compatibility limit as an error,
  and treat a missing description as a warning in Claude mode and an error in portable
  mode. Valid YAML outside the supported subset needs a full YAML/host validator.
- Build the sdist and wheel in CI and exercise the installed command in a clean temporary
  environment. Add Python 3.14 coverage; record provenance for weekly public audits.
- Clarify estimate, usage-history and portability limits; label previous demo media as
  historical. Migrate MIT metadata to SPDX with a compatible setuptools build minimum.

These changes are not included in the published v0.3.1 release. Existing JSON field names
remain available, but corrected listing-cost semantics can change values. Scripts relying
on previous false-success cases must now handle exit 2.

## 0.3.1 — 2026-09-28

- Add `--fail-over-budget` to gate estimated listing overflow in CI.

## 0.3.0 — 2026-09-28

- Release the listing-budget report and related demonstration assets.
