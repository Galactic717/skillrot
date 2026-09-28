#!/usr/bin/env python3
"""skillrot - find the dead weight in your agent's skill library.

Every skill you install costs context on every single message, whether or not
it ever fires. skillrot measures that bill, finds skills that can never run,
and flags the SKILL.md mistakes that silently break a skill.

Zero dependencies. Python 3.9+.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

__version__ = "0.3.1"

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

_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*)\s*:\s*(.*)$")


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_frontmatter(text: str) -> Tuple[Dict[str, str], str, List[str]]:
    """Split a SKILL.md into (frontmatter, body, structural problems).

    Deliberately not a full YAML parser: skills only ever need top-level
    scalars plus the *names* of the other keys.
    ponytail: hand-rolled subset keeps the tool dependency-free. Swap in
    PyYAML only if a rule ever needs to read nested values.
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
        if lines[i].strip() in ("---", "..."):
            end = i
            break
    if end is None:
        problems.append("unterminated-frontmatter")
        return {}, text, problems

    fm: Dict[str, str] = {}
    i = 1
    while i < end:
        raw = lines[i]
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        if raw[:1] in (" ", "\t", "-"):  # continuation of the previous key
            i += 1
            continue
        match = _KEY_RE.match(raw)
        if not match:
            i += 1
            continue
        key, value = match.group(1), match.group(2).strip()
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            block: List[str] = []
            i += 1
            while i < end and (not lines[i].strip() or lines[i][:1] in (" ", "\t")):
                block.append(lines[i].strip())
                i += 1
            joiner = "\n" if value.startswith("|") else " "
            fm[key] = joiner.join(block).strip()
            continue
        if value == "":
            # Nested map or block list. Collect it raw so length rules still work.
            block = []
            i += 1
            while i < end and (not lines[i].strip() or lines[i][:1] in (" ", "\t", "-")):
                block.append(lines[i].strip())
                i += 1
            fm[key] = " ".join(block).strip()
            continue
        # Plain scalar. YAML folds indented continuation lines with spaces, so
        # `description: foo\n  bar baz` is one value "foo bar baz". Collect them
        # or the routing text is silently truncated to its first line.
        parts = [value]
        i += 1
        while i < end and lines[i][:1] in (" ", "\t") and lines[i].strip():
            parts.append(lines[i].strip())
            i += 1
        fm[key] = _strip_quotes(value) if len(parts) == 1 else " ".join(parts).strip()

    body = "\n".join(lines[end + 1:])
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
        combined = " ".join(p for p in (self.description, self.when_to_use) if p)
        if combined:
            return combined
        for line in self.body.splitlines():
            if line.strip():
                return line.strip().lstrip("#").strip()
        return ""

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


@lru_cache(maxsize=None)
def _plugin_json_name(manifest: str) -> Optional[str]:
    """Read a plugin.json `name`, cached: sibling skills share one manifest."""
    try:
        data = json.loads(Path(manifest).read_text(encoding="utf-8", errors="replace"))
        name = data.get("name")
        return str(name) if name else None
    except (ValueError, OSError, AttributeError):
        return None


def _plugin_name_for(skill_dir: Path) -> Optional[str]:
    """Walk up from a skill directory to name the plugin that ships it."""
    for parent in skill_dir.parents:
        if parent.name != "skills":
            continue
        root = parent.parent
        manifest = root / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            name = _plugin_json_name(str(manifest))
            if name:
                return name
        if _is_version_dir(root.name) and root.parent != root:
            return root.parent.name
        return root.name
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
        dirs[:] = [d for d in dirs if d not in _PRUNE_DIRS]
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
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:  # unreadable file is a finding, not a crash
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
    """Skill install directories on this machine (plus other harnesses' ones)."""
    home = Path.home()
    candidates = [
        home / ".claude" / "skills",
        home / ".claude" / "plugins",
        home / ".codex" / "skills",
        home / ".cursor" / "skills",
        home / ".config" / "agent-skills",
    ] + [d / ".claude" / "skills" for d in _project_dirs(cwd or Path.cwd())]
    return [c for c in candidates if c.is_dir()]


def command_entries(root: Path) -> List[Entry]:
    """Legacy command files: commands/deploy.md is /deploy and
    commands/frontend/component.md is /frontend:component."""
    if not root.is_dir():
        return []
    entries: List[Entry] = []
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root).with_suffix("")
        entries.append((path, None, "command", ":".join(rel.parts)))
    return entries


