"""Regression coverage for evidence, listing accounting and collision boundaries."""

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import skillrot


def entry(name, description="abcd" * 20, **fields):
    frontmatter = {"description": description}
    frontmatter.update(fields)
    return skillrot.Skill(Path(name) / "SKILL.md", Path(name), "scanned",
                          name, frontmatter, "body")


class ListingAccountingRegressionTests(unittest.TestCase):
    def test_unfilled_budget_does_not_bill_a_dropped_description(self):
        # Three one-token names, one 20-token description fits a 30-token budget.
        skills = [entry(name) for name in ("a", "b", "c")]
        totals = skillrot.budget(skills, 4.0, 200_000, listing_budget_tokens=30)
        self.assertEqual(totals.requested_tokens, 63)
        self.assertEqual(totals.always_on_tokens, 23)

    def test_aggregate_and_per_entry_costs_use_the_same_usage_order(self):
        skills = [entry("a", "x" * 64), entry("b", "x" * 32)]
        totals = skillrot.budget(skills, 4.0, 200_000, listing_budget_tokens=20,
                                usage={"a": 9})
        # Two one-token names; the frequently used 16-token description survives.
        self.assertEqual(totals.always_on_tokens, 18)
        payload = json.loads(skillrot.to_json(skills, [], totals, {"a": 9}, 4.0))
        self.assertEqual([s["retained_listing_tokens"] for s in payload["skills"]], [17, 1])

    def test_hidden_skill_has_zero_requested_listing_cost(self):
        skill = entry("manual", **{"disable-model-invocation": "true"})
        self.assertEqual(skillrot.listing_tokens(skill, 4.0), 0)

    def test_name_only_override_bills_only_the_name(self):
        skill = entry("manual")
        skill.override = "name-only"
        self.assertEqual(skillrot.listing_tokens(skill, 4.0), 2)

    def test_json_costs_reconcile_with_hidden_and_dropped_entries(self):
        skills = [entry("a"), entry("b"),
                  entry("manual", **{"disable-model-invocation": "true"})]
        totals = skillrot.budget(skills, 4.0, 200_000, listing_budget_tokens=25)
        payload = json.loads(skillrot.to_json(skills, [], totals, None, 4.0))
        self.assertEqual(payload.get("schema_version"), 1)
        self.assertTrue(payload["model"]["estimated"])
        costs = {row["command"]: row["retained_listing_tokens"]
                 for row in payload["skills"]}
        self.assertEqual(costs, {"a": 21, "b": 1, "manual": 0})
        self.assertEqual(sum(costs.values()), payload["budget"]["always_on_tokens"])

    def test_shadowed_command_is_not_billed_twice_in_json(self):
        first, shadow = entry("a"), entry("a")
        shadow.path = Path("other/SKILL.md")
        shadow.kind = "command"
        skills = [first, shadow]
        totals = skillrot.budget(skills, 4.0, 200_000)
        payload = json.loads(skillrot.to_json(skills, [], totals, {}, 4.0))
        self.assertEqual([row.get("retained_listing_tokens") for row in payload["skills"]],
                         [21, 0])
        self.assertEqual(totals.always_on_tokens, 21)

    def test_json_unicode_is_safe_in_legacy_windows_pipes(self):
        skill = entry("deploy")
        skill.path = Path("日本語/SKILL.md")
        text = skillrot.to_json([skill], [], skillrot.budget([skill], 4.0, 200_000),
                               None, 4.0)
        self.assertEqual(json.loads(text)["skills"][0]["path"], str(skill.path))
        self.assertTrue(text.isascii())  # Safe in a real Windows cp1251 stdout pipe.


