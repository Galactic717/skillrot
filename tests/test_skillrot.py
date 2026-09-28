"""Behaviour tests for skillrot. Run: python -m unittest discover -s tests"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import skillrot  # noqa: E402


def run_cli(argv):
    """Run main() with stdout captured, so the suite stays quiet."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(io.StringIO()):
        code = skillrot.main(argv)
    return code, buffer.getvalue()


def write_skill(root: Path, name: str, text: str) -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "SKILL.md"
    path.write_text(text, encoding="utf-8")
    return path


GOOD = """---
name: deploy
description: Deploys the service to staging. Use when the user asks to deploy or ship.
---

# Deploy

1. Run the tests.
2. Push the image.
"""


class FrontmatterTests(unittest.TestCase):
    def test_parses_scalars_and_body(self):
        fm, body, problems = skillrot.parse_frontmatter(GOOD)
        self.assertEqual(fm["name"], "deploy")
        self.assertIn("Use when", fm["description"])
        self.assertEqual(problems, [])
        self.assertIn("# Deploy", body)

    def test_leading_blank_line_breaks_frontmatter(self):
        fm, body, problems = skillrot.parse_frontmatter("\n" + GOOD)
        self.assertEqual(fm, {})
        self.assertIn("frontmatter-not-first-line", problems)
        self.assertIn("---", body)

    def test_missing_frontmatter(self):
        fm, _, problems = skillrot.parse_frontmatter("# Just markdown\n")
        self.assertEqual(fm, {})
        self.assertIn("no-frontmatter", problems)

    def test_unterminated_frontmatter(self):
        _, _, problems = skillrot.parse_frontmatter("---\nname: x\ndescription: y\n")
        self.assertIn("unterminated-frontmatter", problems)

    def test_folded_block_scalar(self):
        text = "---\nname: x\ndescription: >-\n  first line\n  second line\n---\nbody\n"
        fm, _, _ = skillrot.parse_frontmatter(text)
        self.assertEqual(fm["description"], "first line second line")

    def test_nested_map_captured_as_key(self):
        text = "---\nname: x\nmetadata:\n  team: infra\ndescription: Use when asked.\n---\nb\n"
        fm, _, _ = skillrot.parse_frontmatter(text)
        self.assertIn("metadata", fm)
        self.assertEqual(fm["description"], "Use when asked.")

    def test_quotes_stripped(self):
        fm, _, _ = skillrot.parse_frontmatter('---\nname: "x"\n---\n')
        self.assertEqual(fm["name"], "x")


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def rules_for(self, text, name="thing", **kwargs):
        write_skill(self.root, name, text)
        skills = skillrot.discover([self.root])
        return {f.rule for f in skillrot.analyze(skills, **kwargs)}

    def test_clean_skill_has_no_errors(self):
        write_skill(self.root, "deploy", GOOD)
        findings = skillrot.analyze(skillrot.discover([self.root]))
        self.assertEqual([f.rule for f in findings if f.severity == "error"], [])

    def test_sr001_frontmatter_not_first_line(self):
        self.assertIn("SR001", self.rules_for("\n" + GOOD))

    def test_sr002_missing_description(self):
        self.assertIn("SR002", self.rules_for("---\nname: x\n---\nbody\n"))

    def test_sr003_listing_cap(self):
        long_text = "Use when " + ("a" * 1600)
        self.assertIn("SR003", self.rules_for(
            "---\nname: x\ndescription: {}\n---\nbody\n".format(long_text)))

    def test_sr003_counts_when_to_use_toward_the_cap(self):
        half = "b" * 900
        text = "---\nname: x\ndescription: Use when {}\nwhen_to_use: {}\n---\nbody\n".format(
            half, half)
        self.assertIn("SR003", self.rules_for(text))

    def test_sr004_unreachable_skill(self):
        text = ("---\nname: x\ndescription: Use when the user asks.\n"
                "disable-model-invocation: true\nuser-invocable: false\n---\nbody\n")
        self.assertIn("SR004", self.rules_for(text))

    def test_sr004_not_raised_when_only_one_is_set(self):
        text = ("---\nname: x\ndescription: Use when the user asks.\n"
                "disable-model-invocation: true\n---\nbody\n")
        self.assertNotIn("SR004", self.rules_for(text))

    def test_boolean_synonyms_accepted(self):
        text = ("---\nname: x\ndescription: Use when the user asks.\n"
                "disable-model-invocation: yes\nuser-invocable: off\n---\nbody\n")
        rules = self.rules_for(text)
        self.assertIn("SR004", rules)      # yes/off still means unreachable
        self.assertNotIn("SR005", rules)   # ...and they are valid booleans

    def test_sr005_invalid_boolean(self):
        text = ("---\nname: x\ndescription: Use when the user asks.\n"
                "user-invocable: maybe\n---\nbody\n")
        self.assertIn("SR005", self.rules_for(text))

    def test_sr022_description_without_trigger(self):
        text = "---\nname: x\ndescription: A helper for formatting tables.\n---\nbody\n"
        self.assertIn("SR022", self.rules_for(text))

    def test_sr022_silent_when_trigger_present(self):
        self.assertNotIn("SR022", self.rules_for(GOOD))

    def test_sr023_oversized_body(self):
        body = "\n".join("line {}".format(i) for i in range(60))
        text = "---\nname: x\ndescription: Use when the user asks.\n---\n" + body
        self.assertIn("SR023", self.rules_for(text, body_line_budget=50))

    def test_sr025_thin_description(self):
        self.assertIn("SR025", self.rules_for("---\nname: x\ndescription: hi\n---\nbody\n"))

    def test_sr010_portable_rejects_extra_fields(self):
        text = ("---\nname: x\ndescription: Use when the user asks.\n"
                "argument-hint: [file]\n---\nbody\n")
        self.assertIn("SR010", self.rules_for(text, portable=True))
        self.assertNotIn("SR010", self.rules_for(text, name="other", portable=False))

    def test_sr011_compatibility_cap(self):
        text = "---\nname: x\ndescription: Use when asked.\ncompatibility: {}\n---\nb\n".format(
            "c" * 600)
        self.assertIn("SR011", self.rules_for(text, portable=True))

    def test_sr012_unknown_field(self):
        text = "---\nname: x\ndescription: Use when asked.\ndescriptoin: typo\n---\nb\n"
        self.assertIn("SR012", self.rules_for(text))

    def test_sr020_duplicate_command_names(self):
        write_skill(self.root / "a", "deploy", GOOD)
        write_skill(self.root / "b", "deploy", GOOD)
        findings = skillrot.analyze(skillrot.discover([self.root]))
        self.assertIn("SR020", {f.rule for f in findings})

    def test_sr021_near_duplicate_descriptions(self):
        one = ("---\nname: a\ndescription: Use when the user wants to render charts "
               "from csv data files.\n---\nbody\n")
        two = ("---\nname: b\ndescription: Use when the user wants to render charts "
               "from csv data files.\n---\nbody\n")
        write_skill(self.root, "alpha", one)
        write_skill(self.root, "beta", two)
        findings = skillrot.analyze(skillrot.discover([self.root]))
        self.assertIn("SR021", {f.rule for f in findings})

    def test_sr021_ignores_distinct_descriptions(self):
        one = "---\nname: a\ndescription: Use when the user wants to render charts.\n---\nb\n"
        two = "---\nname: b\ndescription: Use when the user asks to rotate ssh keys.\n---\nb\n"
        write_skill(self.root, "alpha", one)
        write_skill(self.root, "beta", two)
        findings = skillrot.analyze(skillrot.discover([self.root]))
        self.assertNotIn("SR021", {f.rule for f in findings})

    def test_sr024_never_fired(self):
        write_skill(self.root, "deploy", GOOD)
        skills = skillrot.discover([self.root])
        self.assertIn("SR024", {f.rule for f in skillrot.analyze(skills, usage={})})
        self.assertNotIn(
            "SR024", {f.rule for f in skillrot.analyze(skills, usage={"deploy": 3})})


