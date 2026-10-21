"""Exercise expected public-workflow failures and actual native guards without accepting unrelated failures."""
import json
import os
import re
from pathlib import Path
import runpy
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
TAP = "releaseway/homebrew-tap-fixture"
MARKERS = {"revision-decrease": ("publish", "Refusing Formula revision downgrade"),
           "source-replacement": ("publish", "Same-version Formula updates require the same source commit"),
           "missing-asset": ("generate", "missing asset deliberately-missing-native-fixture.tar.gz")}
CONTEXT_KEYS = ["formula", "formula_sha256", "source_commit", "spec_commit", "spec_path", "spec_sha256",
                "version", "version_scheme", "revision", "declaration_mode", "declared_platforms", "required_platforms", "runners"]


def require(value, message):
    if not value:
        raise ValueError(message)


def gh(args, raw=None):
    attempts = 4 if args[-1].endswith("/logs") else 1
    for attempt in range(attempts):
        result = subprocess.run(["gh", *args], input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90)
        if result.returncode == 0:
            break
        error = result.stderr.decode(errors="replace")
        # Completed job logs can briefly lag the run's completed state.
        if "HTTP 404" in error and attempt + 1 < attempts:
            time.sleep(2)
            continue
        status = re.search(r"HTTP (\d{3})", error)
        reason = status[0] if status else "CLI escape safety" if "escape sequences" in error else f"exit {result.returncode}"
        raise ValueError("GitHub negative-case lookup/dispatch failed: " + reason)
    require(len(result.stdout) <= 1024 * 1024, "negative-case response exceeds limit")
    return result.stdout


def job_log(repo, job_id):
    raw = gh(["api", "--allow-escape-sequences", f"repos/{repo}/actions/jobs/{job_id}/logs"]).decode(errors="replace")
    return re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", raw)


def api(path):
    return json.loads(gh(["api", path]))


def tap_head():
    return api("repos/" + TAP + "/git/ref/heads/main")["object"]["sha"]


def select_child(repo, source, title):
    selected = []
    for page in range(1, 11):
        runs = api(f"repos/{repo}/actions/workflows/homebrew-features-negative.yml/runs?event=workflow_dispatch&head_sha={source}&per_page=100&page={page}")["workflow_runs"]
        selected += [run for run in runs if run["display_title"] == title]
        if len(runs) < 100:
            break
    require(len(selected) <= 1, "ambiguous negative child runs")
    return selected[0] if selected else None


def publication_failure(case, env):
    repo, source = env["GITHUB_REPOSITORY"], env["SOURCE_COMMIT"]
    title = f'homebrew-negative-{case}-{env["GITHUB_RUN_ID"]}-{env["GITHUB_RUN_ATTEMPT"]}'
    before = tap_head()
    child = select_child(repo, source, title)
    if child is None:
        body = dict(ref=env["RELEASE_TAG"], inputs={
            "case": case, "automation-ref": env["AUTOMATION_REF"], "source-commit": source,
            "spec-commit": env["SPEC_COMMIT"], "version": env["VERSION"],
            "parent-run": env["GITHUB_RUN_ID"], "parent-attempt": env["GITHUB_RUN_ATTEMPT"]})
        gh(["api", "--method", "POST", f"repos/{repo}/actions/workflows/homebrew-features-negative.yml/dispatches", "--input", "-"],
           json.dumps(body).encode())
    deadline = time.monotonic() + 30 * 60
    while time.monotonic() < deadline:
        child = select_child(repo, source, title) if child is None else api(f'repos/{repo}/actions/runs/{child["id"]}')
        if child is not None and child["status"] == "completed":
            break
        time.sleep(10)
    require(child is not None and child["status"] == "completed" and child["conclusion"] == "failure", "expected negative child failure was not observed")
    require(child["head_sha"] == source and child["repository"]["full_name"] == repo
            and child["path"] == ".github/workflows/homebrew-features-negative.yml"
            and child["event"] == "workflow_dispatch", "negative child provider identity differs")
    jobs = api(f'repos/{repo}/actions/runs/{child["id"]}/attempts/{child["run_attempt"]}/jobs?per_page=100')["jobs"]
    job_name, marker = MARKERS[case]
    failed = [job for job in jobs if job["conclusion"] == "failure" and job["name"].endswith("/ " + job_name)]
    require(len(failed) == 1, "negative child failed in an unrelated job")
    log = job_log(repo, failed[0]["id"])
    require(marker in log, "negative child did not reach the required rejection")
    require(tap_head() == before, "negative publication changed the fixture tap")
    return dict(case=case, state="rejected", before=before, after=before, run_id=child["id"],
                run_attempt=child["run_attempt"], fixture_commit=source, workflow="homebrew-features-negative.yml",
                conclusion="failure", failed_job_id=failed[0]["id"], reason=marker)


