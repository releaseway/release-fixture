"""Collect schema-2 Homebrew acceptance from actual public invocation, consumer and rejection evidence."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ["macos-arm64", "macos-x86_64", "linux-arm64", "linux-x86_64"]
RUNNERS = dict(zip(TARGETS, ["macos-latest", "macos-15-intel", "ubuntu-24.04-arm", "ubuntu-24.04"]))
CONTEXT_KEYS = ["formula", "formula_sha256", "source_commit", "spec_commit", "spec_path", "spec_sha256", "version",
                "version_scheme", "revision", "declaration_mode", "declared_platforms", "required_platforms", "runners"]
ROLES = {
    "source-r0": ("SOURCE_ZERO_ARTIFACT", "source", TARGETS, 0),
    "source-r1": ("SOURCE_ONE_ARTIFACT", "source", TARGETS, 1),
    "source-rerun": ("SOURCE_RERUN_ARTIFACT", "source", TARGETS, 1),
    "prebuilt-linux": ("PREBUILT_LINUX_ARTIFACT", "linux", ["linux-x86_64"], 0),
    "prebuilt-macos": ("PREBUILT_MACOS_ARTIFACT", "macos", ["macos-arm64"], 0),
    "prebuilt-mixed": ("PREBUILT_MIXED_ARTIFACT", "mixed", ["macos-arm64", "linux-x86_64"], 0),
}
NAMES = {"source": "releaseway-source-platform-fixture", "linux": "releaseway-prebuilt-linux-fixture",
         "macos": "releaseway-prebuilt-macos-fixture", "mixed": "releaseway-prebuilt-mixed-fixture"}


def require(value, message):
    if not value:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate evidence JSON key")
        result[key] = value
    return result


def parse(raw):
    return json.loads(raw, object_pairs_hook=unique)


def gh(path):
    result = subprocess.run(["gh", "api", path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=90)
    require(result.returncode == 0 and len(result.stdout) <= 1024 * 1024, "GitHub evidence lookup failed or exceeds limit")
    return result.stdout


def api(path):
    return parse(gh(path))


def one_file(name):
    files = list(Path("evidence").rglob(name))
    require(len(files) == 1, "missing or ambiguous feature evidence file: " + name)
    return parse(files[0].read_bytes())


def original_invocation(artifact_id, env, aggregate):
    repo, run_id = env["GITHUB_REPOSITORY"], int(env["GITHUB_RUN_ID"])
    metadata = api(f"repos/{repo}/actions/artifacts/{artifact_id}")
    require(type(metadata["id"]) is int and metadata["id"] == artifact_id and metadata["expired"] is False
            and 0 < metadata["size_in_bytes"] <= 1024 * 1024, "invalid native validation artifact")
    require(metadata["workflow_run"]["id"] == run_id and metadata["workflow_run"]["head_sha"] == env["GITHUB_SHA"],
            "validation artifact belongs to another caller run")
    raw = gh(f"repos/{repo}/actions/artifacts/{artifact_id}/zip")
    digest = hashlib.sha256(raw).hexdigest()
    require(metadata["digest"] == "sha256:" + digest, "native artifact provider digest differs")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        require(len(members) == 1 and members[0].filename == "homebrew-validation.json"
                and members[0].file_size <= 100 * 1024
                and (members[0].external_attr >> 16 & 0o170000) in (0, 0o100000), "unexpected native validation archive layout")
        validation = parse(archive.read(members[0]))
    require(type(validation["schema"]) is int and validation["schema"] == 1 and validation["kind"] == "homebrew-validation",
            "unexpected native validation schema")
    context = {key: validation[key] for key in CONTEXT_KEYS}
    scope = dict(invocation_id=validation["invocation_id"], automation_repository="releaseway/homebrew-actions",
                 automation_sha=env["AUTOMATION_REF"], caller_repository=repo, caller_sha=env["GITHUB_SHA"],
                 run_id=run_id, run_attempt=int(env["GITHUB_RUN_ATTEMPT"]))
    require(aggregate(context, scope, validation["native_receipts"]) == validation, "native receipt aggregate differs")
    require(metadata["name"] == "homebrew-validation-" + validation["invocation_id"], "native artifact invocation name differs")
    return dict(artifact={key: metadata[key] for key in ["id", "name", "size_in_bytes", "digest", "created_at", "expires_at"]},
                zip_sha256=digest, zip_base64=base64.b64encode(raw).decode(), validation=validation)


def collect(env):
    require(env["GITHUB_REPOSITORY"] == "releaseway/release-fixture" and env["SOURCE_COMMIT"] == env["GITHUB_SHA"], "unexpected feature fixture identity")
    run_id, attempt = int(env["GITHUB_RUN_ID"]), int(env["GITHUB_RUN_ATTEMPT"])
    require(env["VERSION"] == f"1.{run_id}.{attempt}", "rerun all jobs to collect a fresh current attempt")
    dataset, build = one_file("homebrew-feature-dataset.json"), one_file("native-build.json")
    expected_dataset = dict(source_commit=env["SOURCE_COMMIT"], spec_commit=env["SPEC_COMMIT"], version=env["VERSION"], release_tag=env["RELEASE_TAG"])
    require(all(dataset[key] == value for key, value in expected_dataset.items()), "source/spec fixture dataset differs")
    spec_zero = (ROOT / ".github/homebrew/features/source.yml").read_bytes()
    spec_one = spec_zero.replace(b"revision: 0\n", b"revision: 1\n")
    require(spec_zero.count(b"revision: 0\n") == 1 and dataset["source_spec_sha256"] == hashlib.sha256(spec_zero).hexdigest()
            and dataset["packaging_spec_sha256"] == hashlib.sha256(spec_one).hexdigest(), "packaging spec digest differs")
    packaging = api(f'repos/{env["GITHUB_REPOSITORY"]}/commits/{env["SPEC_COMMIT"]}')
    require([parent["sha"] for parent in packaging["parents"]] == [env["SOURCE_COMMIT"]]
            and [file["filename"] for file in packaging["files"]] == [dataset["spec_path"]], "packaging commit changes upstream payload")
    require(build["version"] == env["VERSION"] and re.match(r"go version go1\.26\.", build["toolchain"]), "fixture Go toolchain/version differs")
    require(build["source_files"] == {name: hashlib.sha256((ROOT / "native-fixture" / name).read_bytes()).hexdigest() for name in ["go.mod", "main.go"]}, "compiled Go source files differ")
    release = api(f'repos/{env["GITHUB_REPOSITORY"]}/releases/tags/{env["RELEASE_TAG"]}')
    commit = api(f'repos/{env["GITHUB_REPOSITORY"]}/commits/{env["RELEASE_TAG"]}')["sha"]
    require(release["immutable"] is True and release["draft"] is False and release["prerelease"] is True
            and commit == env["SOURCE_COMMIT"], "native asset release is not the isolated immutable source")
    assets = {asset["name"]: asset for asset in release["assets"]}
    require([entry["platform"] for entry in build["platforms"]] == TARGETS, "four compiled binary targets required")
    for entry in build["platforms"]:
        asset = assets.get(entry["asset"])
        require(asset and asset["state"] == "uploaded" and asset["digest"] == "sha256:" + entry["sha256"]
                and asset["size"] == entry["size"], "published binary differs from ABI-checked build")
    aggregate = runpy.run_path(str(ROOT / "automation/internal/scripts/aggregate-formula-validation.py"))["aggregate"]
    invocations = []
    for role, (key, spec, targets, revision) in ROLES.items():
        invocation = original_invocation(int(env[key]), env, aggregate)
        invocation["role"] = role
        context = invocation["validation"]
        expected_spec = env["SPEC_COMMIT"] if revision else env["SOURCE_COMMIT"]
        expected_digest = dataset["packaging_spec_sha256"] if revision else hashlib.sha256((ROOT / f".github/homebrew/features/{spec}.yml").read_bytes()).hexdigest()
        require(context["formula"] == NAMES[spec] and context["source_commit"] == env["SOURCE_COMMIT"]
                and context["spec_commit"] == expected_spec and context["spec_path"] == f".github/homebrew/features/{spec}.yml"
                and context["spec_sha256"] == expected_digest and context["version"] == env["VERSION"]
                and context["revision"] == revision and context["version_scheme"] == 0
                and context["required_platforms"] == context["declared_platforms"] == targets
                and context["declaration_mode"] == "explicit"
                and context["runners"] == {target: RUNNERS[target] for target in targets}, "native invocation differs from required feature case")
        invocations.append(invocation)
    require(len({item["validation"]["invocation_id"] for item in invocations}) == 6
            and len({item["artifact"]["id"] for item in invocations}) == 6, "reusable invocation artifacts collided")
    by_role = {entry["role"]: entry["validation"] for entry in invocations}
    require(by_role["source-r0"]["formula_sha256"] != by_role["source-r1"]["formula_sha256"]
            and by_role["source-r1"]["formula_sha256"] == by_role["source-rerun"]["formula_sha256"]
            and env["RERUN_STATE"] == "unchanged", "revision publication/rerun bytes differ")
    files = list(Path("evidence").rglob("consumer.json"))
    require(len(files) == 4, "four native upgrade consumers required")
    consumers = [parse(path.read_bytes()) for path in files]
    seen, cases = set(), []
    unsupported = {"macos-arm64": ("releaseway-prebuilt-linux-fixture", "Linux"), "macos-x86_64": ("releaseway-prebuilt-macos-fixture", "arm64"),
                   "linux-arm64": ("releaseway-prebuilt-linux-fixture", "x86_64"), "linux-x86_64": ("releaseway-prebuilt-macos-fixture", "macOS")}
    for consumer in consumers:
        platform = consumer["platform"]
        require(platform in TARGETS and platform not in seen, "unexpected/duplicate native consumer")
        seen.add(platform)
        require(consumer["run_id"] == run_id and consumer["run_attempt"] == attempt and consumer["fixture_commit"] == env["GITHUB_SHA"]
                and consumer["source_commit"] == env["SOURCE_COMMIT"] and consumer["spec_commit"] == env["SPEC_COMMIT"]
                and consumer["candidate_sha"] == env["AUTOMATION_REF"] and consumer["version"] == env["VERSION"],
                "consumer identity differs")
        require((consumer["tap_zero"], consumer["tap_one"], consumer["tap_final"]) == (env["TAP_ZERO"], env["TAP_ONE"], env["TAP_FINAL"])
                and consumer["zero_formula_sha256"] == by_role["source-r0"]["formula_sha256"]
                and consumer["one_formula_sha256"] == by_role["source-r1"]["formula_sha256"]
                and consumer["initial_package"] == env["VERSION"] and consumer["updated_package"] == env["VERSION"] + "_1",
                "same-job installed keg upgrade proof differs")
        goos, goarch = ("darwin" if platform.startswith("macos") else "linux"), ("arm64" if platform.endswith("arm64") else "amd64")
        require(consumer["native_output"].startswith(f'releaseway-native-fixture {env["VERSION"]} {goos}/{goarch} '), "native consumer executed wrong ABI")
        require(consumer["unsupported_rejected"] is True and (consumer["unsupported_formula"], consumer["unsupported_requirement"]) == unsupported[platform],
                "unsupported native installation proof differs")
    for platform in TARGETS:
        cases += [dict(id="source-install-" + platform, state="verified", invocation="source-r1", platform=platform),
                  dict(id="revision-upgrade-" + platform, state="verified", platform=platform),
                  dict(id="unsupported-" + platform, state="verified", platform=platform)]
    negatives = one_file("negatives.json")
    require(negatives["run_id"] == run_id and negatives["run_attempt"] == attempt and negatives["candidate_sha"] == env["AUTOMATION_REF"]
            and negatives["fixture_commit"] == env["GITHUB_SHA"], "negative case parent differs")
    required_negatives = {"revision-decrease", "source-replacement", "missing-asset", "missing-receipt", "native-arch-mismatch"}
    require(len(negatives["cases"]) == 5 and {entry["case"] for entry in negatives["cases"]} == required_negatives, "negative cases missing")
    for entry in negatives["cases"]:
        require(entry["state"] == "rejected" and entry["before"] == entry["after"] and re.fullmatch(r"[a-f0-9]{40}", entry["before"]),
                "negative case changed tap or did not reject")
        cases.append(dict(id=entry["case"] + "-rejected", state="verified"))
    cases += [dict(id="revision-rerun", state="verified", invocation="source-rerun")]
    cases += [dict(id=role, state="verified", invocation=role) for role in ["prebuilt-linux", "prebuilt-macos", "prebuilt-mixed"]]
    require(len(cases) == 21 and len({case["id"] for case in cases}) == 21, "feature case inventory differs")
    return dict(schema=2, candidate_repository="releaseway/homebrew-actions", candidate_sha=env["AUTOMATION_REF"],
                fixture_repository=env["GITHUB_REPOSITORY"], fixture_commit=env["GITHUB_SHA"], run_id=run_id, run_attempt=attempt,
                workflow="homebrew-features-acceptance.yml", scenario="homebrew-revision-platforms", state="verified",
                version=env["VERSION"], dataset=dataset, build=build, rerun_state=env["RERUN_STATE"],
                tap=dict(zero=env["TAP_ZERO"], one=env["TAP_ONE"], final=env["TAP_FINAL"]),
                fixture_release=dict(id=release["id"], tag=release["tag_name"], commit=commit,
                                     assets=[{key: asset[key] for key in ["id", "name", "size", "digest"]} for asset in release["assets"]]),
                invocations=invocations, consumers=sorted(consumers, key=lambda item: TARGETS.index(item["platform"])),
                negatives=negatives["cases"], cases=cases)


if __name__ == "__main__":
    evidence = collect(os.environ)
    raw = (json.dumps(evidence, sort_keys=True, indent=2) + "\n").encode()
    require(len(raw) <= 100 * 1024, "feature acceptance exceeds bounded receipt limit")
    Path("acceptance.json").write_bytes(raw)
    print("Verified 21 feature cases and preserved six original invocation artifact ZIPs")