def _read_json(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return data if isinstance(data, dict) else None
    except (ValueError, OSError):
        return None


def _as_paths(value) -> List[str]:
    if isinstance(value, str):
        return [value]
    return [p for p in value if isinstance(p, str)] if isinstance(value, list) else []


def _plugin_entries(
    plugin_root: Path, entry: Optional[dict] = None, name: Optional[str] = None
) -> List[Entry]:
    """Everything one plugin adds to the listing: skills and commands.

    Skills: default `skills/<name>/SKILL.md`, plus any manifest `skills` paths
    (a folder of skill folders, or one folder holding SKILL.md); a plugin with
    only a root SKILL.md loads as a single skill. Commands: `commands/*.md`,
    unless the manifest `commands` key replaces that default. With no
    plugin.json, the marketplace entry is the manifest.
    ponytail: the object form of `commands` (inline name -> source map) is
    skipped; add it if a real plugin needs counting that way.
    """
    manifest = _read_json(plugin_root / ".claude-plugin" / "plugin.json") or entry or {}
    plugin = str(manifest.get("name") or name or (entry or {}).get("name")
                 or plugin_root.resolve().name)
    extra = _as_paths(manifest.get("skills"))
    skills: List[Path] = []
    for folder in [plugin_root / "skills"] + [plugin_root / p for p in extra]:
        if (folder / "SKILL.md").is_file():
            skills.append(folder / "SKILL.md")
        elif folder.is_dir():
            skills.extend(sorted(folder.glob("*/SKILL.md")))
    if not skills and not extra and (plugin_root / "SKILL.md").is_file():
        skills.append(plugin_root / "SKILL.md")
    found: List[Entry] = [(p, plugin, "skill", None) for p in skills]

    command_paths = (_as_paths(manifest["commands"]) if "commands" in manifest
                     else ["commands"])
    for rel in command_paths:
        target = plugin_root / rel
        if target.is_file():
            files = [target]
        elif target.is_dir():
            files = sorted(target.glob("*.md"))
        else:
            files = []
        found.extend((f, plugin, "command", "{}:{}".format(plugin, f.stem))
                     for f in files if f.suffix == ".md")
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
    # The checkout itself can be a plugin even when its marketplace entry points
    # at a remote copy of the same repo (source: github), so check both.
    if (root / ".claude-plugin" / "plugin.json").is_file():
        found.extend(_plugin_entries(root))
    market = _read_json(root / ".claude-plugin" / "marketplace.json") or {}
    for entry in market.get("plugins") or []:
        source = entry.get("source") if isinstance(entry, dict) else None
        if isinstance(source, str):
            found.extend(_plugin_entries(root / source, entry))
    # Nothing installable resolved locally: fall back to the recursive scan.
    return found or None


def load_settings(home: Path, cwd: Path) -> dict:
    """Merge Claude Code settings: user, then project, then local (later wins;
    enabledPlugins, skillOverrides and env merge key by key)."""
    merged: dict = {}
    files = [home / ".claude" / "settings.json"]
    for folder in reversed(_project_dirs(cwd)):
        files += [folder / ".claude" / "settings.json", folder / ".claude" / "settings.local.json"]
    for path in files:
        data = _read_json(path) or {}
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
    known_marketplaces.json. Returns None when no plugins are configured, so the
    caller can fall back to scanning ~/.claude/plugins. Scanning that folder
    blindly counts every plugin in every cloned marketplace, enabled or not.
    """
    enabled = settings.get("enabledPlugins")
    if not isinstance(enabled, dict):
        return None
    plugins_dir = home / ".claude" / "plugins"
    installed = (_read_json(plugins_dir / "installed_plugins.json") or {}).get("plugins") or {}
    markets = _read_json(plugins_dir / "known_marketplaces.json") or {}
    found: List[Entry] = []
    for key, on in sorted(enabled.items()):
        if on is not True:
            continue
        name, _, market = key.partition("@")
        root: Optional[Path] = None
        entry: Optional[dict] = None
        for install in installed.get(key) or []:
            path = Path(str((install or {}).get("installPath", "")))
            if str(path) not in ("", ".") and path.is_dir():
                root = path
                break
        info = markets.get(market) if isinstance(markets.get(market), dict) else {}
        location = info.get("installLocation") or (info.get("source") or {}).get("path")
        if location:
            catalog = _read_json(Path(location) / ".claude-plugin" / "marketplace.json") or {}
            entry = next((p for p in catalog.get("plugins") or []
                          if isinstance(p, dict) and p.get("name") == name), None)
            if root is None and entry and isinstance(entry.get("source"), str):
                candidate = Path(location) / entry["source"]
                root = candidate if candidate.is_dir() else None
        if root is not None:
            found.extend(_plugin_entries(root, entry, name))
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
        elif root in shallow:
            found = [(p, None, "skill", None) for p in sorted(root.glob("*/SKILL.md"))]
        elif manifest is not None:
            found = manifest
        else:
            found = [(p, None, "skill", None) for p in sorted(root.rglob("SKILL.md"))]
        entries.extend(found)
    seen: Set[Path] = set()
    unique: List[Entry] = []
    for item in list(entries) + list(extra):
        try:
            resolved = item[0].resolve()
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

_SKILL_CALL_RE = re.compile(
    r'"name"\s*:\s*"Skill"\s*,\s*"input"\s*:\s*\{\s*"skill"\s*:\s*"([^"]+)"'
)


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
                    names: List[str] = []
                    if '"Skill"' in line:
                        names += _SKILL_CALL_RE.findall(line)
                    if "<command-name>" in line and '"type":"user"' in line:
                        names += _TYPED_COMMAND_RE.findall(line)
                    for name in names:
                        counts[name] = counts.get(name, 0) + 1
        except OSError:
            continue
    return counts


def resolve_usage(skill: Skill, counts: Dict[str, int]) -> int:
    if skill.command in counts:
        return counts[skill.command]
    leaf = skill.command.rsplit(":", 1)[-1]
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

    ponytail: no tokenizer dependency. Close enough to rank offenders, not
    exact. Pass --chars-per-token to recalibrate, or feed --json into a real
    tokenizer when you need precise numbers.
    """
    if not text:
        return 0
    return max(1, int(round(len(text) / chars_per_token)))


def _content_words(text: str) -> Set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
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

    Pairs are drawn from an inverted index of discriminative words rather than
    compared all-against-all, which keeps a 4,500-skill library well under a
    second. ponytail: a description built entirely from library-wide common
    words finds no candidates and is skipped. Lower --similarity if you want
    those too.
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
                "and the skill has no description at all.",
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

        description = skill.description
        combined = " ".join(p for p in (description, skill.when_to_use) if p)
        # Command files are the older format: no description and no frontmatter
        # are normal for them, and the Agent Skills spec does not cover them, so
        # the skill-authoring rules below skip them.
        authoring = skill.kind == "skill"

        if authoring and fm and not description:
            add("SR002", "error", skill,
                "No `description`. Routing falls back to the first non-empty line of the body.",
                "Add a description that says what the skill does and when to use it.")
        elif authoring and description and len(description) < 15:
            add("SR025", "warn", skill,
                "Description is {} characters. Too thin to route on.".format(len(description)),
                "Say what it does and name the trigger, in one sentence.")

        if len(combined) > LISTING_CHAR_CAP:
            add("SR003", "error", skill,
                "description + when_to_use is {} chars; the listing truncates at {}, so "
                "everything past the cutoff never reaches the router.".format(
                    len(combined), LISTING_CHAR_CAP),
                "Put the trigger first and move the detail into the body.")

        disabled_model = _truthy(fm.get("disable-model-invocation", "false"))
        user_invocable = _truthy(fm.get("user-invocable", "true"))
        if disabled_model is True and user_invocable is False:
            add("SR004", "error", skill,
                "`disable-model-invocation: true` and `user-invocable: false`: neither you "
                "nor the model can ever run this skill.",
                "Drop one of the two fields, or delete the skill.")

        for bool_field in BOOL_FIELDS:
            if bool_field in fm and _truthy(fm[bool_field]) is None:
                add("SR005", "warn", skill,
                    "`{}: {}` is not a boolean.".format(bool_field, fm[bool_field]),
                    "Use true/false (yes/no/on/off/1/0 also work).")

        if authoring and description and not any(cue in combined.lower() for cue in TRIGGER_CUES):
            add("SR022", "warn", skill,
                "Description never says *when* to use the skill, only what it is.",
                "Append a trigger clause: 'Use when the user asks to ...'.")

        if skill.body_lines > body_line_budget:
            add("SR023", "warn", skill,
                "Body is {} non-blank lines and stays in context for the rest of the "
                "session once it fires.".format(skill.body_lines),
                "Split the reference material into files the skill reads on demand.")

        if portable and authoring:
            for key in sorted(fm):
                if key not in PORTABLE_FIELDS:
                    add("SR010", "error", skill,
                        "`{}` is not in the Agent Skills spec; claude.ai upload and "
                        "package_skill.py reject it outright.".format(key),
                        "Remove it, or keep the skill Claude Code-only.")
            compat = fm.get("compatibility", "")
            if len(compat) > COMPATIBILITY_CAP:
                add("SR011", "warn", skill,
                    "`compatibility` is {} chars; the spec allows {}.".format(
                        len(compat), COMPATIBILITY_CAP),
                    "Trim it.")
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
            "{} skills share a near-identical description ({:.0%}+ word overlap): {}. "
            "The router picks between them on a coin flip.".format(
                len(cluster), similarity, names),
            "Differentiate the triggers, or merge them into one skill.",
        ))

    if usage is not None:
        for skill in skills:
            if resolve_usage(skill, usage) == 0:
                findings.append(Finding(
                    "SR024", "info", skill.command, str(skill.path),
                    "Never invoked in any local transcript.",
                    "Uninstall it, or fix the description so it can fire.",
                ))

    if listing_budget is not None:
        for skill in name_only_skills(skills, usage or {}, listing_budget, chars_per_token):
            findings.append(Finding(
                "SR030", "info", skill.command, str(skill.path),
                "Listing budget is full, so this skill lists name-only: its description "
                "is not in context and the router can't match it by keyword.",
                "Turn off skills you don't use (skillOverrides), or raise the listing "
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

    @property
    def requested_tokens(self) -> int:
        """What the whole listing would cost if nothing were dropped."""
        return self.name_tokens + self.desc_tokens

    @property
    def always_on_tokens(self) -> int:
        """What actually reaches the model: names, plus descriptions until the
        budget is full."""
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
    return estimate_tokens(skill.listing_text[:LISTING_CHAR_CAP], chars_per_token)


def _listed(skills: Sequence[Skill]) -> List[Skill]:
    """The entries the model actually sees: advertised to the model, one per
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
    remaining = listing_budget - sum(_name_tokens(s, chars_per_token) for s in listed)
    dropped: List[Skill] = []
    candidates = [s for s in listed if s.override != "name-only"]
    ordered = sorted(
        candidates,
        key=lambda s: (-resolve_usage(s, usage), _desc_tokens(s, chars_per_token)),
    )
    for skill in ordered:
        cost = _desc_tokens(skill, chars_per_token)
        if remaining >= cost:
            remaining -= cost
        else:
            dropped.append(skill)
    return dropped


def budget(
    skills: Sequence[Skill],
    chars_per_token: float,
    context_window: int,
    budget_fraction: float = DEFAULT_BUDGET_FRACTION,
    listing_budget_tokens: Optional[int] = None,
) -> Budget:
    """Size the listing. Only skills advertised to the model count toward it;
    `listing_budget_tokens` pins the budget (SLASH_COMMAND_TOOL_CHAR_BUDGET)."""
    listed = _listed(skills)
    if listing_budget_tokens is None:
        listing_budget_tokens = int(round(context_window * budget_fraction))
    return Budget(
        skills=len(skills),
        name_tokens=sum(_name_tokens(s, chars_per_token) for s in listed),
        desc_tokens=sum(_desc_tokens(s, chars_per_token) for s in listed),
        body_tokens=sum(estimate_tokens(s.body, chars_per_token) for s in skills),
        bundle_bytes=sum(s.bundle_bytes for s in skills),
        context_window=context_window,
        listing_budget=listing_budget_tokens,
        commands=sum(1 for s in skills if s.kind == "command"),
        hidden=sum(1 for s in skills if not s.in_listing),
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
    out.append(bold("  Context bill"))
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
            "over budget by ~{:,} tok: descriptions are being dropped".format(over),
            "warn", color))
    out.append("    ~{:,} tokens of skill bodies waiting to load".format(totals.body_tokens))
    out.append("    {} on disk".format(_human_bytes(totals.bundle_bytes)))
    out.append("")

    if totals.skills and top > 0:
        ranked = sorted(skills, key=lambda s: listing_tokens(s, chars_per_token), reverse=True)[:top]
        out.append(bold("  Heaviest listings") + dim("  (paid on every message)"))
        for skill in ranked:
            fired = ""
            if usage is not None:
                count = resolve_usage(skill, usage)
                fired = dim("  never fired") if count == 0 else dim("  {}x".format(count))
            out.append("    {:>5} tok  /{}{}".format(
                listing_tokens(skill, chars_per_token), skill.command, fired))
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
                _paint(finding.rule, finding.severity, color), finding.command))
            out.append("      {}".format(finding.message))
            out.append("      {}".format(dim("fix: " + finding.fix)))
        for rule in sorted(hidden):
            out.append("    {}  {}".format(
                _paint(rule, "info", color),
                dim("... and {} more (--full to show every one)".format(hidden[rule]))))
        out.append("")

    verdict = "{} error(s), {} warning(s)".format(errors, warns)
    if name_only:
        verdict += ", {} name-only".format(name_only)
    if usage is not None:
        verdict += ", {} skill(s) never fired".format(dead)
    out.append(bold("  " + verdict))
    out.append("")
    return "\n".join(out)


def to_json(
    skills: Sequence[Skill],
    findings: Sequence[Finding],
    totals: Budget,
    usage: Optional[Dict[str, int]],
    chars_per_token: float,
) -> str:
    payload = {
        "version": __version__,
        "budget": {
            "skills": totals.skills,
            "always_on_tokens": totals.always_on_tokens,
            "requested_tokens": totals.requested_tokens,
            "name_tokens": totals.name_tokens,
            "desc_tokens": totals.desc_tokens,
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
                "body_tokens": estimate_tokens(s.body, chars_per_token),
                "body_lines": s.body_lines,
                "invocations": resolve_usage(s, usage) if usage is not None else None,
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
    return json.dumps(payload, indent=2, ensure_ascii=False)


# --- SVG visual -----------------------------------------------------------

def _svg_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


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
    ranked = sorted(skills, key=lambda s: listing_tokens(s, chars_per_token), reverse=True)[:top]
    row_h, pad_top, left, width = 30, 150, 250, 640
    height = pad_top + row_h * (len(ranked) + 1) + 40
    heaviest = max((listing_tokens(s, chars_per_token) for s in ranked), default=1) or 1
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
        'font-family="ui-monospace,Menlo,Consolas,monospace">'.format(w=left + width + 40, h=height),
        "<style>"
        ":root{--bg:#ffffff;--fg:#1a1a1a;--mut:#6b7280;--bar:#2563eb;--over:#dc2626;--line:#9ca3af}"
        "@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;"
        "--bar:#3b82f6;--over:#f85149;--line:#484f58}}"
        ".bg{fill:var(--bg)}.title{fill:var(--fg);font-size:22px;font-weight:700}"
        ".sub{fill:var(--mut);font-size:13px}.lbl{fill:var(--fg);font-size:12px}"
        ".val{fill:var(--mut);font-size:11px;dominant-baseline:middle}"
        ".hd{fill:var(--fg);font-size:13px;font-weight:600}"
        "</style>",
        '<rect class="bg" x="0" y="0" width="{w}" height="{h}"/>'.format(w=left + width + 40, h=height),
        '<text x="30" y="42" class="title">skillrot</text>',
        '<text x="30" y="68" class="sub">{}</text>'.format(_svg_escape(
            "{:,} skills  •  {:,} tok always-on  •  {:.1f}% of a {:,}-tok window".format(
                totals.skills, totals.always_on_tokens, totals.context_percent, totals.context_window))),
        '<text x="30" y="90" class="sub">{}</text>'.format(_svg_escape(
            "listing budget {:,} tok  •  {:.0f}% requested{}".format(
                totals.listing_budget, totals.budget_percent,
                "  •  OVER: descriptions dropped" if totals.overflows else "  •  fits"))),
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
    parts.append('<text x="30" y="{y}" class="hd">Heaviest listings</text>'.format(
        y=pad_top + row_h + 12))
    for idx, s in enumerate(ranked):
        y = pad_top + row_h * (idx + 1) + 22
        sub = ""
        if usage is not None:
            c = resolve_usage(s, usage)
            sub = "never fired" if c == 0 else "{}x".format(c)
        parts.append(bar_row(y, s.command[:30], listing_tokens(s, chars_per_token), sub, "var(--bar)"))
    parts.append("</svg>")
    return "".join(parts)


# --- CLI ------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skillrot",
        description="Find the dead weight in your agent's skill library.",
    )
    parser.add_argument(
        "paths", nargs="*", type=Path,
        help="Directories or SKILL.md files to scan. Default: your installed skills.")
    parser.add_argument("--json", action="store_true", help="Machine-readable output.")
    parser.add_argument(
        "--portable", action="store_true",
        help="Check against the six-field Agent Skills spec (claude.ai / Skills API).")
    parser.add_argument(
        "--no-usage", action="store_true",
        help="Skip transcript analysis for never-fired skills.")
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
        help="Token estimate divisor.")
    parser.add_argument(
        "--budget-fraction", type=float, default=None,
        help="Listing budget as a fraction of the context window. Default: your "
             "skillListingBudgetFraction setting, else Claude Code's 0.01.")
    parser.add_argument(
        "--svg", type=Path, default=None,
        help="Write a budget chart (SVG) to this path.")
    parser.add_argument(
        "--all", action="store_true",
        help="Count every SKILL.md under a path, ignoring plugin/marketplace manifests.")
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


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    # When the user passes paths, audit everything under them. With no paths we
    # audit what this machine's Claude Code actually loads: personal and project
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
        sys.stderr.write("skillrot: no skills found. Pass a path to scan.\n")
        return 2

    for path in [r for r in roots if not r.exists()]:
        sys.stderr.write("skillrot: no such path: {}\n".format(path))
    roots = [r for r in roots if r.exists()]
    if not roots and not extra:
        return 2

    skills = discover(roots, shallow_roots=shallow, scan_all=args.all, extra=extra)
    if not skills:
        sys.stderr.write("skillrot: found no SKILL.md under {}\n".format(
            ", ".join(str(r) for r in roots)))
        return 2

    overrides = {str(k).lower(): v for k, v in (settings.get("skillOverrides") or {}).items()}
    for skill in skills:
        skill.override = overrides.get(skill.command.lower())

    fraction = args.budget_fraction
    if fraction is None:
        fraction = settings.get("skillListingBudgetFraction")
        fraction = fraction if isinstance(fraction, (int, float)) else DEFAULT_BUDGET_FRACTION
    char_budget = (os.environ.get("SLASH_COMMAND_TOOL_CHAR_BUDGET")
                   or (settings.get("env") or {}).get("SLASH_COMMAND_TOOL_CHAR_BUDGET"))
    fixed = None
    if args.budget_fraction is None and char_budget and str(char_budget).isdigit():
        fixed = int(int(char_budget) / args.chars_per_token)

    usage = None if args.no_usage else usage_counts(args.transcripts)
    totals = budget(skills, args.chars_per_token, args.context_window, fraction, fixed)
    findings = analyze(
        skills, usage=usage, portable=args.portable,
        body_line_budget=args.body_lines, similarity=args.similarity,
        listing_budget=totals.listing_budget, chars_per_token=args.chars_per_token,
    )

    if args.svg:
        try:
            args.svg.write_text(
                to_svg(skills, totals, usage, args.chars_per_token, args.top), encoding="utf-8")
            sys.stderr.write("skillrot: wrote {}\n".format(args.svg))
        except OSError as exc:
            sys.stderr.write("skillrot: could not write {}: {}\n".format(args.svg, exc))

    if args.json:
        print(to_json(skills, findings, totals, usage, args.chars_per_token))
    else:
        color = (not args.no_color and sys.stdout.isatty()
                 and os.environ.get("NO_COLOR") is None)
        print(render(skills, findings, totals, usage, args.chars_per_token,
                     args.top, color, 0 if args.full else 20))

    if args.fail_on == "error" and any(f.severity == "error" for f in findings):
        return 1
    if args.fail_on == "warn" and any(f.severity in ("error", "warn") for f in findings):
        return 1
    if args.fail_over_budget and totals.overflows:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
