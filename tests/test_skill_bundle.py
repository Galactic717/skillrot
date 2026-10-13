"""Behavioral delivery checks for standalone and MCP-oriented skill archives."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import skillrot


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_skill_bundle.py"


class SkillBundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="skillrot-bundle-test-")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)

    def builder_module(self):
        spec = importlib.util.spec_from_file_location("skillrot_bundle_builder", BUILDER)
        if spec is None or spec.loader is None:
            self.fail("The skill bundle builder must be importable")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def run_builder(self, profile, output):
        return subprocess.run(
            [sys.executable, str(BUILDER), "--profile", profile, "--output-dir", str(output)],
            cwd=self.workspace, capture_output=True, timeout=30,
        )

    def test_builder_cli_works_outside_the_checkout(self):
        output = self.workspace / "delivery with spaces"
        result = self.run_builder("local", output)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        archives = list(output.glob("*.zip"))
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].name, "skillrot-" + skillrot.__version__ + "-local.zip")

    def test_archive_resources_have_one_root_and_complete_checksums(self):
        expected = {
            "local": {"SKILL.md", "README.md", "skillrot.py", "docs/RULES.md", "LICENSE"},
            "agensi": {"SKILL.md", "README.md", "references/RULES.md", "LICENSE"},
        }
        builder = self.builder_module()
        for profile, resources in expected.items():
            with self.subTest(profile=profile):
                path = builder.build_bundle(self.workspace / profile, profile)
                with zipfile.ZipFile(path) as archive:
                    self.assertEqual(set(archive.namelist()),
                                     {"skillrot/" + name for name in resources | {"manifest.json"}})
                    manifest = json.loads(archive.read("skillrot/manifest.json"))
                    self.assertEqual(manifest["schema_version"], 1)
                    self.assertEqual(manifest["name"], "skillrot")
                    self.assertEqual(manifest["version"], skillrot.__version__)
                    self.assertEqual(manifest["profile"], profile)
                    self.assertEqual(set(manifest["files"]), resources)
                    for name in resources:
                        payload = archive.read("skillrot/" + name)
                        self.assertEqual(manifest["files"][name]["sha256"],
                                         hashlib.sha256(payload).hexdigest())
                        self.assertEqual(manifest["files"][name]["size"], len(payload))

    def test_archives_are_byte_deterministic_and_exclude_repository_noise(self):
        builder = self.builder_module()
        source = self.workspace / "source"
        source.mkdir()
        for name in ("SKILL.md", "skillrot.py", "LICENSE", "docs/RULES.md",
                     "marketplace/skillrot/SKILL.md", "marketplace/skillrot/README.md"):
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        for name in (".env", ".git/config", "private.json", "docs/assets/demo.mp4",
                     "__pycache__/cached.pyc", "dist/old.zip"):
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"private delivery noise")
        with patch.object(builder, "ROOT", source):
            for profile in ("local", "agensi"):
                with self.subTest(profile=profile):
                    first = builder.build_bundle(self.workspace / (profile + "-first"), profile)
                    # Same text and changed source modification times must yield identical bytes.
                    for target in source.rglob("*"):
                        if target.is_file():
                            target.write_bytes(target.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8"))
                            os.utime(target, (1234567890, 1234567890))
                    second = builder.build_bundle(self.workspace / (profile + "-second"), profile)
                    self.assertEqual(first.read_bytes(), second.read_bytes())
                    with zipfile.ZipFile(second) as archive:
                        self.assertTrue(all(member.date_time == (1980, 1, 1, 0, 0, 0)
                                            for member in archive.infolist()))
                        self.assertTrue(all(member.external_attr >> 16 == 0o100644
                                            for member in archive.infolist()))
                        self.assertTrue(all(b"private delivery noise" not in archive.read(name)
                                            for name in archive.namelist()))

    def test_extracted_local_cli_audits_real_files_outside_the_checkout(self):
        builder = self.builder_module()
        artifact = builder.build_bundle(self.workspace / "dist", "local")
        extracted = self.workspace / "installed skill 日本語 with spaces"
        with zipfile.ZipFile(artifact) as archive:
            archive.extractall(extracted)
        folder = self.workspace / "user library" / "notes"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(
            "---\nname: notes\ndescription: Use when the user organizes notes.\n---\nRead notes.\n",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        for name in ("PYTHONPATH", "PYTHONHOME", "SLASH_COMMAND_TOOL_CHAR_BUDGET"):
            environment.pop(name, None)
        result = subprocess.run(
            [sys.executable, str(extracted / "skillrot" / "skillrot.py"), str(folder),
             "--portable", "--no-usage", "--json", "--fail-on", "error"],
            cwd=self.workspace, env=environment, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
        payload = json.loads(result.stdout)
        self.assertEqual(payload["version"], skillrot.__version__)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["budget"]["skills"], 1)
        self.assertEqual(payload["skills"][0]["command"], "notes")
        self.assertEqual(payload["findings"], [])

    def test_both_extracted_skill_frontmatters_are_portable(self):
        builder = self.builder_module()
        for profile in ("local", "agensi"):
            with self.subTest(profile=profile):
                artifact = builder.build_bundle(self.workspace / profile, profile)
                installed = self.workspace / (profile + "-installed")
                with zipfile.ZipFile(artifact) as archive:
                    archive.extractall(installed)
                skill = skillrot.load_skill(installed / "skillrot" / "SKILL.md")
                errors = [finding for finding in skillrot.analyze([skill], portable=True)
                          if finding.severity == "error"]
                self.assertEqual(errors, [])

    def test_symlink_or_junction_resource_is_rejected_instead_of_embedded(self):
        builder = self.builder_module()
        source = self.workspace / "source"
        source.mkdir()
        for name in ("SKILL.md", "LICENSE"):
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        linked = source / "skillrot.py"
        try:
            linked.symlink_to(ROOT / "skillrot.py")
        except (OSError, NotImplementedError):
            if os.name != "nt":
                self.skipTest("This host cannot create file symlinks")
            shutil.copy2(ROOT / "skillrot.py", linked)
            reference = self.workspace / "reference"
            reference.mkdir()
            shutil.copy2(ROOT / "docs/RULES.md", reference / "RULES.md")
            junction = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(source / "docs"), str(reference)],
                capture_output=True,
            )
            if junction.returncode:
                self.skipTest("Neither file symlinks nor directory junctions are available")
        else:
            (source / "docs").mkdir()
            shutil.copy2(ROOT / "docs/RULES.md", source / "docs/RULES.md")
        with patch.object(builder, "ROOT", source):
            with self.assertRaises(ValueError):
                builder.build_bundle(self.workspace / "dist", "local")

    def test_unknown_profile_is_rejected_without_an_archive(self):
        output = self.workspace / "invalid"
        result = self.run_builder("unknown", output)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())
        self.assertNotIn(b"Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
