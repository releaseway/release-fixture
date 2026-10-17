#!/usr/bin/env python3
import io
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts" / "build-fixtures.py"
DIST = ROOT / "dist"

PLATFORMS = (
    "macos-arm64",
    "macos-x86_64",
    "linux-arm64",
    "linux-x86_64",
)


def build(version: str) -> dict[str, bytes]:
    subprocess.run(["python3", str(BUILD), version], cwd=ROOT, check=True)
    return {
        path.name: path.read_bytes()
        for path in sorted(DIST.glob("release-fixture_*.tar.gz"))
    }


def verify_archive(name: str, data: bytes, version: str, platform: str) -> None:
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        assert [member.name for member in members] == ["release-fixture"]
        member = members[0]
        assert member.mode == 0o755
        executable = archive.extractfile(member)
        assert executable is not None
        text = executable.read().decode()
        assert f"release-fixture {version} {platform}" in text


def main() -> None:
    version = "1.0.0"
    first = build(version)
    second = build(version)
    assert first == second
    assert len(first) == len(PLATFORMS)

    specs = {
        ".github/homebrew/formula.yml": "release-fixture",
        ".github/homebrew/source-formula.yml": "release-source-fixture",
    }
    for path, name in specs.items():
        text = (ROOT / path).read_text()
        assert text.startswith(f"name: {name}\n")
        assert 'command_aliases:' in text
        expected = ['rw-source-fixture'] if name == 'release-source-fixture' else ['rw-fixture', 'release-fixture-cli']
        for alias in expected:
            assert f'  {alias}: {name}' in text
            assert f'"{alias}"' in text.split('test: |')[1]

    for platform in PLATFORMS:
        filename = f"release-fixture_{platform.replace('-', '_')}.tar.gz"
        verify_archive(filename, first[filename], version, platform)

    print("release-fixture regression passed")


if __name__ == "__main__":
    main()
