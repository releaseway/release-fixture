"""Resolve only the isolated dataset's three expected public-workflow failures."""
import os
import base64
import json
from pathlib import Path
import re
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
runpy.run_path(str(ROOT / "scripts/verify-homebrew-candidate.py"), run_name="__main__")
env = os.environ
source, packaging = env["SOURCE_COMMIT"], env["SPEC_COMMIT"]
if not all(re.fullmatch(r"[a-f0-9]{40}", sha) for sha in [source, packaging]) or source != env["GITHUB_SHA"]:
    raise ValueError("negative case must use the parent immutable fixture source")
parent, attempt = int(env["PARENT_RUN"]), int(env["PARENT_ATTEMPT"])
if parent <= 0 or attempt <= 0 or env["VERSION"] != f"1.{parent}.{attempt}":
    raise ValueError("negative case version differs from parent run/attempt")
def api(path):
    return json.loads(subprocess.check_output(["gh", "api", path], stderr=subprocess.DEVNULL, timeout=60))
parent_run = api(f'repos/{env["GITHUB_REPOSITORY"]}/actions/runs/{parent}')
if (env["GITHUB_REPOSITORY"] != "releaseway/release-fixture" or parent_run["head_sha"] != source
        or parent_run["run_attempt"] != attempt or parent_run["path"] != ".github/workflows/homebrew-features-acceptance.yml"
        or parent_run["event"] != "workflow_dispatch" or parent_run["status"] != "in_progress"):
    raise ValueError("negative case must belong to a currently running feature acceptance")
tap = api('repos/releaseway/homebrew-tap-fixture/contents/Formula/releaseway-source-platform-fixture.rb')
formula = base64.b64decode(tap['content'], validate=False).decode()
if (f'# releaseway-version: {env["VERSION"]}\n' not in formula
        or f'# releaseway-source-commit: {source}\n' not in formula
        or f'# releaseway-spec-commit: {packaging}\n' not in formula or not re.search(r'^  revision 1$', formula, re.M)):
    raise ValueError("negative case baseline must be the parent source/revision one publication")
subprocess.run(["git", "fetch", "origin", packaging], check=True, stdout=subprocess.DEVNULL)
parents = subprocess.check_output(["git", "rev-list", "--parents", "-n", "1", packaging], text=True).strip().split()
changed = subprocess.check_output(["git", "diff", "--name-only", source, packaging], text=True).strip()
if parents != [packaging, source] or changed != ".github/homebrew/features/source.yml":
    raise ValueError("negative case packaging commit changes upstream payload")
spec_zero = subprocess.check_output(["git", "show", source + ":.github/homebrew/features/source.yml"])
spec_one = subprocess.check_output(["git", "show", packaging + ":.github/homebrew/features/source.yml"])
if spec_zero.count(b"revision: 0\n") != 1 or spec_one != spec_zero.replace(b"revision: 0\n", b"revision: 1\n"):
    raise ValueError("negative case packaging revision differs")
cases = {"revision-decrease": (source, source, "source"),
         "source-replacement": (packaging, packaging, "source"),
         "missing-asset": (source, source, "missing")}
commit, spec_commit, path = cases[env["CASE"]]
with open(env["GITHUB_OUTPUT"], "a") as stream:
    stream.write("commit=" + commit + "\nspec-commit=" + spec_commit + "\nspec-path=.github/homebrew/features/" + path + ".yml\n")