class TranscriptEvidenceRegressionTests(unittest.TestCase):
    def counts(self, records):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "session.jsonl"
            path.write_text("\n".join(records), encoding="utf-8")
            return skillrot.usage_counts(Path(tmp))

    def test_tool_call_key_order_and_spacing_do_not_change_usage(self):
        record = {"input": {"args": "staging", "skill": "deploy"},
                  "name": "Skill", "type": "tool_use"}
        self.assertEqual(self.counts([json.dumps(record)]), {"deploy": 1})

    def test_nested_assistant_tool_blocks_are_counted(self):
        record = {"type": "assistant", "message": {"content": [
            {"type": "text", "text": "Running the skill"},
            {"input": {"skill": "plugin:deploy"}, "type": "tool_use", "name": "Skill"}
        ]}}
        self.assertEqual(self.counts([json.dumps(record)]), {"plugin:deploy": 1})

    def test_user_command_json_whitespace_is_irrelevant(self):
        record = {"type": "user", "message": {
            "content": "<command-name>/deploy</command-name>"}}
        self.assertEqual(self.counts([json.dumps(record)]), {"deploy": 1})

    def test_unrelated_records_and_invalid_json_are_not_invocations(self):
        self.assertEqual(self.counts([
            json.dumps({"type": "system", "name": "Skill", "input": {"skill": "deploy"}}),
            'invalid "name":"Skill","input":{"skill":"deploy"}',
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": '<command-name>/deploy</command-name>'}]}})
        ]), {})

    def test_tool_result_content_is_not_recursively_counted_as_an_invocation(self):
        record = {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": [
                {"type": "tool_use", "name": "Skill", "input": {"skill": "fake"}}]}
        ]}}
        self.assertEqual(self.counts([json.dumps(record)]), {})

    def test_bare_local_command_is_not_credited_to_namespaced_plugins(self):
        skills = [entry("deploy"), entry("one:deploy"), entry("two:deploy")]
        totals = skillrot.budget(skills, 4.0, 200_000, usage={"deploy": 3})
        payload = json.loads(skillrot.to_json(skills, [], totals, {"deploy": 3}, 4.0))
        self.assertEqual([s["invocations"] for s in payload["skills"]], [3, 0, 0])

    def test_ambiguous_bare_usage_has_no_attributed_plugin_invocations(self):
        skills = [entry("one:deploy"), entry("two:deploy")]
        totals = skillrot.budget(skills, 4.0, 200_000, usage={"deploy": 3, "one:deploy": 2})
        payload = json.loads(skillrot.to_json(skills, [], totals,
                                           {"deploy": 3, "one:deploy": 2}, 4.0))
        self.assertEqual([s["invocations"] for s in payload["skills"]], [2, 0])


class UntrustedReportTextTests(unittest.TestCase):
    def test_escaped_yaml_controls_cannot_corrupt_svg_xml(self):
        for command in ("evil\x00\x1bname", "evil\ufffename", "evil\uffffname"):
            with self.subTest(command=repr(command)):
                skill = entry(command)
                totals = skillrot.budget([skill], 4.0, 200_000)
                svg = skillrot.to_svg([skill], totals, None, 4.0)
                try:
                    ET.fromstring(svg)
                except ET.ParseError as exc:
                    self.fail("Untrusted command text produced invalid SVG: {}".format(exc))

    def test_untrusted_names_cannot_emit_terminal_escape_sequences(self):
        skill = entry("evil\x1b]52;c;dGVzdA==\x07")
        totals = skillrot.budget([skill], 4.0, 200_000)
        report = skillrot.render([skill], [], totals, None, 4.0, 10, False)
        self.assertNotIn("\x1b", report)
        self.assertNotIn("\x07", report)


class CollisionBoundaryRegressionTests(unittest.TestCase):
    def test_body_description_fallback_keeps_when_to_use(self):
        skill = entry("deploy", "")
        skill.frontmatter["when_to_use"] = "Only after review."
        skill.body = "\nDeploy after required checks.\nDetailed instructions.\n"
        self.assertEqual(skill.routing_text, "Deploy after required checks. Only after review.")

    def test_exact_duplicates_survive_the_common_word_cutoff(self):
        for size in (50, 51, 300):
            with self.subTest(size=size):
                skills = [entry("s{}".format(i), "Use when rendering charts from csv data.")
                          for i in range(size)]
                clusters = skillrot.cluster_by_description(skills)
                self.assertEqual(len(clusters), 1)
                self.assertEqual(len(clusters[0]), size)

    def test_unicode_duplicate_descriptions_are_detected(self):
        skills = [entry("a", "Використовуй для перевірки бібліотеки навичок."),
                  entry("b", "Використовуй для перевірки бібліотеки навичок.")]
        self.assertEqual(len(skillrot.cluster_by_description(skills)), 1)


if __name__ == "__main__":
    unittest.main()