def native_failures(env):
    original = json.loads(Path("source-validation/homebrew-validation.json").read_text())
    context = {key: original[key] for key in CONTEXT_KEYS}
    scope = dict(invocation_id=original["invocation_id"], automation_repository="releaseway/homebrew-actions",
                 automation_sha=env["AUTOMATION_REF"], caller_repository=env["GITHUB_REPOSITORY"],
                 caller_sha=env["GITHUB_SHA"], run_id=int(env["GITHUB_RUN_ID"]), run_attempt=int(env["GITHUB_RUN_ATTEMPT"]))
    aggregate = runpy.run_path(str(ROOT / "automation/internal/scripts/aggregate-formula-validation.py"))["aggregate"]
    require(aggregate(context, scope, original["native_receipts"]) == original, "original native receipt set differs")
    require(context["required_platforms"] == ["macos-arm64", "macos-x86_64", "linux-arm64", "linux-x86_64"], "expected all native source targets")
    base_env = dict(env, FORMULA_CONTEXT=json.dumps(context), INVOCATION_ID=scope["invocation_id"],
                    AUTOMATION_REPOSITORY=scope["automation_repository"], AUTOMATION_SHA=scope["automation_sha"])
    results = []
    with tempfile.TemporaryDirectory(prefix="homebrew-guard-cases-") as directory:
        root = Path(directory)
        receipt_dir = root / "receipts"
        receipt_dir.mkdir()
        for index, receipt in enumerate(original["native_receipts"][:-1]):
            path = receipt_dir / str(index) / "receipt.json"
            path.parent.mkdir()
            path.write_text(json.dumps(receipt))
        before = tap_head()
        result = subprocess.run(["python3", str(ROOT / "automation/internal/scripts/aggregate-formula-validation.py"),
                                 "--receipts", str(receipt_dir), "--output", str(root / "aggregate.json")],
                                env=base_env, capture_output=True, text=True)
        require(result.returncode != 0 and "receipt set incomplete" in result.stderr
                and not (root / "aggregate.json").exists(), "missing receipt did not block aggregation")
        require(tap_head() == before, "missing receipt case changed tap")
        results.append(dict(case="missing-receipt", state="rejected", before=before, after=before, reason="native receipt set incomplete"))
        before = tap_head()
        runtime_env = dict(base_env, PLATFORM="linux-arm64", REQUESTED_RUNNER=context["runners"]["linux-arm64"],
                           FORMULA_PATH=str(ROOT / "tap/Formula/releaseway-source-platform-fixture.rb"),
                           NATIVE_RUNTIME=str(root / "runtime.json"), NATIVE_RECEIPT=str(root / "receipt.json"))
        result = subprocess.run(["ruby", str(ROOT / "automation/internal/scripts/record-formula-validation.rb"), "--preflight"],
                                env=runtime_env, capture_output=True, text=True)
        require(result.returncode != 0 and "Native hardware architecture mismatch" in result.stderr
                and not (root / "runtime.json").exists() and not (root / "receipt.json").exists(), "actual native architecture mismatch did not block validation")
        require(tap_head() == before, "native architecture mismatch case changed tap")
        results.append(dict(case="native-arch-mismatch", state="rejected", before=before, after=before,
                            reason="Native hardware architecture mismatch", actual_os=os.uname().sysname,
                            actual_arch=os.uname().machine, requested_platform="linux-arm64"))
    return results


def main():
    env = os.environ
    require(env["GITHUB_REPOSITORY"] == "releaseway/release-fixture" and env["SOURCE_COMMIT"] == env["GITHUB_SHA"], "unexpected negative fixture identity")
    require(env["VERSION"] == f'1.{env["GITHUB_RUN_ID"]}.{env["GITHUB_RUN_ATTEMPT"]}', "rerun all jobs for a fresh acceptance attempt")
    records = [publication_failure(case, env) for case in MARKERS]
    records += native_failures(env)
    Path("negatives.json").write_text(json.dumps(dict(schema=1, run_id=int(env["GITHUB_RUN_ID"]),
        run_attempt=int(env["GITHUB_RUN_ATTEMPT"]), candidate_sha=env["AUTOMATION_REF"],
        fixture_commit=env["GITHUB_SHA"], cases=records), sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
