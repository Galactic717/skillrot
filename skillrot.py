#!/usr/bin/env python3
"""skillrot - offline audits of skill libraries and estimated listing pressure.

Model the supported Claude Code listing profile, check skill authoring and
collection conflicts, and optionally inspect local invocation evidence.
Token and routing estimates do not inspect a running agent session.

Zero dependencies. Python 3.9+.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import math
import os
import re
import stat
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

__version__ = "0.4.0"

# --- Spec constants -------------------------------------------------------
# Sourced from the Claude Code skills reference and the Agent Skills spec.
# docs/RULES.md carries the citation behind every rule.

LISTING_CHAR_CAP = 1536      # description + when_to_use, truncated in the listing
COMPATIBILITY_CAP = 500      # Agent Skills spec limit on `compatibility`

# The six fields accepted by claude.ai uploads, the Skills API and
# package_skill.py. Anything else is a hard error on those paths.
PORTABLE_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}

# Every field Claude Code itself accepts.
KNOWN_FIELDS = PORTABLE_FIELDS | {
    "when_to_use",
    "argument-hint",
    "arguments",
    "disable-model-invocation",
    "user-invocable",
    "disallowed-tools",
    "model",
    "effort",
    "context",
    "agent",
    "background",
    "hooks",
    "paths",
    "shell",
    "version",
}

BOOL_FIELDS = ("disable-model-invocation", "user-invocable", "background")
TRUE_WORDS = {"true", "yes", "on", "1"}
FALSE_WORDS = {"false", "no", "off", "0"}

# Cues that tell the router *when* to reach for a skill. A description with
# none of these describes what a skill is, not when it applies.
TRIGGER_CUES = (
    "use when", "use this when", "used when", "when the user", "when you",
    "when asked", "when working", "when a ", "when the ", "invoke when",
    "trigger", "for when", "apply when", "activates when", "call this when",
)

DEFAULT_CONTEXT_WINDOW = 200_000
DEFAULT_BODY_LINE_BUDGET = 500
DEFAULT_SIMILARITY = 0.80
DEFAULT_CHARS_PER_TOKEN = 4.0
# Claude Code sizes the always-on skill listing at 1% of the context window and
# drops the least-used descriptions when it overflows (skillListingBudgetFraction,
# SLASH_COMMAND_TOOL_CHAR_BUDGET). Skill names are always kept.
DEFAULT_BUDGET_FRACTION = 0.01

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "into", "is", "it", "of", "on", "or", "that", "the", "this", "to", "use",
    "used", "using", "when", "with", "you", "your",
}


# --- Frontmatter parsing --------------------------------------------------

_KEY_RE = re.compile(r'''^((?:"(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[A-Za-z_][A-Za-z0-9_.-]*))\s*:\s*(.*)$''')


class _FrontmatterValue(str):
    """Keep the public string mapping while retaining YAML types for validation."""
    kind: str
    members: object

    def __new__(cls, value: str, kind: str = "string", members=None):
        instance = super().__new__(cls, value)
        instance.kind = kind
        instance.members = members
        return instance


def _yaml_comment(value: str) -> str:
    """Remove a separated comment, respecting a scalar's opening quotes."""
    quote = value[:1] if value[:1] in ("'", '"') else None
    flow = value.startswith("[")
    i = 1 if quote else 0
    while i < len(value):
        char = value[i]
        if quote:
            if quote == '"' and char == "\\":
                i += 2
                continue
            if char == quote:
                if quote == "'" and value[i:i + 2] == "''":
                    i += 2
                    continue
                quote = None
        elif flow and char in "\"'" and (i == 0 or value[i - 1] in " [,\t"):
            quote = char
        elif char == "#" and (i == 0 or value[i - 1].isspace()):
            return value[:i].rstrip()
        i += 1
    return value.rstrip()


def _strip_quotes(value: str) -> str:
    value = _yaml_comment(value.strip())
    if not value or value[0] not in "\"'":
        return value
    quote = value[0]
    output: List[str] = []
    escapes = {"0": "\0", "a": "\a", "b": "\b", "t": "\t", "n": "\n",
               "v": "\v", "f": "\f", "r": "\r", "e": "\x1b", " ": " ",
               '"': '"', "/": "/", "\\": "\\", "N": "\x85", "_": "\xa0",
               "L": "\u2028", "P": "\u2029"}
    i = 1
    while i < len(value):
        char = value[i]
        if char == quote:
            if quote == "'" and value[i:i + 2] == "''":
                output.append("'")
                i += 2
                continue
            if value[i + 1:].strip():
                raise ValueError("text after a quoted scalar")
            return "".join(output)
        if char == "\\" and quote == '"':
            i += 1
            if i >= len(value):
                break
            escaped = value[i]
            if escaped == "\n":
                i += 1
                while i < len(value) and value[i] in " \t":
                    i += 1
                continue
            if escaped in "xuU":
                length = {"x": 2, "u": 4, "U": 8}[escaped]
                digits = value[i + 1:i + 1 + length]
                if len(digits) != length or not re.fullmatch(r"[0-9a-fA-F]+", digits):
                    raise ValueError("invalid quoted Unicode escape")
                try:
                    codepoint = int(digits, 16)
                    if 0xD800 <= codepoint <= 0xDFFF:
                        raise ValueError("surrogates are not Unicode scalar values")
                    output.append(chr(codepoint))
                except ValueError:
                    raise ValueError("invalid quoted Unicode code point")
                i += length + 1
                continue
            if escaped not in escapes:
                raise ValueError("unsupported or invalid quoted escape")
            output.append(escapes[escaped])
        elif char == "\n":
            # YAML folds ordinary line breaks in quoted scalars.
            while output and output[-1] in " \t":
                output.pop()
            breaks = 0
            while i < len(value) and value[i] == "\n":
                breaks += 1
                i += 1
                while i < len(value) and value[i] in " \t":
                    i += 1
            output.append("\n" * (breaks - 1) if breaks > 1 else " ")
            continue
        else:
            output.append(char)
        i += 1
    raise ValueError("unterminated quoted scalar")


def _yaml_scalar(value: str) -> _FrontmatterValue:
    value = _yaml_comment(value.strip())
    if value[:1] in ("'", '"'):
        return _FrontmatterValue(_strip_quotes(value))
    if value.startswith(("&", "*", "!", "{", "?", "%", "@", "`", "|", ">")) or re.match(r"^-(?:\s|$)", value):
        raise ValueError("anchors, aliases, tags, flow mappings or reserved syntax are unsupported")
    if value.startswith("["):
        # A bounded flat sequence supports common tools/arguments list syntax.
        if not value.endswith("]"):
            raise ValueError("unterminated flow sequence")
        items: List[_FrontmatterValue] = []
        token: List[str] = []
        quote = None
        escaped = False
        content = value[1:-1]
        for index, char in enumerate(content + ","):
            if escaped:
                token.append(char)
                escaped = False
            elif quote == '"' and char == "\\":
                token.append(char)
                escaped = True
            elif quote:
                token.append(char)
                if char == quote:
                    quote = None
            elif char in "\"'":
                token.append(char)
                quote = char
            elif char == ",":
                part = "".join(token).strip()
                if part:
                    if part[:1] not in ("'", '"') and any(char in part for char in "[]{}"):
                        raise ValueError("flow delimiters inside plain sequence items are unsupported")
                    items.append(_yaml_scalar(part))
                elif index < len(content):
                    raise ValueError("empty flow sequence items are invalid")
                token = []
            else:
                token.append(char)
        if quote:
            raise ValueError("unterminated quote in flow sequence")
        return _FrontmatterValue(" ".join(items), "sequence", items)
    if re.search(r":(?:\s|$)", value):
        raise ValueError("a plain scalar containing ': ' must be quoted")
    kind = "string"
    if not value or value.lower() in ("null", "~"):
        kind = "null"
    elif value.lower() in TRUE_WORDS | FALSE_WORDS:
        kind = "boolean"
    elif re.fullmatch(r"[-+]?(?:[0-9][0-9_]*(?:\.[0-9_]*)?(?:[eE][-+]?[0-9]+)?|\.[0-9_]+|0[xob][0-9a-fA-F_]+|\.inf|\.nan)", value, re.I):
        kind = "number"
    elif re.match(r"^\d{4}-\d\d-\d\d(?:$|[Tt ])", value):
        kind = "timestamp"
    return _FrontmatterValue(value, kind)


def _yaml_key(value: str) -> str:
    """Keep mapping keys as YAML strings, including explicitly quoted keys."""
    key = _yaml_scalar(value)
    if key.kind != "string":
        raise ValueError("mapping keys must be strings; quote boolean or null-looking keys")
    return str(key)


def _yaml_block(value: str, children: List[str]) -> _FrontmatterValue:
    nonempty = [line for line in children if line.strip()]
    indent = len(nonempty[0]) - len(nonempty[0].lstrip(" ")) if nonempty else 0
    if any(len(line) - len(line.lstrip(" ")) < indent for line in nonempty):
        raise ValueError("block scalar indentation is inconsistent")
    block = [line[indent:] if line.strip() else "" for line in children]
    if value.startswith("|"):
        result = "\n".join(block)
    else:
        result = ""
        last_content = max((i for i, line in enumerate(block) if line), default=-1)
        for i, line in enumerate(block):
            result += line
            if i + 1 < len(block):
                following = block[i + 1]
                if line and following and not line.startswith(" ") and not following.startswith(" "):
                    result += " "
                elif not following and line and not line.startswith(" ") and i + 1 < last_content:
                    # The following blank line supplies the paragraph break.
                    pass
                else:
                    result += "\n"
    # Empty children produce the empty string. Default clip retains one newline.
    if "-" in value:
        result = result.rstrip("\n")
    elif "+" not in value and children:
        result = result.rstrip("\n") + "\n"
    elif children:
        result += "\n"
    return _FrontmatterValue(result)


