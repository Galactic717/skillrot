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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

__version__ = "0.1.0"

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
        fm[key] = _strip_quotes(value)
        i += 1

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

    @property
    def description(self) -> str:
        return self.frontmatter.get("description", "").strip()

    @property
    def when_to_use(self) -> str:
        return self.frontmatter.get("when_to_use", "").strip()

    @property
    def listing_text(self) -> str:
        """The text the harness puts in the always-on skill listing."""
        parts = [self.frontmatter.get("name", self.command)]
        combined = " ".join(p for p in (self.description, self.when_to_use) if p)
        if combined:
            parts.append(combined)
        return ": ".join(parts)

    @property
    def body_lines(self) -> int:
        return len([ln for ln in self.body.splitlines() if ln.strip()])


def _is_version_dir(name: str) -> bool:
    return bool(re.fullmatch(r"v?\d+(\.\d+)*[A-Za-z0-9.+-]*", name))


def _plugin_name_for(skill_dir: Path) -> Optional[str]:
    """Walk up from a skill directory to name the plugin that ships it."""
    for parent in skill_dir.parents:
        if parent.name != "skills":
            continue
        root = parent.parent
        manifest = root / ".claude-plugin" / "plugin.json"
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8", errors="replace"))
                name = data.get("name")
                if name:
                    return str(name)
            except (ValueError, OSError, AttributeError):
                pass
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


def _bundle_bytes(skill_dir: Path) -> int:
    total = 0
    try:
        for entry in skill_dir.rglob("*"):
            if entry.is_file():
                try:
                    total += entry.stat().st_size
                except OSError:
                    pass
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


def load_skill(path: Path) -> Skill:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:  # unreadable file is a finding, not a crash
        return Skill(
            path=path, root=path.parent, origin="scanned", command=path.parent.name,
            frontmatter={}, body="", problems=["unreadable: {}".format(exc)],
        )
    fm, body, problems = parse_frontmatter(text)
    origin, plugin = _classify(path)
    directory = _directory_name(path)
    if plugin:
        # Plugin skills take their last command segment from `name`, else the dir.
        leaf = fm.get("name") or directory
        command = leaf if leaf.startswith(plugin + ":") else "{}:{}".format(plugin, leaf)
    else:
        command = directory or fm.get("name", "") or path.stem
    return Skill(
        path=path, root=path.parent, origin=origin, command=command,
        frontmatter=fm, body=body, problems=problems, plugin=plugin,
        bundle_bytes=_bundle_bytes(path.parent),
    )


def default_roots() -> List[Path]:
    home = Path.home()
    candidates = [
        home / ".claude" / "skills",
        home / ".claude" / "plugins",
        home / ".codex" / "skills",
        home / ".cursor" / "skills",
        home / ".config" / "agent-skills",
        Path.cwd() / ".claude" / "skills",
    ]
    return [c for c in candidates if c.is_dir()]


def discover(roots: Sequence[Path]) -> List[Skill]:
    seen: Set[Path] = set()
    skills: List[Skill] = []
    for root in roots:
        if root.is_file():
            found: Iterable[Path] = [root]
        else:
            found = sorted(root.rglob("SKILL.md"))
        for path in found:
            try:
                resolved = path.resolve()
            except OSError:
                resolved = path
            if resolved in seen:
                continue
            seen.add(resolved)
            skills.append(load_skill(path))
    return skills


# --- Usage evidence -------------------------------------------------------

_SKILL_CALL_RE = re.compile(
    r'"name"\s*:\s*"Skill"\s*,\s*"input"\s*:\s*\{\s*"skill"\s*:\s*"([^"]+)"'
)


