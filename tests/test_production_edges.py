"""Production regressions for typed input, diagnostics and source preservation."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import skillrot


class TypedFrontmatterEdgeTests(unittest.TestCase):
    def skill(self, header):
        fm, body, problems = skillrot.parse_frontmatter(
            "---\nname: thing\ndescription: Use when asked.\n" + header + "\n---\nBody."
            if not header.startswith("description:") else
            "---\nname: thing\n" + header + "\n---\nBody."
        )
        return skillrot.Skill(Path("thing/SKILL.md"), Path("thing"), "scanned",
                              "thing", fm, body, problems)

    def test_collection_cannot_become_a_string_via_plain_continuation(self):
        for value in ("[]", "[Use when asked.]", "[true]"):
            with self.subTest(value=value):
                skill = self.skill("description: " + value + "\n  Use when asked.")
                findings = skillrot.analyze([skill], portable=True)
                self.assertIn("SR009", {f.rule for f in findings})
                self.assertEqual(skill.frontmatter, {})

    def test_collection_comments_do_not_erase_type_evidence(self):
        skill = self.skill("description: [Use when asked.]\n  # comment")
        self.assertEqual(getattr(skill.frontmatter["description"], "kind"), "sequence")
        self.assertIn("SR014", {f.rule for f in skillrot.analyze([skill])})
        self.assertNotIn("SR009", {f.rule for f in skillrot.analyze([skill])})

    def test_metadata_boolean_and_null_keys_are_not_string_keys(self):
        for key in ("true", "false", "null", "on"):
            with self.subTest(key=key):
                skill = self.skill("metadata:\n  " + key + ": text")
                self.assertIn("SR009", {f.rule for f in skillrot.analyze([skill], portable=True)})

    def test_quoted_boolean_and_null_metadata_keys_remain_strings(self):
        skill = self.skill('metadata:\n  "true": text\n  "null": text')
        self.assertEqual(getattr(skill.frontmatter["metadata"], "members"),
                         {"true": "text", "null": "text"})
        self.assertEqual([f for f in skillrot.analyze([skill], portable=True)
                          if f.severity == "error"], [])

    def test_boolean_collections_are_flagged_and_do_not_hide_the_skill(self):
        for field in ("disable-model-invocation", "user-invocable", "background"):
            with self.subTest(field=field):
                skill = self.skill(field + ": [true]")
                self.assertIn("SR005", {f.rule for f in skillrot.analyze([skill])})
                self.assertTrue(skill.in_listing)

    def test_folded_keep_chomping_preserves_trailing_blank_lines(self):
        for suffix, expected in (("", "first last\n"),
                                 ("\n", "first last\n\n"),
                                 ("\n\n", "first last\n\n\n")):
            with self.subTest(suffix=repr(suffix)):
                skill = self.skill("description: >+\n  first\n  last" + suffix)
                self.assertEqual(skill.frontmatter.get("description"), expected)


class OperationalSourceBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "thing" / "SKILL.md"
        self.path.parent.mkdir()
        self.path.write_text("---\nname: thing\ndescription: Use when asked.\n---\nBody.",
                             encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                patch.dict(os.environ, {"SLASH_COMMAND_TOOL_CHAR_BUDGET": ""}):
            try:
                code = skillrot.main(args)
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_missing_explicit_transcript_directory_is_an_operational_failure(self):
        code, out, err = self.cli([str(self.path), "--json", "--transcripts",
                                  str(self.root / "missing")])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("--transcripts", err)

    def test_file_is_not_an_explicit_transcript_directory(self):
        code, out, err = self.cli([str(self.path), "--json", "--transcripts", str(self.path)])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("--transcripts", err)

    def test_no_usage_does_not_require_an_explicit_transcript_path(self):
        code, out, _ = self.cli([str(self.path), "--json", "--no-usage", "--transcripts",
                                str(self.root / "missing")])
        self.assertEqual(code, 0)
        self.assertIsNone(json.loads(out)["skills"][0]["invocations"])

    def test_operational_error_paths_cannot_emit_terminal_controls(self):
        code, _, err = self.cli(["missing\x1b]52;c;dGVzdA==\x07", "--no-usage"])
        self.assertEqual(code, 2)
        self.assertNotIn("\x1b", err)
        self.assertNotIn("\x07", err)

    def test_c1_controls_cannot_escape_reports_or_diagnostics(self):
        for control in ("\x9b", "\x9d", "\x85"):
            with self.subTest(control=repr(control), channel="stderr"):
                code, _, err = self.cli(["missing" + control + "name", "--no-usage"])
                self.assertEqual(code, 2)
                self.assertNotIn(control, err)
            with self.subTest(control=repr(control), channel="report"):
                skill = skillrot.Skill(self.path, self.path.parent, "scanned",
                                      "evil" + control + "name",
                                      {"description": "Use when asked."}, "body")
                totals = skillrot.budget([skill], 4.0, 200_000)
                report = skillrot.render([skill], [], totals, None, 4.0, 10, False)
                self.assertNotIn(control, report)

    def test_argparse_errors_cannot_emit_terminal_controls(self):
        code, _, err = self.cli(["--unknown\x1b]52;c;dGVzdA==\x07"])
        self.assertEqual(code, 2)
        self.assertNotIn("\x1b", err)
        self.assertNotIn("\x07", err)

    def test_svg_status_path_cannot_emit_terminal_controls(self):
        # Newlines and tab characters are legal POSIX filename characters;
        # Windows rejects them before any successful write can be tested.
        if os.name == "nt":
            self.skipTest("Control-character filenames are unavailable on Windows")
        target = self.root / "chart\x1b]52;c;dGVzdA==\x07.svg"
        code, _, err = self.cli([str(self.path), "--no-usage", "--svg", str(target)])
        self.assertEqual(code, 0)
        self.assertTrue(target.is_file())
        self.assertNotIn("\x1b", err)
        self.assertNotIn("\x07", err)

    def test_svg_status_is_safe_when_the_filesystem_accepts_a_control_path(self):
        # A narrow filesystem boundary double lets Windows exercise the same
        # status message without asking NTFS to create a forbidden filename.
        target = self.root / "chart\x1b]52;c;dGVzdA==\x07.svg"
        with patch.object(Path, "write_text", return_value=0):
            code, _, err = self.cli([str(self.path), "--no-usage", "--svg", str(target)])
        self.assertEqual(code, 0)
        self.assertNotIn("\x1b", err)
        self.assertNotIn("\x07", err)

    def test_svg_cannot_overwrite_an_audited_skill(self):
        original = self.path.read_bytes()
        code, out, err = self.cli([str(self.path), "--no-usage", "--svg", str(self.path)])
        self.assertEqual(code, 2)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(out, "")
        self.assertIn("audited", err.lower())

    def test_svg_cannot_overwrite_a_hardlinked_audited_skill(self):
        target = self.root / "chart.svg"
        try:
            os.link(self.path, target)
        except (OSError, NotImplementedError):
            self.skipTest("Hard links unavailable on this filesystem")
        original = self.path.read_bytes()
        code, _, _ = self.cli([str(self.path), "--no-usage", "--svg", str(target)])
        self.assertEqual(code, 2)
        self.assertEqual(self.path.read_bytes(), original)

    def deny_scandir(self, denied):
        # Replace only the filesystem enumeration boundary. The actual layout,
        # discovery, parser, CLI and streams remain real.
        actual_scandir = os.scandir

        def guarded(path):
            if Path(path).resolve() == denied.resolve():
                raise PermissionError(13, "directory enumeration denied", str(path))
            return actual_scandir(path)

        return patch.object(skillrot.os, "scandir", side_effect=guarded)

    def test_recursive_inventory_failure_cannot_report_a_clean_partial_library(self):
        denied = self.root / "denied"
        nested = denied / "nested"
        nested.mkdir(parents=True)
        (nested / "SKILL.md").write_bytes(self.path.read_bytes())
        with self.deny_scandir(denied):
            code, out, err = self.cli([str(self.root), "--no-usage", "--portable",
                                      "--json", "--fail-on", "error"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("denied", err)

    def test_shallow_inventory_surfaces_denied_skill_directory(self):
        denied = self.root / "denied"
        denied.mkdir()
        (denied / "SKILL.md").write_bytes(self.path.read_bytes())
        with self.deny_scandir(denied), self.assertRaises(skillrot.AuditError):
            skillrot.discover([self.root], shallow_roots=[self.root])

    def test_plugin_skill_inventory_surfaces_denied_component_directory(self):
        plugin = self.root / "plugin"
        manifest = plugin / ".claude-plugin" / "plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text('{"name": "p"}', encoding="utf-8")
        visible = plugin / "skills" / "thing"
        denied = plugin / "skills" / "denied"
        visible.mkdir(parents=True)
        denied.mkdir()
        (visible / "SKILL.md").write_bytes(self.path.read_bytes())
        (denied / "SKILL.md").write_bytes(self.path.read_bytes())
        with self.deny_scandir(denied):
            code, out, err = self.cli([str(plugin), "--no-usage", "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("denied", err)

    def test_plugin_command_inventory_surfaces_denied_nested_directory(self):
        plugin = self.root / "plugin"
        manifest = plugin / ".claude-plugin" / "plugin.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text('{"name": "p"}', encoding="utf-8")
        denied = plugin / "commands" / "denied"
        denied.mkdir(parents=True)
        (plugin / "commands" / "visible.md").write_text("Visible command.", encoding="utf-8")
        (denied / "hidden.md").write_text("Hidden command.", encoding="utf-8")
        with self.deny_scandir(denied):
            code, out, err = self.cli([str(plugin), "--no-usage", "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("denied", err)

    def test_local_command_inventory_surfaces_denied_nested_directory(self):
        commands = self.root / "commands"
        denied = commands / "denied"
        denied.mkdir(parents=True)
        (commands / "visible.md").write_text("Visible command.", encoding="utf-8")
        (denied / "hidden.md").write_text("Hidden command.", encoding="utf-8")
        with self.deny_scandir(denied), self.assertRaises(skillrot.AuditError):
            skillrot.command_entries(commands)

    def test_absent_optional_commands_directory_stays_empty(self):
        self.assertEqual(skillrot.command_entries(self.root / "absent"), [])

    def directory_link(self, link, target):
        try:
            link.symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            if os.name != "nt":
                self.skipTest("Directory links unavailable on this filesystem")
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode:
                self.skipTest("Neither directory symlinks nor junctions are available")

    def test_recursive_inventory_does_not_follow_child_directory_links(self):
        with tempfile.TemporaryDirectory() as outside:
            other = Path(outside) / "other"
            other.mkdir()
            (other / "SKILL.md").write_bytes(self.path.read_bytes())
            link = self.root / "linked"
            self.directory_link(link, Path(outside))
            code, out, _ = self.cli([str(self.root), "--no-usage", "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(len(json.loads(out)["skills"]), 1)
            # An explicit root is intentionally followed; only recursive child
            # links are excluded from a tree's implicit inventory.
            code, out, _ = self.cli([str(link), "--no-usage", "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(len(json.loads(out)["skills"]), 1)

    def test_recursive_directory_link_cycle_terminates_without_duplicate_inventory(self):
        self.directory_link(self.root / "cycle", self.root)
        try:
            result = subprocess.run([sys.executable, str(Path(skillrot.__file__).resolve()),
                                     str(self.root), "--no-usage", "--json"],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, timeout=5)
        except subprocess.TimeoutExpired:
            self.fail("Directory-link cycle made inventory traversal fail to terminate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["skills"]), 1)

    def test_bundle_footprint_does_not_count_directory_link_cycles(self):
        assets = self.path.parent / "assets"
        assets.mkdir()
        (assets / "data.txt").write_bytes(b"x" * 128)
        self.directory_link(assets / "cycle", assets)
        expected = len(self.path.read_bytes()) + 128
        code, out, err = self.cli([str(self.path), "--no-usage", "--json"])
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["budget"]["bundle_bytes"], expected)

    def test_bundle_footprint_excludes_files_behind_child_directory_links(self):
        with tempfile.TemporaryDirectory() as outside:
            (Path(outside) / "large.txt").write_bytes(b"x" * 4096)
            self.directory_link(self.path.parent / "linked", Path(outside))
            expected = len(self.path.read_bytes())
            code, out, err = self.cli([str(self.path), "--no-usage", "--json"])
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["budget"]["bundle_bytes"], expected)

    def test_discovered_path_resolution_loop_is_an_operational_failure(self):
        actual_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            if path == self.path:
                # Python 3.9-3.12 reports an infinite symlink resolution loop
                # as RuntimeError. Newer Python may report OSError instead.
                raise RuntimeError("Symlink loop from " + str(path))
            return actual_resolve(path, *args, **kwargs)

        with patch.object(Path, "resolve", resolve):
            try:
                code, out, err = self.cli([str(self.path), "--no-usage", "--json"])
            except RuntimeError as exc:
                self.fail("Resolution error escaped the CLI boundary: " + str(exc))
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("resolve", err.lower())
        self.assertNotIn("Traceback", err)


if __name__ == "__main__":
    unittest.main()