class UsageTests(unittest.TestCase):
    def test_counts_skill_invocations_in_transcripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "proj").mkdir()
            line = ('{"type":"tool_use","id":"toolu_1","name":"Skill",'
                    '"input":{"skill":"anthropic-skills:docx"}}')
            other = '{"type":"text","text":"no tool here"}'
            (root / "proj" / "session.jsonl").write_text(
                "\n".join([line, other, line]), encoding="utf-8")
            counts = skillrot.usage_counts(root)
            self.assertEqual(counts["anthropic-skills:docx"], 2)

    def test_missing_transcript_dir_is_not_an_error(self):
        self.assertEqual(skillrot.usage_counts(Path("/nope/does/not/exist")), {})

    def test_resolve_usage_falls_back_to_bare_name(self):
        skill = skillrot.Skill(
            path=Path("x/SKILL.md"), root=Path("x"), origin="plugin",
            command="myplugin:docx", frontmatter={}, body="")
        self.assertEqual(skillrot.resolve_usage(skill, {"docx": 5}), 5)
        self.assertEqual(skillrot.resolve_usage(skill, {"myplugin:docx": 2, "docx": 5}), 2)


class BudgetTests(unittest.TestCase):
    def test_listing_cost_is_capped_at_the_spec_limit(self):
        skill = skillrot.Skill(
            path=Path("x/SKILL.md"), root=Path("x"), origin="scanned", command="x",
            frontmatter={"name": "x", "description": "d" * 5000}, body="")
        capped = skillrot.listing_tokens(skill, 4.0)
        self.assertLessEqual(capped, skillrot.LISTING_CHAR_CAP / 4 + 1)

    def test_totals_add_up(self):
        skills = [
            skillrot.Skill(path=Path("a/SKILL.md"), root=Path("a"), origin="scanned",
                           command="a", frontmatter={"description": "abcd" * 10},
                           body="x" * 400),
            skillrot.Skill(path=Path("b/SKILL.md"), root=Path("b"), origin="scanned",
                           command="b", frontmatter={"description": "abcd" * 10},
                           body="y" * 800),
        ]
        totals = skillrot.budget(skills, 4.0, 200_000)
        self.assertEqual(totals.skills, 2)
        self.assertEqual(totals.body_tokens, 300)
        self.assertGreater(totals.always_on_tokens, 0)
        self.assertAlmostEqual(
            totals.context_percent, 100 * totals.always_on_tokens / 200_000, places=6)

    def test_zero_context_window_does_not_divide_by_zero(self):
        totals = skillrot.budget([], 4.0, 0)
        self.assertEqual(totals.context_percent, 0.0)