def parse_frontmatter(text: str) -> Tuple[Dict[str, str], str, List[str]]:
    """Parse a bounded YAML subset, reporting invalid/unsupported syntax.

    Supports scalar strings, flat lists and shallow metadata maps. This is not
    a full YAML validator. Unsupported syntax discards the metadata rather than
    supplying apparently valid values to the audit.
    """
    problems: List[str] = []
    lines = text.splitlines()

    if not lines or lines[0].strip() != "---":
        # Claude Code reads frontmatter only when `---` is the very first line.
        # Anything else and the whole file, markers included, becomes body.
        if any(line.strip() == "---" for line in lines[:20]):
            problems.append("frontmatter-not-first-line")
        else:
            problems.append("no-frontmatter")
        return {}, text, problems

    end = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() in ("---", "..."):
            end = i
            break
    if end is None:
        problems.append("unterminated-frontmatter")
        return {}, text, problems

    body = "\n".join(lines[end + 1:])
    if any(ord(char) < 32 and char != "\t" or ord(char) == 127
           for line in lines[1:end] for char in line):
        return {}, body, ["invalid-frontmatter: literal control character in YAML"]
    fm: Dict[str, str] = {}
    i = 1
    while i < end:
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        match = _KEY_RE.match(raw)
        if not match:
            problems.append("invalid-frontmatter: line {}: expected a top-level scalar key".format(i + 1))
            return {}, body, problems
        start = i
        i += 1
        value = _yaml_comment(match.group(2).strip())
        children: List[str] = []
        while i < end and (not lines[i].strip() or lines[i][:1] in (" ", "\t")
                           or (not value and (lines[i].startswith("- ")
                                              or lines[i].lstrip().startswith("#")))):
            children.append(lines[i])
            i += 1
        try:
            if any(line.startswith("\t") or re.match(r"^ +\t", line) for line in children):
                raise ValueError("tabs are not valid YAML indentation")
            key = _yaml_key(match.group(1))
            if key in fm:
                raise ValueError("duplicate key '{}'".format(key))
            meaningful = [line for line in children if line.strip() and not line.lstrip().startswith("#")]
            if value in ("|", ">", "|-", ">-", "|+", ">+"):
                fm[key] = _yaml_block(value, children)
            elif value == "" and meaningful:
                indent = len(meaningful[0]) - len(meaningful[0].lstrip(" "))
                if any(len(line) - len(line.lstrip(" ")) != indent for line in meaningful):
                    raise ValueError("nested or uneven collection indentation is unsupported")
                if meaningful[0].lstrip().startswith("-"):
                    items = []
                    for line in meaningful:
                        item = re.fullmatch(r"\s*-\s+(.*)", line)
                        if not item:
                            raise ValueError("invalid block sequence item")
                        parsed = _yaml_scalar(item.group(1))
                        if parsed.kind == "sequence":
                            raise ValueError("nested collections are unsupported")
                        items.append(parsed)
                    fm[key] = _FrontmatterValue(" ".join(items), "sequence", items)
                elif key == "metadata":
                    members = {}
                    for line in meaningful:
                        item = _KEY_RE.match(line.lstrip())
                        if not item:
                            raise ValueError("invalid metadata mapping entry")
                        member = _yaml_key(item.group(1))
                        if member in members:
                            raise ValueError("duplicate metadata key")
                        members[member] = _yaml_scalar(item.group(2))
                    fm[key] = _FrontmatterValue(" ".join(members), "mapping", members)
                else:
                    raise ValueError("only shallow metadata maps are supported")
            elif value[:1] in ("'", '"'):
                fm[key] = _yaml_scalar("\n".join([value] + children))
            else:
                first = _yaml_scalar(value)
                if first.kind == "sequence" and meaningful:
                    raise ValueError("a flow sequence cannot have scalar continuation lines")
                rendered = str(first)
                blank_lines = 0
                for line in children:
                    if line.lstrip().startswith("#"):
                        continue
                    if not line.strip():
                        blank_lines += 1
                        continue
                    # Continuation text belongs to the existing plain scalar:
                    # quotes, numbers and YAML-looking words stay literal text.
                    part = re.split(r"\s+#", line.strip(), maxsplit=1)[0].rstrip()
                    if re.search(r":(?:\s|$)", part):
                        raise ValueError("a plain scalar containing ': ' must be quoted")
                    rendered += ("\n" * blank_lines if blank_lines else " ") + part
                    blank_lines = 0
                fm[key] = _FrontmatterValue(rendered) if meaningful else first
        except ValueError as exc:
            problems.append("invalid-frontmatter: line {}: {}".format(start + 1, exc))
            return {}, body, problems

    return fm, body, problems


# --- Discovery ------------------------------------------------------------

@dataclass
class Skill:
    path: Path
    root: Path
    origin: str                      # personal | project | plugin | scanned
    command: str                     # what you type to invoke it
    frontmatter: Dict[str, str]
    body: str
    problems: List[str] = field(default_factory=list)
    plugin: Optional[str] = None
    bundle_bytes: int = 0
    kind: str = "skill"              # skill | command (a commands/*.md file)
    override: Optional[str] = None   # skillOverrides state from settings, if any

    @property
    def description(self) -> str:
        return self.frontmatter.get("description", "").strip()

    @property
    def when_to_use(self) -> str:
        return self.frontmatter.get("when_to_use", "").strip()

    @property
    def routing_text(self) -> str:
        """What the listing shows after the name: description + when_to_use, or,
        with no description, the first non-empty line of the body (as documented)."""
        description = self.description
        if not description:
            for line in self.body.splitlines():
                if line.strip():
                    description = line.strip().lstrip("#").strip()
                    break
        return " ".join(p for p in (description, self.when_to_use) if p)

    @property
    def in_listing(self) -> bool:
        """Whether the skill is advertised to the model at all.
        `disable-model-invocation: true` and the skillOverrides states "off" and
        "user-invocable-only" keep it out of context entirely."""
        if self.override in ("off", "user-invocable-only"):
            return False
        return _truthy(self.frontmatter.get("disable-model-invocation", "false")) is not True

    @property
    def listing_text(self) -> str:
        """The text the harness puts in the always-on skill listing."""
        return ": ".join(p for p in (self.command, self.routing_text) if p)

    @property
    def body_lines(self) -> int:
        return len([ln for ln in self.body.splitlines() if ln.strip()])


def _is_version_dir(name: str) -> bool:
    return bool(re.fullmatch(r"v?\d+(\.\d+)*[A-Za-z0-9.+-]*", name))


def _plugin_name_for(skill_dir: Path) -> Optional[str]:
    """Walk up from a skill directory to name the plugin that ships it."""
    for parent in [skill_dir] + list(skill_dir.parents):
        manifest = parent / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            data = _read_json(manifest)
            if data is not None:
                _validate_plugin_manifest(data, str(manifest))
                if "name" not in data:
                    raise AuditError("{}: name is required".format(manifest))
                return data["name"]
        if parent.name == "skills":
            root = parent.parent
            # Versioned install caches are the only manifest-free ownership
            # evidence. A generic directory named skills is not a plugin.
            if _is_version_dir(root.name) and any(p.name == "plugins" for p in root.parents):
                return root.parent.name
    return None


def _classify(path: Path) -> Tuple[str, Optional[str]]:
    normalized = str(path).lower().replace("\\", "/")
    home = str(Path.home()).lower().replace("\\", "/")
    plugin = _plugin_name_for(path.parent)

    if "/plugins/" in normalized or "/marketplace" in normalized:
        if plugin:
            return "plugin", plugin
    if normalized.startswith(home + "/.claude/skills"):
        return "personal", None
    if "/.claude/skills/" in normalized:
        return "project", None
    if plugin:
        return "plugin", plugin
    return "scanned", None


_PRUNE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}


