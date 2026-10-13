"""Build a deterministic, allowlisted Agent Skill ZIP using only the standard library.

    python scripts/build_skill_bundle.py --profile local --output-dir dist
    python scripts/build_skill_bundle.py --profile agensi --output-dir dist

The local profile carries the offline CLI. The Agensi profile carries an MCP-oriented
workflow that requires a separately installed CLI; MCP resources are not local files.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LOCAL_README = """# skillrot: local Agent Skill

Unpack this archive into a skill directory named `skillrot` for your agent.
It contains the Python CLI, instructions, rule reference and MIT license.
Python 3.9+ is required; the audit uses no runtime dependencies or network.

Locate `skillrot.py` beside `SKILL.md` and use its verified absolute path:

    python "/absolute/path/to/skillrot/skillrot.py" "/path/to/skills" --no-usage --json

Use `python3` where that is your Python command. Quote paths with spaces.
No-path discovery is for Claude Code only. Other agents' libraries require
explicit paths and still use Claude's estimated listing model.
`--no-usage` skips transcript scanning. Without it, available Claude transcripts
are read locally. Nothing is uploaded. `docs/RULES.md` explains findings.

Version and resource SHA-256 hashes are recorded in `manifest.json`.
Verify hashes before use; hashes establish integrity, not authorship or a signature.
"""
PROFILES = {
    "local": {
        "SKILL.md": "SKILL.md",
        "skillrot.py": "skillrot.py",
        "docs/RULES.md": "docs/RULES.md",
        "LICENSE": "LICENSE",
    },
    "agensi": {
        "SKILL.md": "marketplace/skillrot/SKILL.md",
        "README.md": "marketplace/skillrot/README.md",
        "references/RULES.md": "docs/RULES.md",
        "LICENSE": "LICENSE",
    },
}


def _read_text(relative: str) -> bytes:
    """Read only a declared text resource, refusing links and reparse points."""
    path = ROOT
    for part in ("",) + Path(relative).parts:
        if part:
            path = path / part
        attributes = path.lstat()
        if path.is_symlink() or getattr(attributes, "st_file_attributes", 0) & getattr(
                stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
            raise ValueError("Symlink or reparse-point resource is not allowed: " + relative)
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        raise ValueError("Resource escapes the source directory: " + relative) from None
    content = path.read_text(encoding="utf-8")
    if "\x00" in content:
        raise ValueError("Resource is not UTF-8 text: " + relative)
    return content.encode("utf-8")


def _version(source: bytes) -> str:
    """Read a literal source version without importing or executing the CLI."""
    for node in ast.parse(source.decode("utf-8")).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "__version__"
                for target in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                version = node.value.value
                if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+[A-Za-z0-9.]*", version):
                    return version
    raise ValueError("skillrot.py must declare a safe literal __version__")


def build_bundle(output_dir: Path, profile: str) -> Path:
    """Build one skillrot archive; no repository traversal selects archive members."""
    if profile not in PROFILES:
        raise ValueError("Unknown delivery profile: " + profile)
    source = _read_text("skillrot.py")
    version = _version(source)
    resources = {name: _read_text(relative) for name, relative in PROFILES[profile].items()}
    if profile == "local":
        resources["README.md"] = LOCAL_README.encode("utf-8")
    manifest = {
        "schema_version": 1, "name": "skillrot", "version": version, "profile": profile,
        "files": {name: {"sha256": hashlib.sha256(content).hexdigest(), "size": len(content)}
                  for name, content in sorted(resources.items())},
    }
    resources["manifest.json"] = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact = output_dir / ("skillrot-" + version + "-" + profile + ".zip")
    with tempfile.NamedTemporaryFile(prefix="skillrot-bundle-", suffix=".tmp",
                                     dir=output_dir, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        # Stored UTF-8 text avoids compressor-version differences in archive bytes.
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, content in sorted(resources.items()):
                member = zipfile.ZipInfo("skillrot/" + name, date_time=(1980, 1, 1, 0, 0, 0))
                member.create_system = 3
                member.external_attr = 0o100644 << 16
                archive.writestr(member, content)
        os.replace(temporary, artifact)
    finally:
        if temporary.exists():
            temporary.unlink()
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="local")
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    arguments = parser.parse_args()
    try:
        artifact = build_bundle(arguments.output_dir, arguments.profile)
    except (OSError, UnicodeError, ValueError, SyntaxError) as exc:
        print("skillrot bundle: " + ascii(str(exc)), file=sys.stderr)
        return 2
    print(str(artifact.resolve()).encode("ascii", errors="backslashreplace").decode("ascii"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