def usage_counts(transcript_root: Optional[Path] = None) -> Dict[str, int]:
    """Count real Skill invocations in local Claude Code transcripts."""
    root = transcript_root or (Path.home() / ".claude" / "projects")
    counts: Dict[str, int] = {}
    if not root.is_dir():
        return counts
    for jsonl in root.rglob("*.jsonl"):
        try:
            with jsonl.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if '"Skill"' not in line:
                        continue
                    for name in _SKILL_CALL_RE.findall(line):
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

        if fm and not description:
            add("SR002", "error", skill,
                "No `description`. Routing falls back to the first paragraph of the body.",
                "Add a description that says what the skill does and when to use it.")
        elif description and len(description) < 15:
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

        if description and not any(cue in description.lower() for cue in TRIGGER_CUES):
            add("SR022", "warn", skill,
                "Description never says *when* to use the skill, only what it is.",
                "Append a trigger clause: 'Use when the user asks to ...'.")

        if skill.body_lines > body_line_budget:
            add("SR023", "warn", skill,
                "Body is {} non-blank lines and stays in context for the rest of the "
                "session once it fires.".format(skill.body_lines),
                "Split the reference material into files the skill reads on demand.")

        if portable:
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
        else:
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

    routable = [
        s for s in skills
        if s.description
        and _truthy(s.frontmatter.get("disable-model-invocation", "false")) is not True
    ]
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

    findings.sort(key=lambda f: (SEVERITIES.get(f.severity, 3), f.rule, f.command))
    return findings


# --- Budget ---------------------------------------------------------------

@dataclass
class Budget:
    skills: int
    always_on_tokens: int
    body_tokens: int
    bundle_bytes: int
    context_window: int

    @property
    def context_percent(self) -> float:
        return 100.0 * self.always_on_tokens / self.context_window if self.context_window else 0.0


def listing_tokens(skill: Skill, chars_per_token: float) -> int:
    return estimate_tokens(skill.listing_text[:LISTING_CHAR_CAP], chars_per_token)


def budget(skills: Sequence[Skill], chars_per_token: float, context_window: int) -> Budget:
    return Budget(
        skills=len(skills),
        always_on_tokens=sum(listing_tokens(s, chars_per_token) for s in skills),
        body_tokens=sum(estimate_tokens(s.body, chars_per_token) for s in skills),
        bundle_bytes=sum(s.bundle_bytes for s in skills),
        context_window=context_window,
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

    out.append("")
    out.append(bold("skillrot {}".format(__version__)))
    out.append("")
    out.append(bold("  Context bill"))
    out.append("    {} skills discovered".format(totals.skills))
    out.append("    ~{:,} tokens in the always-on listing  ({:.1f}% of a {:,}-token window)".format(
        totals.always_on_tokens, totals.context_percent, totals.context_window))
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
            "body_tokens": totals.body_tokens,
            "bundle_bytes": totals.bundle_bytes,
            "context_window": totals.context_window,
            "context_percent": round(totals.context_percent, 2),
        },
        "skills": [
            {
                "command": s.command,
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
        "--fail-on", choices=("never", "error", "warn"), default="never",
        help="Exit non-zero at this severity. Use in CI.")
    parser.add_argument(
        "--full", action="store_true",
        help="Print every finding instead of the first 20 per rule.")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--version", action="version", version="skillrot " + __version__)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    roots = list(args.paths) if args.paths else default_roots()
    if not roots:
        sys.stderr.write("skillrot: no skills found. Pass a path to scan.\n")
        return 2

    for path in [r for r in roots if not r.exists()]:
        sys.stderr.write("skillrot: no such path: {}\n".format(path))
    roots = [r for r in roots if r.exists()]
    if not roots:
        return 2

    skills = discover(roots)
    if not skills:
        sys.stderr.write("skillrot: found no SKILL.md under {}\n".format(
            ", ".join(str(r) for r in roots)))
        return 2

    usage = None if args.no_usage else usage_counts(args.transcripts)
    findings = analyze(
        skills, usage=usage, portable=args.portable,
        body_line_budget=args.body_lines, similarity=args.similarity,
    )
    totals = budget(skills, args.chars_per_token, args.context_window)

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