def _bundle_bytes(skill_dir: Path) -> int:
    """Bytes of the skill's own files.

    Prunes VCS/vendor noise and never descends into a nested skill (a
    subdirectory carrying its own SKILL.md), so a plugin root or a whole
    repository dropped in as one skill reports its own footprint rather than
    the entire tree. Without this, a repo-root SKILL.md billed gigabytes and
    the walk dominated runtime.
    """
    total = 0
    root = str(skill_dir)
    for current, dirs, files in os.walk(root):
        if current != root and "SKILL.md" in files:
            dirs[:] = []            # a separate skill owns everything below here
            continue
        descend: List[str] = []
        for directory in dirs:
            if directory in _PRUNE_DIRS:
                continue
            try:
                info = os.lstat(os.path.join(current, directory))
            except OSError:
                continue
            if (stat.S_ISLNK(info.st_mode) or
                    getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
                continue
            descend.append(directory)
        dirs[:] = descend
        for name in files:
            try:
                total += os.stat(os.path.join(current, name)).st_size
            except OSError:
                pass
    return total


def _directory_name(path: Path) -> str:
    """The skill's own directory name, resolved so `.` and `..` don't leak through."""
    name = path.parent.name
    if name in ("", ".", ".."):
        try:
            name = path.resolve().parent.name
        except OSError:
            name = ""
    return name


# One discovered file: (path, owning plugin or None, "skill" | "command", command name or None)
Entry = Tuple[Path, Optional[str], str, Optional[str]]


def load_skill(
    path: Path, plugin: Optional[str] = None, kind: str = "skill", command: Optional[str] = None
) -> Skill:
    """Load one SKILL.md, or one commands/*.md file when kind == "command".

    `plugin` is the owning plugin when a manifest named it; otherwise it is
    inferred from the path. `command` is a precomputed name (commands take theirs
    from the file path, not from frontmatter)."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:  # unreadable file is a finding, not a crash
        return Skill(
            path=path, root=path.parent, origin="scanned", command=command or path.parent.name,
            frontmatter={}, body="", problems=["unreadable: {}".format(exc)], kind=kind,
        )
    fm, body, problems = parse_frontmatter(text)
    if kind == "command":
        # Command files support the same frontmatter except `name`: the file path
        # is the name. A missing frontmatter block is normal for them.
        problems = [p for p in problems if p != "no-frontmatter"]
        origin = "plugin" if plugin else "command"
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        return Skill(
            path=path, root=path.parent, origin=origin, command=command or path.stem,
            frontmatter=fm, body=body, problems=problems, plugin=plugin,
            bundle_bytes=size, kind="command",
        )
    origin, inferred = ("plugin", plugin) if plugin else _classify(path)
    plugin = inferred
    # Frontmatter `name` wins over the directory name, for plugin and local
    # skills alike; a plugin keeps its prefix in front of it.
    leaf = fm.get("name") or _directory_name(path) or path.stem
    if plugin:
        command = leaf if leaf.startswith(plugin + ":") else "{}:{}".format(plugin, leaf)
    else:
        command = leaf
    return Skill(
        path=path, root=path.parent, origin=origin, command=command,
        frontmatter=fm, body=body, problems=problems, plugin=plugin,
        bundle_bytes=_bundle_bytes(path.parent),
    )


def _project_dirs(cwd: Path) -> List[Path]:
    """The start directory and its parents up to the repository root: Claude Code
    loads project skills from .claude/ in each. Outside a repo, just the start."""
    dirs: List[Path] = []
    for folder in [cwd] + list(cwd.parents):
        dirs.append(folder)
        if (folder / ".git").exists():
            return dirs
    return [cwd]


def default_roots(cwd: Optional[Path] = None) -> List[Path]:
    """Install directories for the Claude Code profile this tool models."""
    home = Path.home()
    candidates = [
        home / ".claude" / "skills",
        home / ".claude" / "plugins",
    ] + [d / ".claude" / "skills" for d in _project_dirs(cwd or Path.cwd())]
    return [c for c in candidates if c.is_dir()]


def command_entries(root: Path) -> List[Entry]:
    """Legacy command files: commands/deploy.md is /deploy and
    commands/frontend/component.md is /frontend:component."""
    entries: List[Entry] = []
    for path in _inventory_files(root, "*.md", missing_ok=True):
        rel = path.relative_to(root).with_suffix("")
        entries.append((path, None, "command", ":".join(rel.parts)))
    return entries


class AuditError(ValueError):
    """An operational input failure: an incomplete audit must not look clean."""


def _inventory_files(
    root: Path, pattern: str, shallow: bool = False, missing_ok: bool = False,
) -> List[Path]:
    """Enumerate inventory without silently suppressing directory read errors.

    Recursive scans do not descend into child symlink/reparse directories;
    explicit roots are followed. Shallow installed roots inspect one level of
    skill directories, including linked installations, but never recurse deeper.
    Missing optional component roots are normal; inaccessible roots are errors.
    """
    found: List[Path] = []
    pending: List[Tuple[Path, int]] = [(root, 0)]
    while pending:
        folder, depth = pending.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    path = Path(entry.path)
                    if (not shallow or depth == 1) and fnmatch.fnmatch(entry.name, pattern):
                        found.append(path)
                    if shallow:
                        if depth == 0 and entry.is_dir():
                            pending.append((path, 1))
                    elif entry.is_dir(follow_symlinks=False):
                        # Older Windows Pythons consider junctions directories
                        # even with follow_symlinks=False. Prune reparse children
                        # before scanning so junction cycles and escapes stop.
                        attributes = getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0)
                        if not attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
                            pending.append((path, depth + 1))
        except OSError as exc:
            if missing_ok and depth == 0 and isinstance(exc, (FileNotFoundError, NotADirectoryError)):
                continue
            raise AuditError("could not scan inventory {}: {}".format(folder, exc)) from None
    return sorted(found)


def _read_json(path: Path) -> Optional[dict]:
    """Read an optional JSON object; present but invalid input is an error."""
    def reject_constant(value):
        raise ValueError("non-finite JSON number {}".format(value))

    try:
        data = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
    except FileNotFoundError:
        return None
    except (ValueError, OSError, UnicodeError, RecursionError) as exc:
        raise AuditError("could not read JSON {}: {}".format(path, exc)) from None
    if not isinstance(data, dict):
        raise AuditError("{}: expected a JSON object".format(path))
    return data


def _as_paths(value, label: str = "manifest path") -> List[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list) and all(isinstance(p, str) for p in value):
        values = value
    else:
        raise AuditError("{}: expected a path string or an array of path strings".format(label))
    if any(not p.strip() for p in values):
        raise AuditError("{}: paths must not be empty".format(label))
    return values


def _within_root(path: Path, root: Path, label: str) -> Path:
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError, RuntimeError):
        raise AuditError("{}: path escapes its root: {}".format(label, path)) from None
    return path


def _manifest_path(root: Path, value: str, label: str) -> Path:
    # Check Windows syntax on every host, before resolving a UNC path could
    # cause network filesystem access. Parent traversal is never a local source.
    normalized = value.replace("\\", "/")
    windows = PureWindowsPath(value)
    if not value.strip() or Path(normalized).is_absolute() or windows.drive or ".." in normalized.split("/"):
        raise AuditError("{}: expected a relative path within {}: {}".format(label, root, value))
    return _within_root(root / normalized, root, label)


def _validate_plugin_manifest(manifest: dict, label: str) -> None:
    if "name" in manifest and (not isinstance(manifest["name"], str) or not manifest["name"].strip()):
        raise AuditError("{}: name must be a non-empty string".format(label))
    for key in ("skills", "commands"):
        if key in manifest:
            _as_paths(manifest[key], "{} {}".format(label, key))


def _marketplace_entries(market: dict, label: str) -> List[dict]:
    if "plugins" not in market:
        raise AuditError("{}: plugins is required".format(label))
    entries = market["plugins"]
    if not isinstance(entries, list) or any(not isinstance(p, dict) for p in entries):
        raise AuditError("{}: plugins must be an array of objects".format(label))
    for entry in entries:
        for required in ("name", "source"):
            if required not in entry:
                raise AuditError("{}: plugin {} is required".format(label, required))
        _validate_plugin_manifest(entry, label)
        if "strict" in entry and not isinstance(entry["strict"], bool):
            raise AuditError("{}: plugin strict must be a boolean".format(label))
        source = entry["source"]
        if not isinstance(source, (str, dict)):
            raise AuditError("{}: plugin source must be a relative path or a source object".format(label))
        if isinstance(source, dict) and (not isinstance(source.get("source"), str)
                                        or not source["source"].strip()):
            raise AuditError("{}: remote source must identify its source type".format(label))
    return entries


def _plugin_entries(
    plugin_root: Path, entry: Optional[dict] = None, name: Optional[str] = None
) -> List[Entry]:
    """Everything one plugin adds to the listing: skills and commands.

    Skills: default `skills/<name>/SKILL.md`, plus any manifest `skills` paths
    (a folder of skill folders, or one folder holding SKILL.md); a plugin with
    only a root SKILL.md loads as a single skill. Commands: `commands/*.md`,
    unless the manifest `commands` key replaces that default. With no
    plugin.json, the marketplace entry is the manifest.
    Unsupported manifest shapes are diagnosed rather than silently skipped.
    """
    manifest_path = plugin_root / ".claude-plugin" / "plugin.json"
    loaded = _read_json(manifest_path)
    if loaded is not None and entry:
        components = [key for key in ("skills", "commands", "agents", "hooks", "mcpServers",
                                     "lspServers", "outputStyles") if key in entry]
        if components and entry.get("strict", True) is False:
            raise AuditError("{}: strict:false conflicts with marketplace component fields: {}".format(
                manifest_path, ", ".join(components)))
        listing_components = [key for key in components if key in ("skills", "commands")]
        if listing_components:
            raise AuditError("{}: unsupported marketplace component extensions alongside plugin.json: {}. "
                             "Audit the component directories explicitly or use --all.".format(
                                 manifest_path, ", ".join(listing_components)))
    manifest = loaded if loaded is not None else entry or {}
    label = str(manifest_path)
    if loaded is not None and "name" not in loaded:
        raise AuditError("{}: name is required".format(label))
    _validate_plugin_manifest(manifest, label)
    plugin = str(manifest.get("name") or name or (entry or {}).get("name")
                 or plugin_root.resolve().name)
    extra = _as_paths(manifest["skills"], label + " skills") if "skills" in manifest else []
    skills: List[Path] = []
    folders = [("skills", False)] + [(p, True) for p in extra]
    for rel, explicit in folders:
        folder = _manifest_path(plugin_root, rel, label + " skills")
        if explicit and not folder.is_dir():
            raise AuditError("{} skills: component directory is missing or invalid: {}".format(label, folder))
        if (folder / "SKILL.md").is_file():
            skills.append(_within_root(folder / "SKILL.md", plugin_root, label + " skills"))
        else:
            skills.extend(_within_root(p, plugin_root, label + " skills")
                          for p in _inventory_files(folder, "SKILL.md", shallow=True,
                                                    missing_ok=not explicit))
    if (not skills and "skills" not in manifest and not (plugin_root / "skills").is_dir()
            and (plugin_root / "SKILL.md").is_file()):
        skills.append(_within_root(plugin_root / "SKILL.md", plugin_root, label + " skills"))
    found: List[Entry] = [(p, plugin, "skill", None) for p in skills]

    command_paths = (_as_paths(manifest["commands"], label + " commands") if "commands" in manifest
                     else ["commands"])
    for rel in command_paths:
        target = _manifest_path(plugin_root, rel, label + " commands")
        if "commands" in manifest and not target.exists():
            raise AuditError("{} commands: component path is missing: {}".format(label, target))
        target_is_file = target.is_file()
        if target_is_file:
            files = [target]
        else:
            files = _inventory_files(target, "*.md", missing_ok="commands" not in manifest)
        for path in files:
            if path.suffix != ".md":
                continue
            _within_root(path, plugin_root, label + " commands")
            leaf = (":".join(path.relative_to(target).with_suffix("").parts)
                    if not target_is_file else path.stem)
            found.append((path, plugin, "command", "{}:{}".format(plugin, leaf)))
    return found


def manifest_skill_files(root: Path) -> Optional[List[Entry]]:
    """Skills and commands a marketplace or plugin checkout would install.

    Returns None when `root` is neither, so the caller falls back to a plain
    recursive scan. Without this, a repo's translated docs and mirrors for
    other harnesses (docs/ja-JP/skills, .gemini/skills, ...) were counted as
    installed skills and inflated the bill several times over.
    ponytail: only local (string) plugin sources resolve; github/url sources
    are not in this checkout, so they are skipped rather than fetched.
    """
    found: List[Entry] = []
    recognized = False
    # The checkout itself can be a plugin even when its marketplace entry points
    # at a remote copy of the same repo (source: github), so check both.
    if (root / ".claude-plugin" / "plugin.json").is_file():
        recognized = True
        found.extend(_plugin_entries(root))
    market_path = root / ".claude-plugin" / "marketplace.json"
    market = _read_json(market_path)
    if market is not None:
        recognized = True
        for entry in _marketplace_entries(market, str(market_path)):
            source = entry.get("source")
            if isinstance(source, str):
                plugin_root = _manifest_path(root, source, str(market_path) + " source")
                if not plugin_root.is_dir():
                    raise AuditError("{} source: plugin directory is missing or invalid: {}".format(market_path, plugin_root))
                found.extend(_plugin_entries(plugin_root, entry))
    return found if recognized else None


def _validate_settings(data: dict, label: str) -> None:
    states = {"on", "off", "name-only", "user-invocable-only"}
    for key in ("enabledPlugins", "skillOverrides", "env"):
        if key in data and not isinstance(data[key], dict):
            raise AuditError("{}: {} must be an object".format(label, key))
    for key, value in data.get("enabledPlugins", {}).items():
        if not isinstance(key, str) or not isinstance(value, bool):
            raise AuditError("{}: enabledPlugins entries must be booleans".format(label))
    for key, value in data.get("skillOverrides", {}).items():
        if not isinstance(key, str) or not isinstance(value, str) or value not in states:
            raise AuditError("{}: skillOverrides entries must be on, off, name-only or user-invocable-only".format(label))
    if any(not isinstance(value, str) for value in data.get("env", {}).values()):
        raise AuditError("{}: env values must be strings".format(label))
    if "skillListingBudgetFraction" in data:
        value = data["skillListingBudgetFraction"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1 or not math.isfinite(value):
            raise AuditError("{}: skillListingBudgetFraction must be finite and in (0, 1]".format(label))
    if "skillListingMaxDescChars" in data and (type(data["skillListingMaxDescChars"]) is not int
                                               or data["skillListingMaxDescChars"] != LISTING_CHAR_CAP):
        raise AuditError("{}: this profile models skillListingMaxDescChars={} only".format(label, LISTING_CHAR_CAP))


def load_settings(home: Path, cwd: Path) -> dict:
    """Merge Claude Code settings: user, then project, then local (later wins;
    enabledPlugins, skillOverrides and env merge key by key)."""
    merged: dict = {}
    files = [home / ".claude" / "settings.json"]
    for folder in reversed(_project_dirs(cwd)):
        files += [folder / ".claude" / "settings.json", folder / ".claude" / "settings.local.json"]
    for path in files:
        data = _read_json(path) or {}
        _validate_settings(data, str(path))
        for key, value in data.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = dict(merged[key], **value)
            else:
                merged[key] = value
    return merged


def installed_plugin_entries(home: Path, settings: dict) -> Optional[List[Entry]]:
    """Skills and commands of the plugins enabled in settings.

    Resolves each `name@marketplace` through installed_plugins.json (the install
    cache) and, for directory marketplaces loaded in place, through
    known_marketplaces.json. An absent enabledPlugins setting means no enabled
    plugins; blindly scanning the cache would count disabled installations.
    """
    _validate_settings(settings, "settings")
    enabled = settings.get("enabledPlugins", {})
    if not enabled:
        return []
    plugins_dir = home / ".claude" / "plugins"
    installed_path = plugins_dir / "installed_plugins.json"
    installed = (_read_json(installed_path) or {}).get("plugins", {})
    if not isinstance(installed, dict):
        raise AuditError("{}: plugins must be an object".format(installed_path))
    for installs in installed.values():
        if not isinstance(installs, list) or any(not isinstance(i, dict) for i in installs):
            raise AuditError("{}: plugin installations must be arrays of objects".format(installed_path))
        for install in installs:
            if "installPath" in install and not isinstance(install["installPath"], str):
                raise AuditError("{}: installPath must be a string".format(installed_path))
    markets_path = plugins_dir / "known_marketplaces.json"
    markets = _read_json(markets_path) or {}
    for info in markets.values():
        if not isinstance(info, dict) or ("source" in info and not isinstance(info["source"], dict)):
            raise AuditError("{}: marketplace entries and sources must be objects".format(markets_path))
        for location in (info.get("installLocation"), info.get("source", {}).get("path")):
            if location is not None and not isinstance(location, str):
                raise AuditError("{}: marketplace locations must be strings".format(markets_path))
    found: List[Entry] = []
    for key, on in sorted(enabled.items()):
        if on is not True:
            continue
        name, _, market = key.partition("@")
        root: Optional[Path] = None
        entry: Optional[dict] = None
        installed_roots: Dict[Path, Path] = {}
        for install in installed.get(key) or []:
            path = Path(str((install or {}).get("installPath", "")))
            if str(path) not in ("", ".") and path.is_dir():
                installed_roots.setdefault(path.resolve(), path)
        if len(installed_roots) > 1:
            raise AuditError("{}: enabled plugin {} has multiple installation roots; "
                             "scoped registry selection is outside this profile. "
                             "Pass an explicit plugin path to audit.".format(installed_path, key))
        if installed_roots:
            root = next(iter(installed_roots.values()))
        info = markets.get(market)
        if not isinstance(info, dict):
            info = {}
        location = info.get("installLocation") or info.get("source", {}).get("path")
        if location:
            catalog_path = Path(location) / ".claude-plugin" / "marketplace.json"
            catalog = _read_json(catalog_path) or {}
            entry = next((p for p in _marketplace_entries(catalog, str(catalog_path))
                          if p.get("name") == name), None)
            if root is None and entry and isinstance(entry.get("source"), str):
                candidate = _manifest_path(Path(location), entry["source"], str(catalog_path) + " source")
                if not candidate.is_dir():
                    raise AuditError("{} source: plugin directory is missing or invalid: {}".format(catalog_path, candidate))
                root = candidate
        if root is not None:
            found.extend(_plugin_entries(root, entry, name))
        else:
            raise AuditError("enabled plugin {} could not be resolved to a local installation".format(key))
    return found


def discover(
    roots: Sequence[Path],
    shallow_roots: Sequence[Path] = (),
    scan_all: bool = False,
    extra: Sequence[Entry] = (),
) -> List[Skill]:
    """Find and load every unique skill under the roots, plus `extra` entries.

    A root in `shallow_roots` is scanned one level deep (`*/SKILL.md`), the way
    Claude Code loads an install directory: a whole repo dropped into
    `~/.claude/skills/foo/` is one skill at `foo/SKILL.md`, not every nested
    SKILL.md it happens to contain. A marketplace or plugin checkout is read
    through its manifest, so only what Claude Code would install is counted.
    Any other root is scanned recursively; `scan_all` forces that everywhere.
    """
    shallow = {Path(r) for r in shallow_roots}
    entries: List[Entry] = []
    for root in roots:
        manifest = None if (scan_all or root.is_file()) else manifest_skill_files(root)
        if root.is_file():
            found: Iterable[Entry] = [(root, None, "skill", None)]
        elif root in shallow and not scan_all:
            found = [(p, None, "skill", None)
                     for p in _inventory_files(root, "SKILL.md", shallow=True)]
        elif manifest is not None:
            found = manifest
        else:
            found = [(p, None, "skill", None) for p in _inventory_files(root, "SKILL.md")]
        entries.extend(found)
    seen: Set[Path] = set()
    unique: List[Entry] = []
    for item in list(entries) + list(extra):
        try:
            resolved = item[0].resolve()
        except RuntimeError as exc:
            raise AuditError("could not resolve discovered path {}: {}".format(item[0], exc)) from None
        except OSError:
            resolved = item[0]
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(item)
    if not unique:
        return []
    # Reads are I/O bound (often on an external disk); load in parallel but
    # keep discovery order so output is deterministic.
    workers = min(32, (os.cpu_count() or 4) * 4, len(unique))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda item: load_skill(*item), unique))


# --- Usage evidence -------------------------------------------------------

# A skill or command the user typed as /name is logged in their own message.
_TYPED_COMMAND_RE = re.compile(r"<command-name>/?([^<\s]+)</command-name>")


def usage_counts(transcript_root: Optional[Path] = None) -> Dict[str, int]:
    """Count real invocations in local Claude Code transcripts: Skill tool calls
    made by the model, plus /commands the user typed."""
    root = transcript_root or (Path.home() / ".claude" / "projects")
    counts: Dict[str, int] = {}
    if not root.is_dir():
        return counts
    for jsonl in root.rglob("*.jsonl"):
        try:
            with jsonl.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except (ValueError, RecursionError):
                        continue
                    if not isinstance(record, dict):
                        continue
                    kind = record.get("type")
                    message = record.get("message")
                    content = message.get("content") if isinstance(message, dict) else None
                    names: List[str] = []
                    blocks = ([record] if kind == "tool_use" else
                              content if kind == "assistant" and isinstance(content, list) else [])
                    for block in blocks:
                        if not isinstance(block, dict) or block.get("type") != "tool_use":
                            continue
                        data = block.get("input")
                        if block.get("name") == "Skill" and isinstance(data, dict):
                            name = data.get("skill")
                            if isinstance(name, str) and name.strip():
                                names.append(name)
                    if kind == "user":
                        text_parts = ([content] if isinstance(content, str) else
                                      [b.get("text", "") for b in content
                                       if isinstance(b, dict) and b.get("type") == "text"]
                                      if isinstance(content, list) else [])
                        for part in text_parts:
                            if isinstance(part, str):
                                names.extend(_TYPED_COMMAND_RE.findall(part))
                    for name in names:
                        counts[name] = counts.get(name, 0) + 1
        except OSError:
            continue
    return counts


def resolve_usage(
    skill: Skill, counts: Dict[str, int], skills: Optional[Sequence[Skill]] = None,
) -> int:
    if skill.command in counts:
        return counts[skill.command]
    leaf = skill.command.rsplit(":", 1)[-1]
    if leaf not in counts:
        return 0
    if skills is not None:
        owners = {s.command for s in skills if s.command.rsplit(":", 1)[-1] == leaf}
        if owners != {skill.command}:
            # A local or legacy bare name does not identify one of several
            # namespaced entries. Preserve exact evidence instead of guessing.
            return 0
    return counts.get(leaf, 0)


# --- Findings -------------------------------------------------------------

SEVERITIES = {"error": 0, "warn": 1, "info": 2}


@dataclass
class Finding:
    rule: str
    severity: str
    command: str
    path: str
    message: str
    fix: str


def estimate_tokens(text: str, chars_per_token: float = DEFAULT_CHARS_PER_TOKEN) -> int:
    """Character-ratio token estimate.

    No tokenizer dependency. Useful for ranking listings, not
    exact. Pass --chars-per-token to recalibrate, or feed --json into a real
    tokenizer when you need precise numbers.
    """
    if not text:
        return 0
    return max(1, int(round(len(text) / chars_per_token)))


def _content_words(text: str) -> Set[str]:
    words = re.findall(r"[^\W_]+", text.casefold())
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def _jaccard(left: Set[str], right: Set[str]) -> float:
    if not left or not right:
        return 0.0
    union = len(left | right)
    return len(left & right) / union if union else 0.0


_SYMLINK_STUB_RE = re.compile(r"^[.\w/\\-]{1,300}\.(md|markdown)$")


def _looks_like_symlink_stub(body: str) -> bool:
    """A git symlink checked out as a plain file: one line holding a path."""
    stripped = body.strip()
    return bool(stripped) and "\n" not in stripped and bool(_SYMLINK_STUB_RE.match(stripped))


def cluster_by_description(
    skills: Sequence[Skill], similarity: float = DEFAULT_SIMILARITY
) -> List[List[Skill]]:
    """Group skills whose descriptions overlap past `similarity`.

    Exact word bags are grouped first, including large duplicate collections.
    Approximate pairs use an index of discriminative words to bound the work;
    descriptions made entirely of collection-wide common words can still hide
    approximate matches. This is a word-overlap heuristic, not a routing eval.
    """
    words = [_content_words(s.description) for s in skills]
    total = len(skills)
    if total < 2:
        return []

    index: Dict[str, List[int]] = {}
    for i, bag in enumerate(words):
        for word in bag:
            index.setdefault(word, []).append(i)
    # Skip words so common they carry no signal, but never below a floor:
    # in a small library every word is "common" and the filter would hide
    # the very duplicates it exists to find.
    max_doc_freq = max(50, int(total * 0.05))

    parent = list(range(total))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        root_i, root_j = find(i), find(j)
        if root_i != root_j:
            parent[max(root_i, root_j)] = min(root_i, root_j)

    exact: Dict[frozenset, int] = {}
    for i, bag in enumerate(words):
        if not bag:
            continue
        key = frozenset(bag)
        if key in exact:
            union(exact[key], i)
        else:
            exact[key] = i

    for i, bag in enumerate(words):
        candidates: Set[int] = set()
        for word in bag:
            bucket = index.get(word, ())
            if len(bucket) > max_doc_freq:
                continue
            candidates.update(j for j in bucket if j > i)
        for j in candidates:
            if find(i) != find(j) and _jaccard(bag, words[j]) >= similarity:
                union(i, j)

    groups: Dict[int, List[Skill]] = {}
    for i, skill in enumerate(skills):
        groups.setdefault(find(i), []).append(skill)
    return [sorted(g, key=lambda s: s.command) for g in groups.values() if len(g) > 1]


def _truthy(value: str) -> Optional[bool]:
    if getattr(value, "kind", "string") in ("sequence", "mapping"):
        return None
    token = value.strip().strip("\"'").lower()
    if token in TRUE_WORDS:
        return True
    if token in FALSE_WORDS:
        return False
    return None


def analyze(
    skills: Sequence[Skill],
    usage: Optional[Dict[str, int]] = None,
    portable: bool = False,
    body_line_budget: int = DEFAULT_BODY_LINE_BUDGET,
    similarity: float = DEFAULT_SIMILARITY,
    listing_budget: Optional[int] = None,
    chars_per_token: float = DEFAULT_CHARS_PER_TOKEN,
) -> List[Finding]:
    findings: List[Finding] = []

    def add(rule: str, severity: str, skill: Skill, message: str, fix: str) -> None:
        findings.append(Finding(rule, severity, skill.command, str(skill.path), message, fix))

    for skill in skills:
        fm = skill.frontmatter

        if any(p.startswith("unreadable") for p in skill.problems):
            add("SR007", "error", skill, "; ".join(skill.problems),
                "Check file permissions and encoding.")
            continue

        if "frontmatter-not-first-line" in skill.problems:
            add("SR001", "error", skill,
                "Frontmatter does not start on line 1, so the whole file is read as body "
                "and these metadata fields do not apply.",
                "Move the opening `---` to the very first line, with nothing above it.")
        elif "no-frontmatter" in skill.problems:
            if _looks_like_symlink_stub(skill.body):
                add("SR008", "error", skill,
                    "File contains a bare path, not a skill: a git symlink that was "
                    "checked out as a plain file (usual on Windows without symlink support).",
                    "Re-clone with symlinks enabled, or replace the stub with the real file.")
            else:
                add("SR001", "error", skill,
                    "No YAML frontmatter block.",
                    "Add a `---` delimited block with at least `description`.")
        if "unterminated-frontmatter" in skill.problems:
            add("SR006", "error", skill,
                "Frontmatter opens but never closes.",
                "Add the closing `---` line.")
        for problem in skill.problems:
            if problem.startswith("invalid-frontmatter:"):
                add("SR009", "error", skill,
                    "Cannot validate frontmatter with the supported YAML subset: " + problem.split(":", 1)[1].strip(),
                    "Correct invalid YAML or use scalar fields, flat lists and a shallow metadata map; "
                    "validate more complex YAML with a full YAML validator.")

        description = skill.description
        combined = " ".join(p for p in (description, skill.when_to_use) if p)
        # Command files are the older format: no description and no frontmatter
        # are normal for them, and the Agent Skills spec does not cover them, so
        # the skill-authoring rules below skip them.
        authoring = skill.kind == "skill"

        if authoring and not description:
            add("SR002", "error" if portable else "warn", skill,
                "No non-empty `description`. " + (
                    "The Agent Skills spec requires it." if portable else
                    "Claude Code falls back to the first non-empty line of the body."),
                "Add a description that says what the skill does and when to use it.")
        elif authoring and description and len(description) < 15:
            add("SR025", "warn", skill,
                "Description is {} characters. Too thin to route on.".format(len(description)),
                "Say what it does and name the trigger, in one sentence.")

        if len(combined) > LISTING_CHAR_CAP:
            add("SR003", "error", skill,
                "description + when_to_use is {} chars; the configured listing model "
                "caps it at {} characters.".format(
                    len(combined), LISTING_CHAR_CAP),
                "Put the trigger first and move the detail into the body.")

        disabled_model = _truthy(fm.get("disable-model-invocation", "false"))
        user_invocable = _truthy(fm.get("user-invocable", "true"))
        if disabled_model is True and user_invocable is False:
            add("SR004", "error", skill,
                "`disable-model-invocation: true` and `user-invocable: false`: direct "
                "/command invocation and automatic invocation are both disabled.",
                "Enable the invocation route the skill needs.")

        for bool_field in BOOL_FIELDS:
            if bool_field in fm and _truthy(fm[bool_field]) is None:
                add("SR005", "warn", skill,
                    "`{}: {}` is not a boolean.".format(bool_field, fm[bool_field]),
                    "Use true/false (yes/no/on/off/1/0 also work).")

        if authoring and description and not any(cue in combined.lower() for cue in TRIGGER_CUES):
            add("SR022", "warn", skill,
                "Description has no recognized trigger phrase (a heuristic, not proof of poor routing).",
                "Review whether the description states when to use the skill.")

        if skill.body_lines > body_line_budget:
            add("SR023", "warn", skill,
                "Body is {} non-blank lines. Invoked content persists across turns; "
                "compaction can truncate or drop it.".format(skill.body_lines),
                "Split the reference material into files the skill reads on demand.")

        if authoring:
            scalar_fields: Tuple[str, ...] = ("name", "description", "when_to_use")
            if portable:
                scalar_fields += ("license", "compatibility", "allowed-tools")
            for key in scalar_fields:
                if key in fm and getattr(fm[key], "kind", "string") != "string":
                    add("SR014", "error", skill,
                        "`{}` must be a string; found a YAML {}.".format(key, getattr(fm[key], "kind", "string")),
                        "Use a quoted string or a block scalar.")

        if portable and authoring:
            for key in sorted(fm):
                if key not in PORTABLE_FIELDS:
                    add("SR010", "error", skill,
                        "`{}` is not in the Agent Skills spec; claude.ai upload and "
                        "package_skill.py reject it outright.".format(key),
                        "Remove it, or keep the skill Claude Code-only.")
            name = fm.get("name", "")
            if (not name or len(name) > 64 or name != name.lower()
                    or not all(char.isalnum() or char == "-" for char in name)
                    or name.startswith("-") or name.endswith("-") or "--" in name
                    or name != _directory_name(skill.path)
                    or getattr(name, "kind", "string") != "string"):
                add("SR013", "error", skill,
                    "Portable `name` must be a 1-64 character lowercase alphanumeric/hyphen "
                    "string, with no edge or repeated hyphens, matching the parent directory.",
                    "Set `name` to the valid skill directory name; rename the directory if necessary.")
            if len(fm.get("description", "")) > 1024:
                add("SR014", "error", skill,
                    "`description` is {} chars; the Agent Skills spec allows 1024.".format(len(fm["description"])),
                    "Keep the trigger and summary within 1024 characters.")
            compat = fm.get("compatibility", "")
            if len(compat) > COMPATIBILITY_CAP:
                add("SR011", "error", skill,
                    "`compatibility` is {} chars; the spec allows {}.".format(
                        len(compat), COMPATIBILITY_CAP),
                    "Trim it.")
            elif "compatibility" in fm and not compat:
                add("SR014", "error", skill,
                    "`compatibility` must be non-empty when present.",
                    "Describe the environment requirements, or omit the field.")
            if "metadata" in fm:
                metadata = fm["metadata"]
                members = getattr(metadata, "members", None)
                if (getattr(metadata, "kind", "string") != "mapping" or not isinstance(members, dict)
                        or any(getattr(value, "kind", "string") != "string" for value in members.values())):
                    add("SR014", "error", skill,
                        "`metadata` must be a map from string keys to string values.",
                        "Use an indented map and quote numeric, boolean or null-looking values.")
        elif not portable:
            for key in sorted(fm):
                if key not in KNOWN_FIELDS:
                    add("SR012", "info", skill,
                        "Unrecognized frontmatter field `{}`.".format(key),
                        "Check for a typo, or move it under `metadata:`.")

    # --- Cross-skill rules ---
    by_command: Dict[str, List[Skill]] = {}
    for skill in skills:
        by_command.setdefault(skill.command.lower(), []).append(skill)
    for command, group in sorted(by_command.items()):
        if len(group) > 1:
            others = ", ".join(str(s.path) for s in group[1:])
            findings.append(Finding(
                "SR020", "warn", group[0].command, str(group[0].path),
                "{} skills answer to `/{}`; only one of them ever runs.".format(
                    len(group), command),
                "Rename or remove the duplicates: {}".format(others),
            ))

    routable = [s for s in skills if s.description and s.in_listing]
    for cluster in cluster_by_description(routable, similarity):
        head = cluster[0]
        names = ", ".join("/" + s.command for s in cluster[:4])
        if len(cluster) > 4:
            names += " and {} more".format(len(cluster) - 4)
        findings.append(Finding(
            "SR021", "warn", head.command, str(head.path),
            "{} skills form a description cluster linked by {:.0%}+ word-overlap pairs: {}. "
            "Not every pair in the cluster necessarily meets the threshold. "
            "This overlap may make automatic selection ambiguous; it is a heuristic.".format(
                len(cluster), similarity, names),
            "Differentiate the triggers, or merge them into one skill.",
        ))

    if usage is not None:
        for skill in skills:
            if resolve_usage(skill, usage, skills) == 0:
                findings.append(Finding(
                    "SR024", "info", skill.command, str(skill.path),
                    "No invocation found in the local transcripts scanned.",
                    "Check history coverage and installation age before removing it.",
                ))

    if listing_budget is not None:
        for skill in name_only_skills(skills, usage or {}, listing_budget, chars_per_token):
            findings.append(Finding(
                "SR030", "info", skill.command, str(skill.path),
                "The estimated listing model drops this description at the configured "
                "budget. Its name remains available; actual session ordering can differ.",
                "Disable unused plugins or local skills, shorten descriptions, or raise the listing "
                "budget with skillListingBudgetFraction / SLASH_COMMAND_TOOL_CHAR_BUDGET.",
            ))

    findings.sort(key=lambda f: (SEVERITIES.get(f.severity, 3), f.rule, f.command))
    return findings


# --- Budget ---------------------------------------------------------------

@dataclass
class Budget:
    skills: int               # every discovered entry, skills and commands
    name_tokens: int          # every listed name; always in the listing
    desc_tokens: int          # descriptions the full listing wants (per-entry capped)
    body_tokens: int
    bundle_bytes: int
    context_window: int
    listing_budget: int       # tokens the harness allows the listing (1% of window)
    commands: int = 0         # how many of `skills` are commands/*.md files
    hidden: int = 0           # kept out of context (disable-model-invocation, overrides)
    retained_desc_tokens: Optional[int] = None

    @property
    def requested_tokens(self) -> int:
        """What the whole listing would cost if nothing were dropped."""
        return self.name_tokens + self.desc_tokens

    @property
    def always_on_tokens(self) -> int:
        """Estimated retained names and descriptions in the configured model."""
        if self.retained_desc_tokens is not None:
            return self.name_tokens + self.retained_desc_tokens
        remaining = max(0, self.listing_budget - self.name_tokens)
        return self.name_tokens + min(self.desc_tokens, remaining)

    @property
    def overflows(self) -> bool:
        return self.requested_tokens > self.listing_budget

    @property
    def context_percent(self) -> float:
        return 100.0 * self.always_on_tokens / self.context_window if self.context_window else 0.0

    @property
    def budget_percent(self) -> float:
        return 100.0 * self.requested_tokens / self.listing_budget if self.listing_budget else 0.0


def _name_tokens(skill: Skill, chars_per_token: float) -> int:
    """The listing names each entry by the command you'd type."""
    return estimate_tokens(skill.command + ": ", chars_per_token)


def _desc_tokens(skill: Skill, chars_per_token: float) -> int:
    if skill.override == "name-only":
        return 0
    return estimate_tokens(skill.routing_text[:LISTING_CHAR_CAP], chars_per_token)


def listing_tokens(skill: Skill, chars_per_token: float) -> int:
    """Requested cost of an eligible entry, before collection budget/precedence."""
    if not skill.in_listing:
        return 0
    return _name_tokens(skill, chars_per_token) + _desc_tokens(skill, chars_per_token)


def _listed(skills: Sequence[Skill]) -> List[Skill]:
    """The entries eligible for the estimated listing: one per
    command name. When a skill and a command file share a name, the skill wins,
    so the duplicate never reaches the listing (SR020 still reports it)."""
    chosen: Dict[str, Skill] = {}
    for skill in skills:
        if not skill.in_listing:
            continue
        key = skill.command.lower()
        if key not in chosen or (chosen[key].kind == "command" and skill.kind == "skill"):
            chosen[key] = skill
    return list(chosen.values())


def name_only_skills(
    skills: Sequence[Skill], usage: Dict[str, int], listing_budget: int, chars_per_token: float
) -> List[Skill]:
    """Listed skills whose description won't fit the listing budget.

    Names of everything in the listing are always kept; the remaining budget
    fills with descriptions most-used first (Claude Code drops the least-used
    ones), tie-broken by the cheaper description so more of them fit. Skills
    hidden from the model, or set to name-only on purpose, are not reported.
    """
    listed = _listed(skills)
    remaining = max(0, listing_budget - sum(_name_tokens(s, chars_per_token) for s in listed))
    dropped: List[Skill] = []
    candidates = [s for s in listed if s.override != "name-only" and s.routing_text]
    ordered = sorted(
        candidates,
        key=lambda s: (-resolve_usage(s, usage, skills), _desc_tokens(s, chars_per_token)),
    )
    for skill in ordered:
        cost = _desc_tokens(skill, chars_per_token)
        if remaining >= cost:
            remaining -= cost
        else:
            dropped.append(skill)
    return dropped


def retained_listing_costs(
    skills: Sequence[Skill], usage: Optional[Dict[str, int]],
    listing_budget: int, chars_per_token: float,
) -> Dict[int, int]:
    """Per-entry costs for the same estimated retention model used by SR030.

    Identity keys distinguish shadowed entries with the same command name.
    They are internal only and are never serialized.
    """
    dropped = {id(s) for s in name_only_skills(skills, usage or {}, listing_budget, chars_per_token)}
    return {id(s): _name_tokens(s, chars_per_token) +
            (0 if id(s) in dropped else _desc_tokens(s, chars_per_token))
            for s in _listed(skills)}


def budget(
    skills: Sequence[Skill],
    chars_per_token: float,
    context_window: int,
    budget_fraction: float = DEFAULT_BUDGET_FRACTION,
    listing_budget_tokens: Optional[int] = None,
    usage: Optional[Dict[str, int]] = None,
) -> Budget:
    """Size the listing. Only skills advertised to the model count toward it;
    `listing_budget_tokens` pins the budget (SLASH_COMMAND_TOOL_CHAR_BUDGET)."""
    listed = _listed(skills)
    if listing_budget_tokens is None:
        listing_budget_tokens = int(round(context_window * budget_fraction))
    retained = retained_listing_costs(skills, usage, listing_budget_tokens, chars_per_token)
    names = sum(_name_tokens(s, chars_per_token) for s in listed)
    return Budget(
        skills=len(skills),
        name_tokens=names,
        desc_tokens=sum(_desc_tokens(s, chars_per_token) for s in listed),
        body_tokens=sum(estimate_tokens(s.body, chars_per_token) for s in skills),
        bundle_bytes=sum(s.bundle_bytes for s in skills),
        context_window=context_window,
        listing_budget=listing_budget_tokens,
        commands=sum(1 for s in skills if s.kind == "command"),
        hidden=sum(1 for s in skills if not s.in_listing),
        retained_desc_tokens=sum(retained.values()) - names,
    )


# --- Reporting ------------------------------------------------------------

COLORS = {
    "error": "\033[31m", "warn": "\033[33m", "info": "\033[36m",
    "reset": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
}


def _paint(text: str, style: str, enabled: bool) -> str:
    if not enabled:
        return text
    return "{}{}{}".format(COLORS.get(style, ""), text, COLORS["reset"])


def _human_bytes(count: int) -> str:
    value = float(count)
    for unit in ("B", "KB", "MB"):
        if value < 1024:
            return "{:.0f}{}".format(value, unit) if unit == "B" else "{:.1f}{}".format(value, unit)
        value /= 1024
    return "{:.1f}GB".format(value)


def _display_text(text: str, preserve_layout: bool = False) -> str:
    """Render controls in untrusted file metadata as visible escape notation."""
    return "".join(char if preserve_layout and char in "\n\t" else
                   "\\x{:02x}".format(ord(char)) if ord(char) < 32 or 127 <= ord(char) <= 159
                   else "\\u{:04x}".format(ord(char)) if
                   0xD800 <= ord(char) <= 0xDFFF or ord(char) in (0xFFFE, 0xFFFF)
                   else char for char in text)


def render(
    skills: Sequence[Skill],
    findings: Sequence[Finding],
    totals: Budget,
    usage: Optional[Dict[str, int]],
    chars_per_token: float,
    top: int,
    color: bool,
    per_rule_limit: int = 20,
) -> str:
    out: List[str] = []

    def bold(text: str) -> str:
        return _paint(text, "bold", color)

    def dim(text: str) -> str:
        return _paint(text, "dim", color)

    errors = sum(1 for f in findings if f.severity == "error")
    warns = sum(1 for f in findings if f.severity == "warn")
    dead = sum(1 for f in findings if f.rule == "SR024")
    name_only = sum(1 for f in findings if f.rule == "SR030")

    out.append("")
    out.append(bold("skillrot {}".format(__version__)))
    out.append("")
    out.append(bold("  Context bill (estimated Claude Code listing)"))
    found = "{} skills".format(totals.skills - totals.commands)
    if totals.commands:
        found += " + {} commands".format(totals.commands)
    out.append("    {} discovered".format(found))
    if totals.hidden:
        out.append("    {} kept out of context (disable-model-invocation / skillOverrides)".format(
            totals.hidden))
    out.append("    ~{:,} tokens in the always-on listing  ({:.1f}% of a {:,}-token window)".format(
        totals.always_on_tokens, totals.context_percent, totals.context_window))
    out.append("    ~{:,} tok listing budget ({:.0f}% requested)".format(
        totals.listing_budget, totals.budget_percent))
    if totals.overflows:
        over = totals.requested_tokens - totals.listing_budget
        out.append("    " + _paint(
            "over budget by ~{:,} tok: the model predicts description drops".format(over),
            "warn", color))
    out.append("    ~{:,} tokens of skill bodies waiting to load".format(totals.body_tokens))
    out.append("    {} on disk".format(_human_bytes(totals.bundle_bytes)))
    out.append("")

    if totals.skills and top > 0:
        ranked = sorted(_listed(skills), key=lambda s: listing_tokens(s, chars_per_token), reverse=True)[:top]
        retained = retained_listing_costs(skills, usage, totals.listing_budget, chars_per_token)
        out.append(bold("  Heaviest requested listings") + dim("  (requested / estimated retained)"))
        for skill in ranked:
            fired = ""
            if usage is not None:
                count = resolve_usage(skill, usage, skills)
                fired = dim("  no observed calls") if count == 0 else dim("  {}x".format(count))
            out.append("    {:>5} / {:>5} tok  /{}{}".format(
                listing_tokens(skill, chars_per_token), retained.get(id(skill), 0), _display_text(skill.command), fired))
        out.append("")

    if findings:
        out.append(bold("  Findings"))
        current = None
        shown: Dict[str, int] = {}
        hidden: Dict[str, int] = {}
        for finding in findings:
            if finding.severity != current:
                current = finding.severity
                out.append("")
                out.append("  " + _paint(current.upper(), current, color))
            count = shown.get(finding.rule, 0)
            if per_rule_limit and count >= per_rule_limit:
                hidden[finding.rule] = hidden.get(finding.rule, 0) + 1
                continue
            shown[finding.rule] = count + 1
            out.append("    {} /{}".format(
                _paint(finding.rule, finding.severity, color), _display_text(finding.command)))
            out.append("      {}".format(_display_text(finding.message)))
            out.append("      {}".format(dim("fix: " + _display_text(finding.fix))))
        for rule in sorted(hidden):
            out.append("    {}  {}".format(
                _paint(rule, "info", color),
                dim("... and {} more (--full to show every one)".format(hidden[rule]))))
        out.append("")

    verdict = "{} error(s), {} warning(s)".format(errors, warns)
    if name_only:
        verdict += ", {} predicted name-only".format(name_only)
    if usage is not None:
        verdict += ", {} skill(s) with no observed calls".format(dead)
    out.append(bold("  " + verdict))
    out.append(dim("  Estimates use characters per token; this does not inspect a live session."))
    out.append("")
    return "\n".join(out)


def to_json(
    skills: Sequence[Skill],
    findings: Sequence[Finding],
    totals: Budget,
    usage: Optional[Dict[str, int]],
    chars_per_token: float,
) -> str:
    retained = retained_listing_costs(skills, usage, totals.listing_budget, chars_per_token)
    payload = {
        "schema_version": 1,
        "version": __version__,
        "model": {
            "harness": "claude-code",
            "estimated": True,
            "chars_per_token": chars_per_token,
            "listing_char_cap": LISTING_CHAR_CAP,
            "usage_available": usage is not None,
        },
        "budget": {
            "skills": totals.skills,
            "always_on_tokens": totals.always_on_tokens,
            "requested_tokens": totals.requested_tokens,
            "name_tokens": totals.name_tokens,
            "desc_tokens": totals.desc_tokens,
            "retained_desc_tokens": totals.retained_desc_tokens,
            "listing_budget": totals.listing_budget,
            "budget_percent": round(totals.budget_percent, 2),
            "overflows": totals.overflows,
            "commands": totals.commands,
            "hidden": totals.hidden,
            "body_tokens": totals.body_tokens,
            "bundle_bytes": totals.bundle_bytes,
            "context_window": totals.context_window,
            "context_percent": round(totals.context_percent, 2),
        },
        "skills": [
            {
                "command": s.command,
                "kind": s.kind,
                "in_listing": s.in_listing,
                "override": s.override,
                "path": str(s.path),
                "origin": s.origin,
                "plugin": s.plugin,
                "listing_tokens": listing_tokens(s, chars_per_token),
                "retained_listing_tokens": retained.get(id(s), 0),
                "body_tokens": estimate_tokens(s.body, chars_per_token),
                "body_lines": s.body_lines,
                "invocations": resolve_usage(s, usage, skills) if usage is not None else None,
            }
            for s in skills
        ],
        "findings": [
            {
                "rule": f.rule, "severity": f.severity, "command": f.command,
                "path": f.path, "message": f.message, "fix": f.fix,
            }
            for f in findings
        ],
    }
    # Escaped JSON remains valid Unicode after decoding and is safe through
    # Windows pipes whose active encoding cannot represent the audited path.
    return json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False)