class DiscoveryTests(unittest.TestCase):
    def test_plugin_command_is_namespaced_from_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugins" / "cache" / "market" / "myplug" / "1.2.3"
            (root / ".claude-plugin").mkdir(parents=True)
            (root / ".claude-plugin" / "plugin.json").write_text(
                json.dumps({"name": "myplug"}), encoding="utf-8")
            # No `name` field, so the command leaf comes from the directory.
            write_skill(root / "skills", "review",
                        "---\ndescription: Use when the user asks to review.\n---\nbody\n")
            skills = skillrot.discover([Path(tmp)])
            self.assertEqual(skills[0].command, "myplug:review")
            self.assertEqual(skills[0].origin, "plugin")

    def test_plugin_name_falls_back_past_a_version_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugins" / "figma" / "2.2.81"
            write_skill(root / "skills", "code-connect", GOOD)
            skills = skillrot.discover([Path(tmp)])
            self.assertEqual(skills[0].plugin, "figma")

    def test_frontmatter_name_sets_the_plugin_command_leaf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "plugins" / "myplug"
            text = GOOD.replace("name: deploy", "name: fancy")
            write_skill(root / "skills", "review", text)
            skills = skillrot.discover([Path(tmp)])
            self.assertEqual(skills[0].command, "myplug:fancy")

    def test_same_skill_is_not_counted_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_skill(root, "deploy", GOOD)
            self.assertEqual(len(skillrot.discover([root, root, path])), 1)

    def test_a_direct_file_path_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_skill(Path(tmp), "deploy", GOOD)
            self.assertEqual(len(skillrot.discover([path])), 1)

    def test_relative_path_still_yields_a_command_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "myskill"
            root.mkdir()
            (root / "SKILL.md").write_text(GOOD.replace("name: deploy\n", ""), encoding="utf-8")
            previous = Path.cwd()
            os.chdir(root)
            try:
                skills = skillrot.discover([Path(".")])
            finally:
                os.chdir(previous)
            self.assertEqual(skills[0].command, "myskill")


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        write_skill(self.root, "deploy", GOOD)

    def tearDown(self):
        self.tmp.cleanup()

    def test_json_output_is_valid(self):
        skills = skillrot.discover([self.root])
        payload = json.loads(skillrot.to_json(
            skills, skillrot.analyze(skills), skillrot.budget(skills, 4.0, 200_000), {}, 4.0))
        self.assertEqual(payload["budget"]["skills"], 1)
        self.assertEqual(payload["skills"][0]["command"], "deploy")

    def test_exit_zero_on_clean_library(self):
        code, out = run_cli([str(self.root), "--no-usage", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["budget"]["skills"], 1)

    def test_fail_on_error_exits_nonzero(self):
        write_skill(self.root, "broken", "\n" + GOOD)
        self.assertEqual(
            run_cli([str(self.root), "--no-usage", "--json", "--fail-on", "error"])[0], 1)

    def test_missing_path_exits_two(self):
        self.assertEqual(run_cli([str(self.root / "nope"), "--no-usage"])[0], 2)

    def test_render_is_plain_text_without_color(self):
        skills = skillrot.discover([self.root])
        text = skillrot.render(
            skills, skillrot.analyze(skills), skillrot.budget(skills, 4.0, 200_000),
            {}, 4.0, 10, False)
        self.assertNotIn("\033[", text)
        self.assertIn("Context bill", text)


class ClusterTests(unittest.TestCase):
    def make(self, command, description):
        return skillrot.Skill(
            path=Path(command) / "SKILL.md", root=Path(command), origin="scanned",
            command=command, frontmatter={"description": description}, body="")

    def test_identical_descriptions_form_one_cluster(self):
        text = "Use when the user wants to render charts from csv data files."
        skills = [self.make(n, text) for n in ("a", "b", "c")]
        clusters = skillrot.cluster_by_description(skills, 0.8)
        self.assertEqual(len(clusters), 1)
        self.assertEqual([s.command for s in clusters[0]], ["a", "b", "c"])

    def test_distinct_descriptions_do_not_cluster(self):
        skills = [
            self.make("a", "Use when the user wants to render charts from csv."),
            self.make("b", "Use when the user asks to rotate production ssh keys."),
        ]
        self.assertEqual(skillrot.cluster_by_description(skills, 0.8), [])

    def test_separate_duplicate_pairs_stay_separate(self):
        skills = [
            self.make("a", "Use when rendering charts from csv data files."),
            self.make("b", "Use when rendering charts from csv data files."),
            self.make("c", "Use when rotating production ssh keys on servers."),
            self.make("d", "Use when rotating production ssh keys on servers."),
        ]
        clusters = skillrot.cluster_by_description(skills, 0.8)
        self.assertEqual(sorted(len(c) for c in clusters), [2, 2])

    def test_single_skill_library_has_no_clusters(self):
        self.assertEqual(skillrot.cluster_by_description([self.make("a", "x y z")], 0.8), [])

    def test_one_finding_per_cluster_not_per_pair(self):
        text = "Use when the user wants to render charts from csv data files."
        skills = [self.make(n, text) for n in "abcde"]
        findings = [f for f in skillrot.analyze(skills) if f.rule == "SR021"]
        self.assertEqual(len(findings), 1)
        self.assertIn("5 skills", findings[0].message)


class SymlinkStubTests(unittest.TestCase):
    def test_detects_a_path_only_file(self):
        self.assertTrue(skillrot._looks_like_symlink_stub("../../shared/skills/x/SKILL.md"))

    def test_ignores_real_markdown(self):
        self.assertFalse(skillrot._looks_like_symlink_stub("# Title\n\nSome prose."))
        self.assertFalse(skillrot._looks_like_symlink_stub(""))

    def test_reported_as_sr008_not_sr001(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "linked", "../../other/skills/linked/SKILL.md\n")
            rules = {f.rule for f in skillrot.analyze(skillrot.discover([Path(tmp)]))}
            self.assertIn("SR008", rules)
            self.assertNotIn("SR001", rules)


class RenderLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for i in range(25):
            write_skill(self.root, "skill{}".format(i),
                        "---\nname: s{}\ndescription: A tool for tables.\n---\nbody\n".format(i))

    def tearDown(self):
        self.tmp.cleanup()

    def test_findings_are_capped_per_rule(self):
        skills = skillrot.discover([self.root])
        findings = skillrot.analyze(skills)
        totals = skillrot.budget(skills, 4.0, 200_000)
        capped = skillrot.render(skills, findings, totals, None, 4.0, 5, False, 5)
        self.assertIn("and 20 more", capped)
        full = skillrot.render(skills, findings, totals, None, 4.0, 5, False, 0)
        self.assertNotIn("and 20 more", full)
        self.assertEqual(full.count("SR022"), 25)


class FoldedScalarTests(unittest.TestCase):
    def test_plain_scalar_folds_indented_continuations(self):
        text = ("---\nname: x\ndescription: First line\n"
                "  and its folded continuation about when to use it.\n---\nbody\n")
        fm, _, problems = skillrot.parse_frontmatter(text)
        self.assertEqual(problems, [])
        self.assertEqual(
            fm["description"],
            "First line and its folded continuation about when to use it.")

    def test_folded_description_is_seen_by_the_trigger_rule(self):
        # The trigger cue lives on the continuation line; before folding it was
        # truncated away and SR022 fired falsely.
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "x",
                        "---\nname: x\ndescription: A table formatter\n"
                        "  that you use when the user asks to format a table.\n---\nb\n")
            rules = {f.rule for f in skillrot.analyze(skillrot.discover([Path(tmp)]))}
            self.assertNotIn("SR022", rules)


