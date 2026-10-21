"""Feature fixture contracts, real binary ABI/reproducibility and spec-only Git preparation."""
import contextlib
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILD = runpy.run_path(str(ROOT / "scripts/build-homebrew-feature-fixtures.py"))
PREPARE = runpy.run_path(str(ROOT / "scripts/prepare-homebrew-feature-fixture.py"))
PIN = runpy.run_path(str(ROOT / "scripts/pin-homebrew-candidate.py"))["pin"]
VERIFY = runpy.run_path(str(ROOT / "scripts/verify-homebrew-candidate.py"))["verify"]


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL, text=True).strip()


@contextlib.contextmanager
def cwd(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class FeatureTests(unittest.TestCase):
    def test_all_candidate_pins_and_defaults_are_updated_before_writes(self):
        paths = [".github/workflows/homebrew-acceptance.yml", ".github/workflows/test.yml",
                 ".github/workflows/homebrew-features-acceptance.yml", ".github/workflows/homebrew-features-negative.yml"]
        with tempfile.TemporaryDirectory() as directory:
            selected = []
            for index, path in enumerate(paths):
                output = Path(directory) / str(index)
                output.write_text((ROOT / path).read_text())
                selected.append(output)
            PIN("a" * 40, *selected)
            VERIFY("a" * 40, *[path.read_text() for path in selected])
            self.assertEqual(sum(path.read_text().count("        default: " + "a" * 40) for path in selected), 2)
            original = [path.read_bytes() for path in selected]
            selected[-1].write_text("invalid workflow")
            with self.assertRaises(ValueError):
                PIN("b" * 40, *selected)
            self.assertEqual([path.read_bytes() for path in selected[:-1]], original[:-1])
            with self.assertRaises(ValueError):
                VERIFY("b" * 40, *[path.read_text() for path in selected])

    def test_packaging_commit_changes_only_revision_and_replays_without_moving_branch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote, repo = root / "remote.git", root / "source"
            subprocess.run(["git", "init", "--bare", "--initial-branch=main", str(remote)], check=True, capture_output=True)
            subprocess.run(["git", "clone", str(remote), str(repo)], check=True, capture_output=True)
            for key, value in [("user.name", "test"), ("user.email", "test@example.invalid"), ("commit.gpgsign", "false"),
                               ("core.hooksPath", "/dev/null"), ("gc.auto", "0"), ("maintenance.auto", "false")]:
                git(repo, "config", key, value)
            path = repo / PREPARE["SPEC"]
            path.parent.mkdir(parents=True)
            path.write_bytes((ROOT / PREPARE["SPEC"]).read_bytes())
            (repo / ".gitignore").write_text("dist/\n")
            (repo / "upstream.txt").write_text("unchanged upstream payload\n")
            git(repo, "add", ".")
            git(repo, "commit", "-m", "source")
            source = git(repo, "rev-parse", "HEAD")
            index = git(repo, "write-tree")
            git(repo, "push", "origin", "main")
            with cwd(repo):
                result = PREPARE["prepare"](source, 7, 2, Path("dist/dataset.json"))
                self.assertEqual(PREPARE["prepare"](source, 7, 2, Path("dist/dataset.json")), result)
                packaging = result["spec_commit"]
                self.assertEqual(git(repo, "rev-list", "--parents", "-n", "1", packaging).split(), [packaging, source])
                self.assertEqual(git(repo, "diff", "--name-only", source, packaging), PREPARE["SPEC"])
                self.assertEqual(git(repo, "show", packaging + ":upstream.txt"), "unchanged upstream payload")
                self.assertEqual(git(repo, "rev-parse", "HEAD"), source)
                self.assertEqual(git(repo, "write-tree"), index)
                self.assertEqual(git(repo, "status", "--porcelain"), "")
                self.assertEqual(result["version"], "1.7.2")
                self.assertNotEqual(result["source_spec_sha256"], result["packaging_spec_sha256"])
                frozen = Path("dist/dataset.json").read_bytes()
                git(repo, "push", "origin", source + ":refs/heads/homebrew-feature-spec-8-1")
                with self.assertRaisesRegex(ValueError, "wrong parents"):
                    PREPARE["prepare"](source, 8, 1, Path("dist/dataset.json"))
                self.assertEqual(Path("dist/dataset.json").read_bytes(), frozen)
                (repo / "unrelated.txt").write_text("uncommitted")
                with self.assertRaisesRegex(ValueError, "clean"):
                    PREPARE["prepare"](source, 9, 1, Path("dist/dataset.json"))

    def test_binary_headers_reject_shell_scripts_and_unsupported_abi(self):
        for raw in [b"#!/bin/sh\necho fixture\n", b"\x7fELF", b"x" * 64]:
            with self.assertRaises(ValueError):
                BUILD["binary_identity"](raw)

    def test_real_four_platform_binaries_and_reproducible_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = BUILD["build"]("1.7.2", ROOT / "native-fixture", root / "first")
            second = BUILD["build"]("1.7.2", ROOT / "native-fixture", root / "second")
            self.assertEqual(first, second)
            for platform, (goos, goarch) in BUILD["TARGETS"].items():
                name = "releaseway-native-fixture_" + platform.replace("-", "_") + ".tar.gz"
                raw = (root / "first" / name).read_bytes()
                self.assertEqual(raw, (root / "second" / name).read_bytes())
                with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
                    members = archive.getmembers()
                    self.assertEqual([member.name for member in members], ["releaseway-native-fixture"])
                    self.assertEqual((members[0].mode, members[0].mtime, members[0].uid, members[0].gid), (0o755, 0, 0, 0))
                    binary = archive.extractfile(members[0]).read()
                self.assertEqual(BUILD["binary_identity"](binary), (goos, goarch))
                self.assertEqual(sha256(raw).hexdigest(), next(item["sha256"] for item in first["platforms"] if item["platform"] == platform))
                if platform == "linux-x86_64" and os.uname().machine == "x86_64":
                    executable = root / "native"
                    executable.write_bytes(binary)
                    executable.chmod(0o755)
                    self.assertIn("releaseway-native-fixture 1.7.2 linux/amd64", subprocess.check_output([str(executable), "--version"], text=True))

    def test_public_workflow_covers_same_job_upgrade_and_isolated_rejections(self):
        main = (ROOT / ".github/workflows/homebrew-features-acceptance.yml").read_text()
        negative = (ROOT / ".github/workflows/homebrew-features-negative.yml").read_text()
        consumer = (ROOT / "scripts/verify-homebrew-feature-consumer.sh").read_text()
        for job in ["source-r0", "source-r1", "source-rerun", "prebuilt-linux", "prebuilt-macos", "prebuilt-mixed", "consumers", "negative-cases", "acceptance"]:
            self.assertIn("\n  " + job + ":", main)
        self.assertNotIn("continue-on-error", main)
        self.assertNotIn("always()", main.split("\n  acceptance:")[1])
        for value in ["macos-arm64", "macos-x86_64", "linux-arm64", "linux-x86_64"]:
            self.assertIn("platform: " + value, main)
        self.assertLess(consumer.index('checkout --quiet --detach "$TAP_ZERO"'), consumer.index('brew install --build-from-source "$qualified"'))
        self.assertLess(consumer.index('checkout --quiet --detach "$TAP_ONE"'), consumer.index('brew upgrade "$qualified"'))
        self.assertIn('[ "$updated_package" = "${VERSION}_1" ]', consumer)
        self.assertNotIn("secrets.", main.split("\n  consumers:")[1].split("\n  negative-cases:")[0])
        self.assertIn("scripts/resolve-homebrew-feature-negative.py", negative)
        self.assertIn("tap_deploy_key: ${{ secrets.HOMEBREW_TAP_DEPLOY_KEY }}", negative)
        self.assertIn("releaseway-acceptance-${{ github.run_attempt }}", main)


if __name__ == "__main__":
    unittest.main()
