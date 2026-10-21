"""Create a spec-only packaging commit without changing the caller checkout or index."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

SPEC = ".github/homebrew/features/source.yml"


def git(*args, raw=None, env=None):
    result = subprocess.run(["git", *args], input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, check=True)
    return result.stdout.decode().strip()


def require(value, message):
    if not value:
        raise ValueError(message)


def prepare(source, run_id, attempt, output):
    require(re.fullmatch(r"[a-f0-9]{40}", source), "source must be full lowercase SHA")
    require(type(run_id) is int and run_id > 0 and type(attempt) is int and attempt > 0, "invalid fixture run/attempt")
    require(git("rev-parse", "HEAD") == source, "fixture checkout differs from caller SHA")
    require(not git("status", "--porcelain"), "fixture checkout must be clean")
    original = subprocess.check_output(["git", "show", source + ":" + SPEC])
    changed, count = re.subn(rb"(?m)^revision: 0$", b"revision: 1", original)
    require(count == 1, "expected exactly one explicit source revision zero")
    branch = f"homebrew-feature-spec-{run_id}-{attempt}"
    remote = git("ls-remote", "--heads", "origin", "refs/heads/" + branch)
    if remote:
        packaging = remote.split()[0]
        git("fetch", "origin", "refs/heads/" + branch)
    else:
        blob = git("hash-object", "-w", "--stdin", raw=changed)
        with tempfile.TemporaryDirectory(prefix="releaseway-spec-index-") as directory:
            env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / "index"))
            git("read-tree", source, env=env)
            git("update-index", "--add", "--cacheinfo", "100644," + blob + "," + SPEC, env=env)
            tree = git("write-tree", env=env)
            packaging = git("-c", "user.name=github-actions[bot]", "-c",
                            "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                            "commit-tree", tree, "-p", source, "-m", "test: prepare packaging revision one")
        git("push", "--no-follow-tags", "origin", packaging + ":refs/heads/" + branch)
    require(git("rev-list", "--parents", "-n", "1", packaging).split() == [packaging, source], "packaging commit has wrong parents")
    require(git("diff", "--name-only", source, packaging) == SPEC, "packaging commit changes upstream payload")
    spec_one = subprocess.check_output(["git", "show", packaging + ":" + SPEC])
    require(spec_one == changed, "packaging spec differs from the approved revision change")
    version = f"1.{run_id}.{attempt}"
    result = dict(schema=1, source_commit=source, spec_commit=packaging, spec_branch=branch, version=version,
                  release_tag="homebrew-features-" + version, spec_path=SPEC,
                  source_spec_sha256=hashlib.sha256(original).hexdigest(),
                  packaging_spec_sha256=hashlib.sha256(changed).hexdigest())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


if __name__ == "__main__":
    result = prepare(os.environ["GITHUB_SHA"], int(os.environ["GITHUB_RUN_ID"]), int(os.environ["GITHUB_RUN_ATTEMPT"]),
                     Path("dist/homebrew-feature-dataset.json"))
    with open(os.environ["GITHUB_OUTPUT"], "a") as stream:
        for key in ["source_commit", "spec_commit", "version", "release_tag"]:
            stream.write(key.replace("_", "-") + "=" + result[key] + "\n")