class TriggerSourceTests(unittest.TestCase):
    def test_sr022_silent_when_trigger_is_in_when_to_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "x",
                        "---\nname: x\ndescription: A helper for formatting tables.\n"
                        "when_to_use: Use when the user asks to format a table.\n---\nb\n")
            rules = {f.rule for f in skillrot.analyze(skillrot.discover([Path(tmp)]))}
            self.assertNotIn("SR022", rules)


class ListingBudgetTests(unittest.TestCase):
    def make(self, command, description):
        return skillrot.Skill(
            path=Path(command) / "SKILL.md", root=Path(command), origin="scanned",
            command=command, frontmatter={"name": command, "description": description}, body="")

    def test_names_are_always_counted_even_over_budget(self):
        skills = [self.make("s{}".format(i), "Use when the user asks about topic {}.".format(i))
                  for i in range(50)]
        # A budget too small for any description: always-on is at least the names.
        totals = skillrot.budget(skills, 4.0, 10_000, budget_fraction=0.001)  # 10-tok budget
        self.assertTrue(totals.overflows)
        self.assertGreaterEqual(totals.always_on_tokens, totals.name_tokens)
        self.assertEqual(totals.name_tokens, sum(skillrot._name_tokens(s, 4.0) for s in skills))

    def test_name_only_skills_reported_as_sr030(self):
        skills = [self.make("s{}".format(i), "Use when the user asks about topic {}.".format(i))
                  for i in range(30)]
        findings = skillrot.analyze(skills, usage={}, listing_budget=20, chars_per_token=4.0)
        sr030 = [f for f in findings if f.rule == "SR030"]
        self.assertTrue(sr030)  # a 20-token budget can't hold 30 descriptions

    def test_no_sr030_when_everything_fits(self):
        skills = [self.make("a", "Use when the user asks about alpha.")]
        findings = skillrot.analyze(skills, usage={}, listing_budget=2000, chars_per_token=4.0)
        self.assertNotIn("SR030", {f.rule for f in findings})

    def test_most_used_descriptions_survive_the_budget(self):
        skills = [self.make("keep", "Use when the user asks about the kept topic here."),
                  self.make("drop", "Use when the user asks about the dropped topic here.")]
        budget_tok = (skillrot._name_tokens(skills[0], 4.0) * 2
                      + skillrot._desc_tokens(skills[0], 4.0))  # room for one description
        dropped = skillrot.name_only_skills(skills, {"keep": 9}, budget_tok, 4.0)
        self.assertEqual([s.command for s in dropped], ["drop"])


