"""Exercise a built distribution through its installed command, outside the checkout.

    python -m build
    python scripts/smoke_package.py dist

The runner uses only the standard library. It installs the local wheel without
network access or dependencies into a temporary environment and removes it on exit.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tarfile
import unittest
import venv
import xml.etree.ElementTree as ET
import zipfile


class InstalledPackageTests(unittest.TestCase):
    distribution_dir: Path
    workspace: Path
    executable: Path
    fixture: Path
    version: str

    @classmethod
    def setUpClass(cls):
        wheels = list(cls.distribution_dir.glob("skillrot-*.whl"))
        sources = list(cls.distribution_dir.glob("skillrot-*.tar.gz"))
        if len(wheels) != 1 or len(sources) != 1:
            raise AssertionError("Build one wheel and one sdist into a clean output directory.")
        with zipfile.ZipFile(wheels[0]) as archive:
            metadata_path = next(p for p in archive.namelist() if p.endswith(".dist-info/METADATA"))
            metadata = archive.read(metadata_path).decode("utf-8")
            cls.version = next(line.split(": ", 1)[1] for line in metadata.splitlines()
                               if line.startswith("Version: "))
            if any(line.startswith("Requires-Dist:") for line in metadata.splitlines()):
                raise AssertionError("skillrot must retain zero runtime dependencies.")
            if not any(p.endswith("/LICENSE") for p in archive.namelist()):
                raise AssertionError("The wheel must include the license.")
        cls.temporary = tempfile.TemporaryDirectory(prefix="skillrot-package-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.workspace = Path(cls.temporary.name)
        environment = cls.workspace / "environment"
        venv.EnvBuilder(with_pip=True).create(environment)
        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        interpreter = scripts / ("python.exe" if os.name == "nt" else "python")
        cls.executable = scripts / ("skillrot.exe" if os.name == "nt" else "skillrot")
        install = subprocess.run(
            [str(interpreter), "-m", "pip", "install", "--no-index", "--no-deps", str(wheels[0])],
            cwd=cls.workspace, capture_output=True, timeout=120,
        )
        if install.returncode:
            raise AssertionError(install.stderr.decode("utf-8", errors="replace"))
        cls.fixture = cls.workspace / "skills with spaces"
        cls.write_skill(cls.fixture / "notes")

    @staticmethod
    def write_skill(directory: Path, content=None):
        directory.mkdir(parents=True, exist_ok=True)
        text = content if content is not None else (
            "---\nname: notes\ndescription: Use when the user asks to organize notes.\n"
            "---\nRead and organize the notes.\n"
        )
        (directory / "SKILL.md").write_text(text, encoding="utf-8")

    def run_command(self, *arguments, encoding="utf-8"):
        environment = os.environ.copy()
        for name in ("PYTHONPATH", "PYTHONHOME", "SLASH_COMMAND_TOOL_CHAR_BUDGET"):
            environment.pop(name, None)
        environment["PYTHONIOENCODING"] = encoding
        return subprocess.run(
            [str(self.executable)] + [str(argument) for argument in arguments],
            cwd=self.workspace, env=environment, capture_output=True, timeout=30,
        )

    def assert_exit(self, result, expected):
        self.assertEqual(result.returncode, expected,
                         result.stderr.decode("utf-8", errors="replace"))
        self.assertNotIn(b"Traceback", result.stderr)

    def test_installed_version_and_help(self):
        version = self.run_command("--version")
        self.assert_exit(version, 0)
        self.assertEqual(version.stdout.decode("utf-8").strip(), "skillrot " + self.version)
        help_result = self.run_command("--help")
        self.assert_exit(help_result, 0)
        self.assertIn(b"--fail-over-budget", help_result.stdout)

    def test_clean_json_contract(self):
        result = self.run_command(self.fixture, "--portable", "--no-usage", "--json", "--fail-on", "error")
        self.assert_exit(result, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["version"], self.version)
        self.assertEqual(payload.get("schema_version"), 1)
        self.assertEqual(payload.get("model", {}).get("harness"), "claude-code")
        self.assertTrue(payload.get("model", {}).get("estimated"))
        self.assertIs(payload.get("model", {}).get("usage_available"), False)
        self.assertEqual(payload["budget"]["skills"], 1)
        self.assertEqual(payload["skills"][0]["command"], "notes")
        self.assertEqual(payload["findings"], [])

    def test_svg_export_produces_valid_artifact(self):
        chart = self.workspace / "budget.svg"
        result = self.run_command(self.fixture, "--no-usage", "--svg", chart)
        self.assert_exit(result, 0)
        self.assertEqual(ET.parse(chart).getroot().tag, "{http://www.w3.org/2000/svg}svg")

    def test_lint_and_budget_gates(self):
        broken = self.workspace / "broken" / "notes"
        self.write_skill(broken, "\n---\nname: notes\ndescription: Use when organizing notes.\n---\nBody.\n")
        result = self.run_command(broken, "--no-usage", "--json", "--fail-on", "error")
        self.assert_exit(result, 1)
        self.assertIn("SR001", [finding["rule"] for finding in json.loads(result.stdout)["findings"]])
        over = self.run_command(self.fixture, "--no-usage", "--json", "--context-window", 100,
                                "--fail-over-budget")
        self.assert_exit(over, 1)
        self.assertTrue(json.loads(over.stdout)["budget"]["overflows"])

    def test_missing_input_cannot_pass_a_partial_scan(self):
        missing = self.workspace / "missing"
        for paths in [(missing,), (self.fixture, missing)]:
            with self.subTest(paths=paths):
                result = self.run_command(*paths, "--no-usage", "--json", "--fail-on", "error")
                self.assert_exit(result, 2)

    def test_failed_svg_export_is_operational_error(self):
        result = self.run_command(self.fixture, "--no-usage", "--svg",
                                  self.workspace / "absent" / "chart.svg")
        self.assert_exit(result, 2)

    def test_invalid_numeric_options_are_usage_errors(self):
        for option, value in [("--chars-per-token", "0"), ("--chars-per-token", "nan"),
                              ("--context-window", "-1"), ("--budget-fraction", "nan")]:
            with self.subTest(option=option, value=value):
                result = self.run_command(self.fixture, "--no-usage", option, value)
                self.assert_exit(result, 2)

    def test_unicode_path_json_survives_legacy_output_encoding(self):
        directory = self.workspace / "\u65e5\u672c\u8a9e" / "notes"
        self.write_skill(directory)
        result = self.run_command(directory, "--no-usage", "--json", encoding="cp1251")
        self.assert_exit(result, 0)
        self.assertEqual(Path(json.loads(result.stdout)["skills"][0]["path"]), directory / "SKILL.md")


class SourceDistributionTests(unittest.TestCase):
    distribution_dir: Path

    def test_source_archive_can_run_tests_and_build_both_skill_profiles(self):
        sources = list(self.distribution_dir.glob("skillrot-*.tar.gz"))
        self.assertEqual(len(sources), 1, "Build exactly one source distribution.")
        with tempfile.TemporaryDirectory(prefix="skillrot-sdist-") as temporary:
            destination = Path(temporary)
            with tarfile.open(sources[0]) as archive:
                members = archive.getmembers()
                roots = {Path(member.name).parts[0] for member in members}
                self.assertEqual(len(roots), 1)
                source = destination / next(iter(roots))
                required = ["scripts/build_skill_bundle.py", "scripts/smoke_package.py",
                            "SKILL.md", "docs/RULES.md", "marketplace/skillrot/SKILL.md",
                            "marketplace/skillrot/README.md"]
                names = {member.name for member in members}
                for name in required:
                    self.assertIn(source.name + "/" + name, names,
                                  "Source distribution lacks a delivery resource: " + name)
                for member in members:
                    target = destination / member.name
                    target.resolve().relative_to(destination.resolve())
                    self.assertFalse(member.issym() or member.islnk(), "Source archive must not contain links.")
                    if member.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                    elif member.isfile():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        handle = archive.extractfile(member)
                        self.assertIsNotNone(handle)
                        if handle is not None:
                            with handle:
                                target.write_bytes(handle.read())
            environment = os.environ.copy()
            for name in ("PYTHONPATH", "PYTHONHOME", "SLASH_COMMAND_TOOL_CHAR_BUDGET"):
                environment.pop(name, None)
            interpreter = sys.executable
            tests = subprocess.run([interpreter, "-m", "unittest", "discover", "-s", "tests", "-q"],
                                   cwd=source, env=environment, capture_output=True, timeout=120)
            self.assertEqual(tests.returncode, 0, tests.stderr.decode("utf-8", errors="replace"))
            for profile in ("local", "agensi"):
                result = subprocess.run([interpreter, "scripts/build_skill_bundle.py", "--profile", profile,
                                         "--output-dir", str(destination / "bundles")],
                                        cwd=source, env=environment, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
                bundles = list((destination / "bundles").glob("skillrot-*-" + profile + ".zip"))
                self.assertEqual(len(bundles), 1)
                with zipfile.ZipFile(bundles[0]) as archive:
                    manifest = json.loads(archive.read("skillrot/manifest.json"))
                    self.assertEqual(manifest["profile"], profile)
                    self.assertIn("skillrot/SKILL.md", archive.namelist())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path, help="Directory containing the built wheel and sdist.")
    arguments = parser.parse_args()
    InstalledPackageTests.distribution_dir = arguments.dist.resolve()
    SourceDistributionTests.distribution_dir = arguments.dist.resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(InstalledPackageTests)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(SourceDistributionTests))
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
