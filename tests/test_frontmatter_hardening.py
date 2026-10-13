"""Regression tests for bounded YAML parsing and portable authoring checks."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import skillrot


class FrontmatterHardeningTests(unittest.TestCase):
    def parse(self, header):
        return skillrot.parse_frontmatter("---\n" + header + "\n---\nBody.\n")

    def findings(self, header, portable=False, name="thing"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / name / "SKILL.md"
            path.parent.mkdir()
            path.write_text("---\n" + header + "\n---\nBody.\n", encoding="utf-8")
            return skillrot.analyze([skillrot.load_skill(path)], portable=portable)

    def errors(self, header):
        return [f for f in self.findings(header, portable=True) if f.severity == "error"]

    def test_boolean_comments_preserve_invocation_controls(self):
        findings = self.findings("name: thing\ndescription: Use when asked to check.\n"
                                 "disable-model-invocation: true # manual\n"
                                 "user-invocable: false # hidden")
        self.assertIn("SR004", {f.rule for f in findings})
        self.assertNotIn("SR005", {f.rule for f in findings})

    def test_quoted_keys_cannot_hide_nonportable_fields(self):
        findings = self.findings('name: thing\n"description": "Use when asked."\n'
                                 '"argument-hint": "[file]"', portable=True)
        self.assertIn("SR010", {f.rule for f in findings})

    def test_comment_marker_inside_quotes_is_text(self):
        fm, _, problems = self.parse('description: "Use when #tag appears." # comment')
        self.assertEqual(fm["description"], "Use when #tag appears.")
        self.assertEqual(problems, [])

    def test_quoted_escapes_decode_without_losing_trigger_text(self):
        fm, _, problems = self.parse("name: 'it''s'\ndescription: \"Use when \\\"quoted\\\" paths use \\\\ here.\"")
        self.assertEqual(fm["name"], "it's")
        self.assertEqual(fm["description"], 'Use when "quoted" paths use \\ here.')
        self.assertEqual(problems, [])

    def test_multiline_quoted_scalar_folds_newlines(self):
        fm, _, problems = self.parse('description: "Use when asked\n  to inspect a skill."')
        self.assertEqual(fm["description"], "Use when asked to inspect a skill.")
        self.assertEqual(problems, [])

    def test_multiline_quoted_scalar_preserves_blank_line(self):
        fm, _, problems = self.parse('description: "Use when asked\n\n  to inspect a skill."')
        self.assertEqual(fm["description"], "Use when asked\nto inspect a skill.")
        self.assertEqual(problems, [])

    def test_multiline_double_quote_backslash_joins_lines(self):
        fm, _, problems = self.parse('description: "Use when asked to inspect a ski\\\n  ll."')
        self.assertEqual(fm["description"], "Use when asked to inspect a skill.")
        self.assertEqual(problems, [])

    def test_plain_scalar_preserves_blank_line_paragraph(self):
        fm, _, problems = self.parse('description: Use when asked\n\n  to inspect a skill.')
        self.assertEqual(fm["description"], "Use when asked\nto inspect a skill.")
        self.assertEqual(problems, [])

    def test_indented_block_delimiter_does_not_end_frontmatter(self):
        fm, body, problems = self.parse('description: |-\n  Use when asked.\n  ---\n  More.')
        self.assertEqual(fm["description"], "Use when asked.\n---\nMore.")
        self.assertEqual(body, "Body.")
        self.assertEqual(problems, [])

    def test_flat_flow_list_preserves_quoted_comment_characters(self):
        fm, _, problems = self.parse('allowed-tools: ["Read", "Bash(git:*) # scope"] # outside')
        self.assertEqual(fm.get("allowed-tools"), "Read Bash(git:*) # scope")
        self.assertEqual(problems, [])

    def test_indentless_block_sequence_is_supported(self):
        fm, _, problems = self.parse('allowed-tools:\n- Read\n- Bash(git:*)')
        self.assertEqual(fm.get("allowed-tools"), "Read Bash(git:*)")
        self.assertEqual(problems, [])

    def test_plain_continuation_comments_do_not_become_routing_text(self):
        fm, _, problems = self.parse("description: Use when asked # first\n"
                                     "  # standalone comment\n  to inspect a skill. # last")
        self.assertEqual(fm["description"], "Use when asked to inspect a skill.")
        self.assertEqual(problems, [])

    def test_plain_continuations_preserve_quotes_and_boolean_looking_text(self):
        for continuation in ('"hello"', 'on', '123', '&literal'):
            with self.subTest(continuation=continuation):
                fm, _, problems = self.parse('description: Use when the user says\n  ' + continuation)
                self.assertEqual(fm.get("description"), 'Use when the user says ' + continuation)
                self.assertEqual(problems, [])

    def test_empty_flow_items_and_sequence_indicator_are_invalid(self):
        for value in ('[Bash,, Read]', '[, Bash]', '[,,]', '-'):
            with self.subTest(value=value):
                _, _, problems = self.parse('allowed-tools: ' + value)
                self.assertTrue(any(p.startswith('invalid-frontmatter:') for p in problems))

    def test_top_level_comments_do_not_split_a_metadata_mapping(self):
        fm, _, problems = self.parse('metadata:\n  a: text\n# comment\n  b: text')
        self.assertEqual(problems, [])
        self.assertEqual(getattr(fm.get("metadata"), "members", None), {'a': 'text', 'b': 'text'})

    def test_flow_delimiters_require_quoted_items(self):
        for value in ('[Bash]]', '[Bash[, Read]', '[Bash{x, Read]', '[Bash}x, Read]'):
            with self.subTest(value=value):
                _, _, problems = self.parse('allowed-tools: ' + value)
                self.assertTrue(any(p.startswith('invalid-frontmatter:') for p in problems))
        for value in ('["Bash]"]', '[Bash:Read]'):
            with self.subTest(value=value):
                _, _, problems = self.parse('allowed-tools: ' + value)
                self.assertEqual(problems, [])

    def test_literal_scalar_preserves_indentation_and_comments(self):
        fm, _, problems = self.parse("description: |- # literal\n  Use when asked.\n    # example\n  Last.")
        self.assertEqual(fm["description"], "Use when asked.\n  # example\nLast.")
        self.assertEqual(problems, [])

    def test_folded_scalar_preserves_paragraph_break(self):
        fm, _, problems = self.parse("description: >-\n  Use when asked.\n\n  Inspect a skill.")
        self.assertEqual(fm["description"], "Use when asked.\nInspect a skill.")
        self.assertEqual(problems, [])

    def test_block_scalar_cannot_silently_change_uneven_indentation(self):
        findings = self.findings("name: thing\ndescription: |-\n    Use when asked.\n  Less indent.")
        self.assertIn("SR009", {f.rule for f in findings})

    def test_supported_block_tool_list_is_not_flattened_with_dashes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "thing" / "SKILL.md"
            path.parent.mkdir()
            path.write_text("---\nname: thing\ndescription: Use when asked.\n"
                            "allowed-tools:\n  - Read\n  - Bash(git:*) # scoped\n---\nBody.", encoding="utf-8")
            skill = skillrot.load_skill(path)
            self.assertEqual(skill.frontmatter["allowed-tools"], "Read Bash(git:*)")
            self.assertNotIn("SR009", {f.rule for f in skillrot.analyze([skill])})
            self.assertIn("SR014", {f.rule for f in skillrot.analyze([skill], portable=True)})

    def test_simple_metadata_string_map_passes_portable(self):
        self.assertEqual(self.errors("name: thing\ndescription: Use when asked.\n"
                                     "metadata:\n  author: 'A # team'\n  version: \"1.0\""), [])

    def test_metadata_nonstring_value_is_not_silently_stringified(self):
        for value in ("true", "1", "null"):
            with self.subTest(value=value):
                findings = self.errors("name: thing\ndescription: Use when asked.\n"
                                       "metadata:\n  version: " + value)
                self.assertIn("SR014", {f.rule for f in findings})

    def test_scalar_metadata_is_not_a_valid_map(self):
        self.assertIn("SR014", {f.rule for f in self.errors(
            "name: thing\ndescription: Use when asked.\nmetadata: author")})

    def test_invalid_or_unsupported_yaml_cannot_pass_validation(self):
        cases = ("description: \"unterminated", "description: [broken",
                 "description: &alias Use when asked.", "description: *alias",
                 "description: !!str Use when asked.", "metadata: {author: team}",
                 "description: Use when asked.\ndescription: duplicate",
                 "description: Use when asked.\nbroken line",
                 "description: Use when asked.\n  nested: value",
                 "description: Use when asked.\n\tbad indent",
                 "description: |2\n  explicit indent",
                 "description: invalid\x00control",
                 'description: "\\ud800"')
        for header in cases:
            with self.subTest(header=header):
                findings = self.findings("name: thing\n" + header)
                self.assertIn("SR009", {f.rule for f in findings})

    def test_missing_description_is_warning_for_claude(self):
        findings = self.findings("name: thing")
        item = next(f for f in findings if f.rule == "SR002")
        self.assertEqual(item.severity, "warn")

    def test_empty_frontmatter_still_requires_portable_fields(self):
        findings = self.errors("")
        self.assertIn("SR002", {f.rule for f in findings})
        self.assertIn("SR013", {f.rule for f in findings})

    def test_nonstring_routing_fields_are_rejected(self):
        for value in ("true", "42", "1.5", "null"):
            with self.subTest(value=value):
                self.assertIn("SR014", {f.rule for f in self.errors(
                    "name: thing\ndescription: " + value)})

    def test_quoted_numeric_description_is_a_string(self):
        self.assertNotIn("SR014", {f.rule for f in self.errors('name: thing\ndescription: "42"')})

    def test_portable_description_limit_is_1024(self):
        self.assertEqual(self.errors("name: thing\ndescription: " + "x" * 1024), [])
        self.assertIn("SR014", {f.rule for f in self.errors("name: thing\ndescription: " + "x" * 1025)})

    def test_description_limit_includes_quoted_whitespace(self):
        self.assertIn("SR014", {f.rule for f in self.errors(
            'name: thing\ndescription: "' + "x" * 1024 + ' "')})

    def test_portable_name_constraints_and_directory_match(self):
        for name in ("", "Thing", "-thing", "thing-", "two--things", "two things", "x" * 65, "other", "123"):
            with self.subTest(name=name):
                self.assertIn("SR013", {f.rule for f in self.errors(
                    "name: " + name + "\ndescription: Use when asked.")})

    def test_portable_unicode_lowercase_name_matches_directory(self):
        self.assertEqual([f for f in self.findings("name: пример\ndescription: Use when asked.",
                                                portable=True, name="пример") if f.severity == "error"], [])

    def test_portable_relative_and_absolute_paths_match_the_same_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "thing"
            root.mkdir()
            path = root / "SKILL.md"
            path.write_text('---\nname: thing\ndescription: Use when asked.\n---\nBody.\n', encoding="utf-8")
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                for spelling in (Path("SKILL.md"), Path("./SKILL.md"), Path("../thing/SKILL.md"), path):
                    with self.subTest(path=spelling):
                        findings = skillrot.analyze([skillrot.load_skill(spelling)], portable=True)
                        self.assertNotIn("SR013", {f.rule for f in findings})
            finally:
                os.chdir(old_cwd)

    def test_portable_compatibility_limit_is_error(self):
        findings = self.errors("name: thing\ndescription: Use when asked.\ncompatibility: " + "x" * 501)
        self.assertIn("SR011", {f.rule for f in findings})

    def test_invalid_utf8_is_an_unreadable_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_bytes(b"---\nname: thing\ndescription: bad \xff\n---\n")
            findings = skillrot.analyze([skillrot.load_skill(path)])
            self.assertIn("SR007", {f.rule for f in findings})


if __name__ == "__main__":
    unittest.main()