class BundleBytesTests(unittest.TestCase):
    def test_nested_skill_is_not_counted_in_parent_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "parent"
            (root).mkdir()
            (root / "SKILL.md").write_text(GOOD, encoding="utf-8")
            (root / "big.txt").write_text("x" * 1000, encoding="utf-8")
            nested = root / "child"
            nested.mkdir()
            (nested / "SKILL.md").write_text(GOOD, encoding="utf-8")
            (nested / "huge.txt").write_text("y" * 100000, encoding="utf-8")
            total = skillrot._bundle_bytes(root)
            self.assertLess(total, 5000)  # the 100k nested file is excluded


class CommandNameTests(unittest.TestCase):
    def test_frontmatter_name_beats_directory_for_local_skills(self):
        # Docs: .claude/skills/deploy-staging/SKILL.md with name: deploy -> /deploy
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "deploy-staging", GOOD)
            self.assertEqual(skillrot.discover([Path(tmp)])[0].command, "deploy")

    def test_same_name_in_two_dirs_is_a_command_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "deploy-staging", GOOD)
            write_skill(Path(tmp), "deploy-prod", GOOD)
            rules = {f.rule for f in skillrot.analyze(skillrot.discover([Path(tmp)]))}
            self.assertIn("SR020", rules)


class ShallowDiscoveryTests(unittest.TestCase):
    def test_shallow_root_scans_one_level_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_skill(root, "top", GOOD)                       # root/top/SKILL.md
            write_skill(root / "repo" / "deep", "buried", GOOD)  # root/repo/deep/SKILL.md
            shallow = skillrot.discover([root], shallow_roots=[root])
            self.assertEqual([s.path.parent.name for s in shallow], ["top"])
            deep = skillrot.discover([root])
            self.assertEqual(sorted(s.path.parent.name for s in deep), ["buried", "top"])