# --- SVG visual -----------------------------------------------------------

def _svg_escape(text: str) -> str:
    return (_display_text(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def to_svg(
    skills: Sequence[Skill],
    totals: Budget,
    usage: Optional[Dict[str, int]],
    chars_per_token: float,
    top: int = 10,
) -> str:
    """A self-contained, theme-aware budget chart.

    One bar for the listing (filled to the budget line, overflow hatched) and a
    ranked bar per heaviest skill. No dependencies: the ranking is the point,
    the numbers are the 4-char-per-token estimate the rest of the tool uses.
    """
    ranked = sorted(_listed(skills), key=lambda s: listing_tokens(s, chars_per_token), reverse=True)[:top]
    row_h, pad_top, left, width = 30, 150, 250, 640
    height = pad_top + row_h * (len(ranked) + 1) + 40
    budget_line = totals.listing_budget or 1
    bar_scale = width / max(budget_line, totals.requested_tokens, 1)

    def bar_row(y, label, tokens, sub, fill):
        lx = left + min(tokens * bar_scale, width)
        note = _svg_escape("{:,} tok  {}".format(tokens, sub))
        return (
            '<text x="{lx0}" y="{ty}" class="lbl" text-anchor="end">{lab}</text>'
            '<rect x="{x}" y="{by}" width="{w:.1f}" height="16" rx="3" fill="{fill}"/>'
            '<text x="{tx:.1f}" y="{ty}" class="val">{note}</text>'
        ).format(lx0=left - 12, ty=y + 13, lab=_svg_escape(label), x=left, by=y,
                 w=min(tokens * bar_scale, width), fill=fill, tx=lx + 8, note=note)

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        'viewBox="0 0 {w} {h}" '
        'font-family="ui-monospace,Menlo,Consolas,monospace">'.format(w=left + width + 240, h=height),
        "<style>"
        ":root{--bg:#ffffff;--fg:#1a1a1a;--mut:#6b7280;--bar:#2563eb;--over:#dc2626;--line:#9ca3af}"
        "@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;"
        "--bar:#3b82f6;--over:#f85149;--line:#484f58}}"
        ".bg{fill:var(--bg)}.title{fill:var(--fg);font-size:22px;font-weight:700}"
        ".sub{fill:var(--mut);font-size:13px}.lbl{fill:var(--fg);font-size:12px}"
        ".val{fill:var(--mut);font-size:11px;dominant-baseline:middle}"
        ".hd{fill:var(--fg);font-size:13px;font-weight:600}"
        "</style>",
        '<rect class="bg" x="0" y="0" width="{w}" height="{h}"/>'.format(w=left + width + 240, h=height),
        '<text x="30" y="42" class="title">skillrot</text>',
        '<text x="30" y="68" class="sub">{}</text>'.format(_svg_escape(
            "{:,} entries  •  ~{:,} tok retained  •  {:.1f}% of a {:,}-tok window".format(
                totals.skills, totals.always_on_tokens, totals.context_percent, totals.context_window))),
        '<text x="30" y="90" class="sub">{}</text>'.format(_svg_escape(
            "listing budget {:,} tok  •  {:.0f}% requested{}".format(
                totals.listing_budget, totals.budget_percent,
                "  •  predicted description drops" if totals.overflows else "  •  estimated to fit"))),
        '<text x="30" y="{y}" class="hd">Listing</text>'.format(y=pad_top - 18),
    ]
    over_fill = "var(--over)" if totals.overflows else "var(--bar)"
    parts.append(bar_row(pad_top, "requested", totals.requested_tokens,
                         "names + descriptions", over_fill))
    # budget line
    bx = left + min(budget_line * bar_scale, width)
    parts.append(
        '<line x1="{bx:.1f}" y1="{y0}" x2="{bx:.1f}" y2="{y1}" stroke="var(--line)" '
        'stroke-dasharray="4 3"/>'
        '<text x="{bx:.1f}" y="{yt}" class="val" text-anchor="middle">budget</text>'.format(
            bx=bx, y0=pad_top - 8, y1=pad_top + 24, yt=pad_top - 12))
    parts.append('<text x="30" y="{y}" class="hd">Heaviest requested listings</text>'.format(
        y=pad_top + row_h + 12))
    for idx, s in enumerate(ranked):
        y = pad_top + row_h * (idx + 1) + 22
        sub = ""
        if usage is not None:
            c = resolve_usage(s, usage, skills)
            sub = "no observed calls" if c == 0 else "{}x".format(c)
        parts.append(bar_row(y, _display_text(s.command)[:30], listing_tokens(s, chars_per_token), sub, "var(--bar)"))
    parts.append("</svg>")
    return "".join(parts)


# --- CLI ------------------------------------------------------------------

class _ReportArgumentParser(argparse.ArgumentParser):
    def _print_message(self, message, file=None):
        if message:
            _write_stream(file if file is not None else sys.stderr,
                          _display_text(message, preserve_layout=True))


def build_parser() -> argparse.ArgumentParser:
    parser = _ReportArgumentParser(
        prog="skillrot",
        description="Find the dead weight in your agent's skill library.",
    )
    parser.add_argument(
        "paths", nargs="*", type=Path,
        help="Directories or SKILL.md files to scan. Default: installed Claude Code skills.")
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    parser.add_argument(
        "--portable", action="store_true",
        help="Check supported frontmatter against the six-field Agent Skills spec.")
    parser.add_argument(
        "--no-usage", action="store_true",
        help="Skip local transcript invocation evidence.")
    parser.add_argument(
        "--transcripts", type=Path, default=None,
        help="Transcript directory. Default: ~/.claude/projects")
    parser.add_argument("--top", type=int, default=10, help="How many heaviest skills to list.")
    parser.add_argument("--context-window", type=int, default=DEFAULT_CONTEXT_WINDOW)
    parser.add_argument(
        "--body-lines", type=int, default=DEFAULT_BODY_LINE_BUDGET,
        help="Flag skill bodies longer than this.")
    parser.add_argument(
        "--similarity", type=float, default=DEFAULT_SIMILARITY,
        help="Description overlap that counts as a collision (0-1).")
    parser.add_argument(
        "--chars-per-token", type=float, default=DEFAULT_CHARS_PER_TOKEN,
        help="Token estimate divisor (0.1-100).")
    parser.add_argument(
        "--budget-fraction", type=float, default=None,
        help="Listing budget as a fraction of the context window. Default: your "
             "skillListingBudgetFraction setting, else Claude Code's 0.01.")
    parser.add_argument(
        "--svg", type=Path, default=None,
        help="Write a budget chart (SVG) to this path.")
    parser.add_argument(
        "--all", action="store_true",
        help="Scan every SKILL.md instead of manifest-selected files; plugin ownership "
             "manifests are still validated. Recursive child directory links are skipped.")
    parser.add_argument(
        "--fail-on", choices=("never", "error", "warn"), default="never",
        help="Exit non-zero at this severity. Use in CI.")
    parser.add_argument(
        "--fail-over-budget", action="store_true",
        help="Exit non-zero when the listing needs more than its budget, i.e. "
             "descriptions would be dropped. Use in CI.")
    parser.add_argument(
        "--full", action="store_true",
        help="Print every finding instead of the first 20 per rule.")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--version", action="version", version="skillrot " + __version__)
    return parser


def _validate_cli_args(args) -> None:
    if not 0 < args.context_window <= sys.maxsize:
        raise AuditError("--context-window must be a positive integer within the platform range")
    for flag, value in (("--top", args.top), ("--body-lines", args.body_lines)):
        if value < 0:
            raise AuditError("{} must be non-negative".format(flag))
    if not math.isfinite(args.chars_per_token) or not 0.1 <= args.chars_per_token <= 100:
        raise AuditError("--chars-per-token must be finite and between 0.1 and 100")
    if not math.isfinite(args.similarity) or not 0 <= args.similarity <= 1:
        raise AuditError("--similarity must be finite and in [0, 1]")
    if args.budget_fraction is not None and (not math.isfinite(args.budget_fraction)
                                              or not 0 < args.budget_fraction <= 1):
        raise AuditError("--budget-fraction must be finite and in (0, 1]")


class _ClosedOutputPipe(Exception):
    """Only a stdout write can turn a closed pipe into normal termination."""


def _write_stream(stream, text: str) -> None:
    """Keep reports usable on narrow terminal encodings without losing JSON."""
    try:
        try:
            stream.write(text)
        except UnicodeEncodeError:
            encoding = getattr(stream, "encoding", None) or "utf-8"
            stream.write(text.encode(encoding, errors="backslashreplace").decode(encoding))
        stream.flush()
    except OSError as exc:
        # Windows reports a closed redirected output pipe as EINVAL, not EPIPE.
        if stream is sys.stdout and (isinstance(exc, BrokenPipeError)
                                     or (os.name == "nt" and exc.errno == 22 and not stream.isatty())):
            try:
                stream.close()
            except OSError:
                pass
            raise _ClosedOutputPipe from None
        raise


def _protect_audited_sources(output: Path, skills: Sequence[Skill]) -> None:
    """Refuse a chart target that aliases a discovered skill or command file."""
    try:
        resolved = output.resolve()
        exists = output.exists()
        for skill in skills:
            if resolved == skill.path.resolve() or (exists and output.samefile(skill.path)):
                raise AuditError("SVG output would overwrite an audited source file: {}".format(output))
    except RuntimeError as exc:
        raise AuditError("could not resolve SVG output safely: {}".format(exc)) from None


def _run_audit(args) -> int:

    # When the user passes paths, audit everything under them. With no paths we
    # audit the supported local Claude Code profile: personal and project
    # skills one level deep, command files, and the plugins enabled in settings.
    home, cwd = Path.home(), Path.cwd()
    settings: dict = {}
    extra: List[Entry] = []
    if args.paths:
        roots, shallow = list(args.paths), []
    else:
        settings = load_settings(home, cwd)
        roots = default_roots(cwd)
        plugins = installed_plugin_entries(home, settings)
        if plugins is not None:
            roots = [r for r in roots if r.name != "plugins"]
            extra += plugins
        shallow = [r for r in roots if r.name != "plugins"]
        for folder in [home] + _project_dirs(cwd):
            extra += command_entries(folder / ".claude" / "commands")
    if not roots and not extra:
        raise AuditError("no skills found. Pass a path to scan.")

    missing = [r for r in roots if not r.exists()]
    if missing:
        raise AuditError("no such path: {}".format(", ".join(str(path) for path in missing)))
    if not args.no_usage and args.transcripts is not None and not args.transcripts.is_dir():
        raise AuditError("--transcripts must be an existing directory: {}".format(args.transcripts))

    skills = discover(roots, shallow_roots=shallow, scan_all=args.all, extra=extra)
    if not skills:
        raise AuditError("found no locally installable skills or commands under {}".format(
            ", ".join(str(r) for r in roots)))

    overrides = {str(k).lower(): v for k, v in (settings.get("skillOverrides") or {}).items()}
    for skill in skills:
        # Claude Code applies skillOverrides to local skills, not plugin skills.
        if skill.origin != "plugin":
            skill.override = overrides.get(skill.command.lower())

    fraction = args.budget_fraction
    if fraction is None:
        fraction = settings.get("skillListingBudgetFraction")
        fraction = fraction if isinstance(fraction, (int, float)) else DEFAULT_BUDGET_FRACTION
    char_budget = (os.environ.get("SLASH_COMMAND_TOOL_CHAR_BUDGET")
                   or (settings.get("env") or {}).get("SLASH_COMMAND_TOOL_CHAR_BUDGET"))
    fixed = None
    if args.budget_fraction is None and char_budget:
        try:
            if not str(char_budget).isascii() or not str(char_budget).isdigit():
                raise ValueError
            value = int(char_budget)
            if not 0 < value <= sys.maxsize:
                raise ValueError
        except ValueError:
            raise AuditError("SLASH_COMMAND_TOOL_CHAR_BUDGET must be a positive integer within the platform range") from None
        fixed = int(value / args.chars_per_token)

    usage = None if args.no_usage else usage_counts(args.transcripts)
    if not usage:
        # Empty or unavailable history is insufficient evidence to recommend
        # uninstalling every skill as never fired.
        usage = None
    totals = budget(skills, args.chars_per_token, args.context_window, fraction, fixed, usage=usage)
    findings = analyze(
        skills, usage=usage, portable=args.portable,
        body_line_budget=args.body_lines, similarity=args.similarity,
        listing_budget=totals.listing_budget, chars_per_token=args.chars_per_token,
    )

    if args.svg:
        try:
            _protect_audited_sources(args.svg, skills)
            args.svg.write_text(
                to_svg(skills, totals, usage, args.chars_per_token, args.top), encoding="utf-8")
            _write_stream(sys.stderr, "skillrot: wrote {}\n".format(_display_text(str(args.svg))))
        except OSError as exc:
            raise AuditError("could not write {}: {}".format(args.svg, exc)) from None

    if args.json:
        _write_stream(sys.stdout, to_json(skills, findings, totals, usage, args.chars_per_token) + "\n")
    else:
        color = (not args.no_color and sys.stdout.isatty()
                 and os.environ.get("NO_COLOR") is None)
        _write_stream(sys.stdout, render(skills, findings, totals, usage, args.chars_per_token,
                                        args.top, color, 0 if args.full else 20) + "\n")

    if args.fail_on == "error" and any(f.severity == "error" for f in findings):
        return 1
    if args.fail_on == "warn" and any(f.severity in ("error", "warn") for f in findings):
        return 1
    if args.fail_over_budget and totals.overflows:
        return 1
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        _validate_cli_args(args)
        return _run_audit(args)
    except _ClosedOutputPipe:
        return 0
    except (AuditError, OSError) as exc:
        _write_stream(sys.stderr, "skillrot: {}\n".format(_display_text(str(exc))))
        return 2


if __name__ == "__main__":
    sys.exit(main())
