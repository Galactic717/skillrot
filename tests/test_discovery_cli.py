"""Discovery boundaries and operational failures, using real temporary files."""

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import skillrot


def write_skill(folder, name="deploy"):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "SKILL.md"
    path.write_text(
        "---\nname: " + name + "\ndescription: Use when the user asks to deploy.\n---\nBody\n",
        encoding="utf-8",
    )
    return path


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def run_cli(args, home=None, cwd=None, stdout=None):
    out, err = stdout if stdout is not None else io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as stack:
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(err))
        stack.enter_context(patch.dict(os.environ, {"SLASH_COMMAND_TOOL_CHAR_BUDGET": ""}))
        if home is not None:
            stack.enter_context(patch.object(skillrot.Path, "home", return_value=home))
        if cwd is not None:
            stack.enter_context(patch.object(skillrot.Path, "cwd", return_value=cwd))
        try:
            code = skillrot.main(args)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class DiscoveryBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def plugin(self, manifest):
        root = self.root / "plugin"
        write_json(root / ".claude-plugin" / "plugin.json", manifest)
        return root

    def test_plain_skills_folder_does_not_invent_plugin_namespace(self):
        write_skill(self.root / "skills" / "deploy")
        skills = skillrot.discover([self.root / "skills"])
        self.assertEqual([(s.command, s.plugin) for s in skills], [("deploy", None)])

    def test_other_harness_paths_do_not_invent_plugin_namespace(self):
        for harness in (".codex", ".cursor"):
            with self.subTest(harness=harness):
                root = self.root / harness / "skills"
                write_skill(root / "deploy")
                self.assertEqual(skillrot.discover([root])[0].command, "deploy")

    def test_generic_plugins_directory_is_not_plugin_ownership_evidence(self):
        write_skill(self.root / "plugins" / "ordinary" / "skills" / "deploy")
        self.assertEqual(skillrot.discover([self.root])[0].command, "deploy")

    def test_default_roots_only_include_the_modeled_claude_profile(self):
        home, cwd = self.root / "home", self.root / "project"
        for folder in (home / ".claude" / "skills", home / ".codex" / "skills",
                       home / ".cursor" / "skills", home / ".config" / "agent-skills"):
            folder.mkdir(parents=True)
        cwd.mkdir()
        with patch.object(skillrot.Path, "home", return_value=home):
            self.assertEqual(skillrot.default_roots(cwd), [home / ".claude" / "skills"])

    def test_scan_all_overrides_shallow_installed_discovery(self):
        write_skill(self.root / "top", "top")
        write_skill(self.root / "top" / "nested", "nested")
        skills = skillrot.discover([self.root], shallow_roots=[self.root], scan_all=True)
        self.assertEqual(sorted(s.command for s in skills), ["nested", "top"])

    def test_empty_plugin_manifest_does_not_count_documentation_mirrors(self):
        root = self.plugin({"name": "empty", "skills": [], "commands": []})
        write_skill(root / "docs" / "skills" / "mirror", "mirror")
        self.assertEqual(skillrot.discover([root]), [])

    def test_explicit_empty_skills_does_not_enable_root_skill_fallback(self):
        root = self.plugin({"name": "p", "skills": []})
        write_skill(root, "root-skill")
        self.assertEqual(skillrot.discover([root]), [])

    def test_existing_empty_skills_directory_disables_root_skill_fallback(self):
        root = self.plugin({"name": "p"})
        (root / "skills").mkdir()
        write_skill(root, "root-skill")
        self.assertEqual(skillrot.discover([root]), [])

    def test_plugin_json_requires_a_name(self):
        root = self.plugin({})
        write_skill(root, "root-skill")
        code, out, err = run_cli([str(root), "--no-usage", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("name", err)
        self.assertEqual(out, "")

    def test_missing_explicit_manifest_components_are_operational_errors(self):
        for key in ("skills", "commands"):
            with self.subTest(key=key):
                root = self.plugin({"name": "p", key: "./missing"})
                write_skill(root, "root-skill")
                code, out, err = run_cli([str(root), "--no-usage", "--json"])
                self.assertEqual(code, 2)
                self.assertIn("missing", err)
                self.assertEqual(out, "")

    def test_missing_local_marketplace_source_is_an_operational_error(self):
        write_json(self.root / ".claude-plugin" / "marketplace.json",
                   {"plugins": [{"name": "p", "source": "./missing"}]})
        code, out, err = run_cli([str(self.root), "--no-usage", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("source", err)
        self.assertIn("missing", err)
        self.assertEqual(out, "")

    def test_remote_only_marketplace_does_not_count_documentation_mirrors(self):
        write_json(self.root / ".claude-plugin" / "marketplace.json",
                   {"plugins": [{"name": "remote", "source": {"source": "github"}}]})
        write_skill(self.root / "catalog" / "mirror", "mirror")
        self.assertEqual(skillrot.discover([self.root]), [])

    def test_required_marketplace_fields_cannot_be_silently_omitted(self):
        good = write_skill(self.root / "valid-input", "valid")
        write_skill(self.root / "market" / "one", "one")
        for catalog, field in (({}, "plugins"),
                               ({"plugins": [{"name": "p"}]}, "source"),
                               ({"plugins": [{"source": "./one"}]}, "name")):
            with self.subTest(catalog=catalog):
                root = self.root / "market"
                write_json(root / ".claude-plugin" / "marketplace.json", catalog)
                code, out, err = run_cli([str(good), str(root), "--no-usage", "--json"])
                self.assertEqual(code, 2)
                self.assertIn("marketplace.json", err)
                self.assertIn(field, err)
                self.assertEqual(out, "")

    def test_explicit_empty_marketplace_is_accepted_alongside_other_inputs(self):
        good = write_skill(self.root / "valid-input", "valid")
        root = self.root / "market"
        write_json(root / ".claude-plugin" / "marketplace.json", {"plugins": []})
        code, out, _ = run_cli([str(good), str(root), "--no-usage", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual([s["command"] for s in json.loads(out)["skills"]], ["valid"])

    def test_marketplace_component_extensions_with_plugin_json_are_diagnosed(self):
        root = self.root / "market"
        plugin = root / "plugin"
        write_json(plugin / ".claude-plugin" / "plugin.json", {"name": "p"})
        write_skill(plugin / "skills" / "default", "default")
        write_skill(plugin / "extra-skills" / "extra", "extra")
        command = plugin / "extra-commands" / "extra.md"
        command.parent.mkdir(parents=True)
        command.write_text("Do the extra work.\n", encoding="utf-8")
        for key, component in (("skills", "./extra-skills"), ("commands", "./extra-commands")):
            for strict in (None, True, False):
                with self.subTest(key=key, strict=strict):
                    entry = {"name": "p", "source": "./plugin", key: [component]}
                    if strict is not None:
                        entry["strict"] = strict
                    write_json(root / ".claude-plugin" / "marketplace.json", {"plugins": [entry]})
                    code, out, err = run_cli([str(root), "--no-usage", "--json"])
                    self.assertEqual(code, 2)
                    self.assertIn("plugin.json", err)
                    self.assertIn(key, err)
                    self.assertIn("conflict" if strict is False else "unsupported", err.lower())
                    self.assertEqual(out, "")

    def test_marketplace_strict_flag_must_be_boolean(self):
        root = self.root / "market"
        write_skill(root / "plugin", "p")
        write_json(root / ".claude-plugin" / "marketplace.json", {"plugins": [
            {"name": "p", "source": "./plugin", "strict": "false"}
        ]})
        code, out, err = run_cli([str(root), "--no-usage", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("strict", err)
        self.assertEqual(out, "")

    def test_empty_remote_source_identifier_is_diagnosed(self):
        good = write_skill(self.root / "valid-input", "valid")
        root = self.root / "market"
        write_json(root / ".claude-plugin" / "marketplace.json", {"plugins": [
            {"name": "p", "source": {"source": ""}}
        ]})
        code, out, err = run_cli([str(good), str(root), "--no-usage", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("source type", err)
        self.assertEqual(out, "")

    def test_strict_false_conflict_in_non_listing_component_is_diagnosed(self):
        root = self.root / "market"
        plugin = root / "plugin"
        write_json(plugin / ".claude-plugin" / "plugin.json", {"name": "p"})
        write_skill(plugin / "skills" / "default", "default")
        write_json(root / ".claude-plugin" / "marketplace.json", {"plugins": [
            {"name": "p", "source": "./plugin", "strict": False, "hooks": "./hooks.json"}
        ]})
        code, out, err = run_cli([str(root), "--no-usage", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("conflict", err)
        self.assertIn("hooks", err)
        self.assertEqual(out, "")

    def test_nested_plugin_commands_keep_path_qualified_names(self):
        root = self.plugin({"name": "p"})
        command = root / "commands" / "frontend" / "component.md"
        command.parent.mkdir(parents=True)
        command.write_text("Build a component.\n", encoding="utf-8")
        skills = skillrot.discover([root])
        self.assertEqual([(s.command, s.kind) for s in skills],
                         [("p:frontend:component", "command")])

    def test_manifest_skill_paths_cannot_escape_checkout(self):
        write_skill(self.root / "private" / "secret", "private")
        for source in ("../private", str(self.root / "private"), r"\\server\share\private"):
            with self.subTest(source=source):
                root = self.plugin({"name": "p", "skills": source})
                code, out, err = run_cli([str(root), "--no-usage", "--json"])
                self.assertEqual(code, 2)
                self.assertIn("skills", err)
                self.assertEqual(out, "")

    def test_marketplace_source_cannot_escape_checkout(self):
        write_skill(self.root / "private", "private")
        root = self.root / "checkout"
        write_json(root / ".claude-plugin" / "marketplace.json",
                   {"plugins": [{"name": "p", "source": "../private"}]})
        code, out, err = run_cli([str(root), "--no-usage", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("source", err)
        self.assertEqual(out, "")

    def test_manifest_command_path_cannot_escape_checkout(self):
        private = self.root / "private.md"
        private.write_text("Private material.\n", encoding="utf-8")
        root = self.plugin({"name": "p", "commands": "../private.md"})
        code, out, err = run_cli([str(root), "--no-usage", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("commands", err)
        self.assertEqual(out, "")

    def test_manifest_symlink_path_cannot_escape_checkout(self):
        write_skill(self.root / "private" / "secret", "private")
        root = self.plugin({"name": "p", "skills": "./linked"})
        try:
            (root / "linked").symlink_to(self.root / "private", target_is_directory=True)
        except (OSError, NotImplementedError):
            if os.name != "nt":
                self.skipTest("Directory symlinks are unavailable on this host")
            # Junctions exercise the same resolved containment boundary on
            # Windows without requiring the symlink creation privilege.
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(root / "linked"), str(self.root / "private")],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            if result.returncode:
                self.skipTest("Neither directory symlinks nor junctions are available")
        code, out, err = run_cli([str(root), "--no-usage", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("skills", err)
        self.assertEqual(out, "")

    def test_malformed_manifest_shapes_are_operational_errors(self):
        for manifest in ({"name": "p", "skills": 3}, {"name": "p", "skills": [3]},
                         {"name": "p", "commands": {}}, {"name": ["p"]}):
            with self.subTest(manifest=manifest):
                root = self.plugin(manifest)
                write_skill(root / "skills" / "deploy")
                code, out, err = run_cli([str(root), "--no-usage", "--json"])
                self.assertEqual(code, 2)
                self.assertIn("plugin.json", err)
                self.assertEqual(out, "")

    def test_invalid_manifest_json_is_not_a_recursive_scan(self):
        root = self.plugin({"name": "p"})
        (root / ".claude-plugin" / "plugin.json").write_text("{bad-json", encoding="utf-8")
        write_skill(root / "skills" / "deploy")
        code, out, err = run_cli([str(root), "--no-usage", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("plugin.json", err)
        self.assertEqual(out, "")

    def test_direct_skill_audit_diagnoses_its_malformed_owning_manifest(self):
        root = self.plugin({"name": "p"})
        path = write_skill(root / "skills" / "deploy")
        (root / ".claude-plugin" / "plugin.json").write_text("{bad-json", encoding="utf-8")
        code, out, err = run_cli([str(path), "--no-usage", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("plugin.json", err)
        self.assertEqual(out, "")

    def test_manifest_json_parser_recursion_is_an_operational_error(self):
        root = self.plugin({"name": "p"})
        write_skill(root / "skills" / "deploy")
        manifest_text = (root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
        actual_loads = json.loads

        def loads(text, *args, **kwargs):
            # Decoder recursion limits vary by Python version. Force only this
            # parser boundary; file reads, discovery and CLI handling stay real.
            if text == manifest_text:
                raise RecursionError("JSON decoder recursion exceeded")
            return actual_loads(text, *args, **kwargs)

        with patch.object(skillrot.json, "loads", side_effect=loads):
            code, out, err = run_cli([str(root), "--no-usage", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("plugin.json", err)
        self.assertIn("could not read JSON", err)
        self.assertIn("JSON decoder recursion exceeded", err)
        self.assertEqual(out, "")
        self.assertNotIn("Traceback", err)


class OperationalCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = write_skill(self.root / "deploy")
        self.home, self.cwd = self.root / "home", self.root / "project"
        self.home.mkdir()
        self.cwd.mkdir()
        write_skill(self.cwd / ".claude" / "skills" / "deploy")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_missing_input_among_valid_inputs_is_an_operational_failure(self):
        code, _, err = run_cli([str(self.path), str(self.root / "missing"), "--no-usage", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("missing", err)

    def test_svg_write_failure_is_an_operational_failure(self):
        code, _, err = run_cli([str(self.path), "--no-usage", "--json", "--svg",
                               str(self.root / "missing" / "budget.svg")])
        self.assertEqual(code, 2)
        self.assertIn("could not write", err)

    def test_invalid_numeric_options_are_rejected_before_audit(self):
        cases = {"--chars-per-token": ["0", "-1", "nan", "inf", "1e-320"],
                 "--context-window": ["0", "-1"], "--top": ["-1"],
                 "--body-lines": ["-1"], "--similarity": ["nan", "inf", "-0.1", "1.1"],
                 "--budget-fraction": ["nan", "inf", "0", "-0.1", "1.1"]}
        for flag, values in cases.items():
            for value in values:
                with self.subTest(flag=flag, value=value):
                    code, out, err = run_cli([str(self.path), "--no-usage", "--json", flag, value])
                    self.assertEqual(code, 2)
                    self.assertIn(flag, err)
                    self.assertEqual(out, "")

    def test_malformed_nested_settings_are_operational_failures(self):
        for value in ({"skillOverrides": []}, {"skillOverrides": {"deploy": 3}},
                      {"env": ["x"]}, {"enabledPlugins": []},
                      {"enabledPlugins": {"p@m": "true"}},
                      {"skillListingBudgetFraction": -0.1},
                      {"skillListingMaxDescChars": 1000}):
            with self.subTest(value=value):
                write_json(self.home / ".claude" / "settings.json", value)
                code, out, err = run_cli(["--no-usage", "--json"], home=self.home, cwd=self.cwd)
                self.assertEqual(code, 2)
                self.assertIn("settings.json", err)
                self.assertEqual(out, "")

    def test_malformed_plugin_registry_is_an_operational_failure(self):
        write_json(self.home / ".claude" / "settings.json", {"enabledPlugins": {"p@m": True}})
        for value in ({"plugins": []}, {"plugins": {"p@m": ["invalid"]}}):
            with self.subTest(value=value):
                write_json(self.home / ".claude" / "plugins" / "installed_plugins.json", value)
                code, out, err = run_cli(["--no-usage", "--json"], home=self.home, cwd=self.cwd)
                self.assertEqual(code, 2)
                self.assertIn("installed_plugins.json", err)
                self.assertEqual(out, "")

    def test_distinct_scoped_plugin_roots_are_an_explicit_profile_limitation(self):
        first, second = self.root / "first-install", self.root / "second-install"
        write_skill(first / "skills" / "one", "one")
        write_skill(second / "skills" / "two", "two")
        write_json(self.home / ".claude" / "settings.json", {"enabledPlugins": {"p@m": True}})
        write_json(self.home / ".claude" / "plugins" / "installed_plugins.json", {"plugins": {"p@m": [
            {"scope": "project", "projectPath": str(self.cwd), "installPath": str(first)},
            {"scope": "user", "installPath": str(second)},
        ]}})
        code, out, err = run_cli(["--no-usage", "--json"], home=self.home, cwd=self.cwd)
        self.assertEqual(code, 2)
        self.assertIn("p@m", err)
        self.assertIn("explicit", err.lower())
        self.assertEqual(out, "")

    def test_repeated_registry_records_for_one_physical_root_are_accepted(self):
        plugin = self.root / "one-install"
        write_skill(plugin / "skills" / "one", "one")
        write_json(self.home / ".claude" / "settings.json", {"enabledPlugins": {"p@m": True}})
        write_json(self.home / ".claude" / "plugins" / "installed_plugins.json", {"plugins": {"p@m": [
            {"scope": "project", "projectPath": str(self.cwd), "installPath": str(plugin)},
            {"scope": "user", "installPath": str(plugin / "skills" / "..")},
        ]}})
        code, out, _ = run_cli(["--no-usage", "--json"], home=self.home, cwd=self.cwd)
        self.assertEqual(code, 0)
        self.assertEqual([s["command"] for s in json.loads(out)["skills"]], ["deploy", "p:one"])

    def test_malformed_marketplace_registry_is_an_operational_failure(self):
        write_json(self.home / ".claude" / "settings.json", {"enabledPlugins": {"p@m": True}})
        write_json(self.home / ".claude" / "plugins" / "known_marketplaces.json",
                   {"m": {"source": "github"}})
        code, out, err = run_cli(["--no-usage", "--json"], home=self.home, cwd=self.cwd)
        self.assertEqual(code, 2)
        self.assertIn("known_marketplaces.json", err)
        self.assertEqual(out, "")

    def test_unresolved_enabled_plugin_does_not_report_a_clean_inventory(self):
        write_json(self.home / ".claude" / "settings.json", {"enabledPlugins": {"p@m": True}})
        code, out, err = run_cli(["--no-usage", "--json"], home=self.home, cwd=self.cwd)
        self.assertEqual(code, 2)
        self.assertIn("p@m", err)
        self.assertEqual(out, "")

    def test_absent_enabled_plugins_does_not_inventory_disabled_cache(self):
        plugin = self.home / ".claude" / "plugins" / "cache" / "m" / "p" / "1.0.0"
        write_skill(plugin / "skills" / "one", "one")
        code, out, _ = run_cli(["--no-usage", "--json"], home=self.home, cwd=self.cwd)
        self.assertEqual(code, 0)
        self.assertEqual([s["command"] for s in json.loads(out)["skills"]], ["deploy"])

    def test_plugin_overrides_do_not_change_plugin_listing(self):
        plugin = self.home / ".claude" / "plugins" / "cache" / "m" / "p" / "1.0.0"
        write_skill(plugin / "skills" / "one", "one")
        write_json(self.home / ".claude" / "plugins" / "installed_plugins.json",
                   {"plugins": {"p@m": [{"installPath": str(plugin)}]}})
        write_json(self.home / ".claude" / "settings.json",
                   {"enabledPlugins": {"p@m": True}, "skillOverrides": {"p:one": "off"}})
        code, out, _ = run_cli(["--no-usage", "--json"], home=self.home, cwd=self.cwd)
        self.assertEqual(code, 0)
        item = next(s for s in json.loads(out)["skills"] if s["command"] == "p:one")
        self.assertTrue(item["in_listing"])
        self.assertIsNone(item["override"])

    def test_no_transcript_evidence_does_not_claim_never_invoked(self):
        transcripts = self.root / "empty-transcripts"
        transcripts.mkdir()
        code, out, _ = run_cli([str(self.path), "--json", "--transcripts", str(transcripts)])
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertNotIn("SR024", [f["rule"] for f in payload["findings"]])
        self.assertIsNone(payload["skills"][0]["invocations"])

    def test_text_output_falls_back_safely_on_ascii_streams(self):
        class AsciiStream(io.StringIO):
            encoding = "ascii"

            def write(self, text):
                text.encode("ascii")
                return super().write(text)

        path = write_skill(self.root / "unicode", "caf\u00e9")
        code, out, _ = run_cli([str(path), "--no-usage"], stdout=AsciiStream())
        self.assertEqual(code, 0)
        self.assertIn("caf", out)

    def test_closed_output_pipe_does_not_print_a_traceback(self):
        script = Path(skillrot.__file__).resolve()
        env = dict(os.environ)
        env.pop("SLASH_COMMAND_TOOL_CHAR_BUDGET", None)
        process = subprocess.Popen([sys.executable, str(script), str(self.path), "--no-usage"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        process.stdout.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace")
        process.stderr.close()
        self.assertEqual(process.wait(timeout=10), 0, stderr)
        self.assertNotIn("Traceback", stderr)

    def test_help_and_version_handle_closed_output_pipes(self):
        script = Path(skillrot.__file__).resolve()
        for flag in ("--help", "--version"):
            with self.subTest(flag=flag):
                process = subprocess.Popen([sys.executable, str(script), flag],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                process.stdout.close()
                stderr = process.stderr.read().decode("utf-8", errors="replace")
                process.stderr.close()
                self.assertEqual(process.wait(timeout=10), 0, stderr)


if __name__ == "__main__":
    unittest.main()