class ManifestDiscoveryTests(unittest.TestCase):
    def make_marketplace(self, root: Path):
        (root / ".claude-plugin").mkdir(parents=True)
        (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
            {"name": "m", "plugins": [{"name": "p", "source": "./p"},
                                      {"name": "remote", "source": {"source": "github"}}]}),
            encoding="utf-8")
        plugin = root / "p"
        (plugin / ".claude-plugin").mkdir(parents=True)
        (plugin / ".claude-plugin" / "plugin.json").write_text(
            json.dumps({"name": "p", "skills": ["./extra"]}), encoding="utf-8")
        write_skill(plugin / "skills", "real", GOOD)
        write_skill(plugin / "extra", "added", GOOD)
        # Mirrors a real repo carries that Claude Code never installs.
        write_skill(root / "docs" / "ja-JP" / "skills", "real", GOOD)
        write_skill(root / ".gemini" / "skills", "real", GOOD)

    def test_marketplace_counts_only_what_the_manifest_installs(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.make_marketplace(Path(tmp))
            skills = skillrot.discover([Path(tmp)])
            self.assertEqual(sorted(s.command for s in skills), ["p:deploy", "p:deploy"])
            self.assertTrue(all(s.origin == "plugin" for s in skills))

    def test_scan_all_still_counts_every_skill_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.make_marketplace(Path(tmp))
            self.assertEqual(len(skillrot.discover([Path(tmp)], scan_all=True)), 4)

    def test_root_plugin_counts_when_marketplace_source_is_remote(self):
        # addyosmani/agent-skills: marketplace points at github, root has plugin.json.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
                {"plugins": [{"name": "a", "source": {"source": "github", "repo": "x/a"}}]}),
                encoding="utf-8")
            (root / ".claude-plugin" / "plugin.json").write_text(
                json.dumps({"name": "a", "skills": "./skills"}), encoding="utf-8")
            write_skill(root / "skills", "one", GOOD.replace("name: deploy\n", ""))
            write_skill(root / ".gemini" / "skills", "one", GOOD)
            self.assertEqual([s.command for s in skillrot.discover([root])], ["a:one"])

    def test_remote_only_marketplace_falls_back_to_recursive_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
                {"plugins": [{"name": "a", "source": {"source": "github"}}]}), encoding="utf-8")
            write_skill(root / "catalog", "one", GOOD)
            self.assertEqual(len(skillrot.discover([root])), 1)

    def test_plugin_root_skill_md_loads_as_single_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin" / "plugin.json").write_text('{"name": "solo"}', encoding="utf-8")
            (root / "SKILL.md").write_text(GOOD, encoding="utf-8")
            self.assertEqual(len(skillrot.discover([root])), 1)


class SvgTests(unittest.TestCase):
    def test_svg_is_well_formed_xml(self):
        import xml.dom.minidom as minidom
        with tempfile.TemporaryDirectory() as tmp:
            write_skill(Path(tmp), "deploy", GOOD)
            skills = skillrot.discover([Path(tmp)])
            svg = skillrot.to_svg(skills, skillrot.budget(skills, 4.0, 200_000), {}, 4.0)
            doc = minidom.parseString(svg)      # raises on malformed XML
            self.assertEqual(doc.documentElement.tagName, "svg")


if __name__ == "__main__":
    unittest.main()
