"""Build real, ABI-checked Go fixtures and deterministic archives for four native targets."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import tarfile
import tempfile

TARGETS = {"macos-arm64": ("darwin", "arm64"), "macos-x86_64": ("darwin", "amd64"),
           "linux-arm64": ("linux", "arm64"), "linux-x86_64": ("linux", "amd64")}


def require(value, message):
    if not value:
        raise ValueError(message)


def binary_identity(raw):
    require(len(raw) >= 64, "truncated executable header")
    if raw[:4] == b"\x7fELF":
        require(raw[4:6] == b"\x02\x01", "expected 64-bit little-endian ELF")
        arch = {62: "amd64", 183: "arm64"}.get(struct.unpack_from("<H", raw, 18)[0])
        require(arch is not None, "unexpected ELF CPU")
        return "linux", arch
    require(raw[:4] == b"\xcf\xfa\xed\xfe", "expected a real ELF or 64-bit Mach-O executable")
    arch = {0x1000007: "amd64", 0x100000C: "arm64"}.get(struct.unpack_from("<I", raw, 4)[0])
    require(arch is not None, "unexpected Mach-O CPU")
    return "darwin", arch


def archive_bytes(binary):
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            member = tarfile.TarInfo("releaseway-native-fixture")
            member.size, member.mode, member.mtime = len(binary), 0o755, 0
            member.uid = member.gid = 0
            member.uname = member.gname = ""
            archive.addfile(member, io.BytesIO(binary))
    return buffer.getvalue()


def build(version, source, output):
    require(re.fullmatch(r"1\.[1-9][0-9]*\.[1-9][0-9]*", version), "invalid isolated fixture version")
    output.mkdir(parents=True, exist_ok=True)
    toolchain = subprocess.check_output(["go", "version"], text=True).strip()
    manifest = dict(schema=1, version=version, toolchain=toolchain, platforms=[],
                    source_files={name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in ["go.mod", "main.go"]})
    with tempfile.TemporaryDirectory(prefix="releaseway-native-build-") as directory:
        for platform, (goos, goarch) in TARGETS.items():
            binary = Path(directory) / platform
            env = dict(os.environ, CGO_ENABLED="0", GOOS=goos, GOARCH=goarch, GOWORK="off", GOFLAGS="")
            subprocess.run(["go", "build", "-trimpath", "-buildvcs=false",
                            "-ldflags", "-s -w -buildid= -X main.version=" + version,
                            "-o", str(binary), "."], cwd=source, env=env, check=True)
            raw = binary.read_bytes()
            require(binary_identity(raw) == (goos, goarch), "binary ABI differs from declared target")
            metadata = subprocess.check_output(["go", "version", "-m", str(binary)], text=True)
            require("GOOS=" + goos in metadata and "GOARCH=" + goarch in metadata and "CGO_ENABLED=0" in metadata,
                    "Go build metadata differs from declared target")
            compressed = archive_bytes(raw)
            name = "releaseway-native-fixture_" + platform.replace("-", "_") + ".tar.gz"
            (output / name).write_bytes(compressed)
            manifest["platforms"].append(dict(platform=platform, goos=goos, goarch=goarch, asset=name,
                                             binary_sha256=hashlib.sha256(raw).hexdigest(),
                                             sha256=hashlib.sha256(compressed).hexdigest(), size=len(compressed)))
    (output / "native-build.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--source", default="native-fixture", type=Path)
    parser.add_argument("--output", default="dist/homebrew-features", type=Path)
    args = parser.parse_args()
    build(args.version, args.source, args.output)
