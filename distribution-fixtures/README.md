# Generic distribution acceptance

Test `releaseway/actions/distribute` and its optional Pages workflow through their
public interfaces. The separate `distribution-acceptance.yml` workflow currently
pins the published **v0.6.3** commit
`2abdf26c6f01c1e49da4ba5d85253847fe721fd9`.

The default run publishes a new `distribution-<run>-<attempt>` prerelease with
`latest=false`. It keeps the stable latest Release unchanged and exercises public
reads, cross-repository read access, tamper rejection, repeat preparation and
native fixture scripts on Linux, macOS and Windows. It does not deploy Pages.
The [consumer guide](https://github.com/releaseway/actions/tree/main/distribute)
explains how to use the released functionality outside this fixture.

## Run the source checks

From an authenticated `gh` session with permission to dispatch this fixture:

```sh
gh workflow run distribution-acceptance.yml \
  --repo releaseway/release-fixture --ref main -f pages=false
```

Observe the returned run ID and wait for success. This is a component check,
not complete Pages acceptance. Generated prerelease assets are test payloads;
this workflow does not publish a stable automation version or adopt it in a product.

## Include actual Pages deployment

`pages: true` requires the preconfigured, isolated `releaseway/release-fixture`
Pages site in Actions mode, with no custom domain. The workflow never creates a
site or changes environment protections. The approved fixture site is
<https://releaseway.github.io/release-fixture/>. Its `github-pages` environment
allows `main`; the temporary feature-branch rule used during implementation was
removed. Dispatch from an allowed ref rather than bypassing that restriction.

```sh
gh workflow run distribution-acceptance.yml \
  --repo releaseway/release-fixture --ref main -f pages=true
```

This replaces only the fixture site. It tests latest-stable assets, exact fixture
Release mappings and generated same-run artifact files in sequence; the artifact
fixture is the final live site. All three deployments check actual served bytes,
including hidden files. The final site also receives real 404 and wrong-digest
failure probes. Script execution runs separately from the Pages deploy jobs.

## Verify complete evidence

The complete checker requires all three native receipts and all three Pages modes
for the same automation/source/run/attempt. Reports include immutable artifact IDs
and environment deployment IDs matched to the relevant run/job.

Download the artifact from a successful run. The placeholders below must be
replaced with its actual run ID, attempt and fixture `headSha`; `candidate` is the
full automation SHA pinned in that run's workflow. Run the checker from this
repository with the matching workflow revision checked out and use a fresh output
directory for the download:

```sh
gh run view <run-id> --repo releaseway/release-fixture \
  --json headSha,attempt,status,conclusion
gh run download <run-id> --repo releaseway/release-fixture \
  --name distribution-evidence-<run-id>-<attempt> \
  --dir /tmp/distribution-evidence
python3 scripts/verify-distribution-candidate.py \
  --candidate <full-automation-sha> --source <fixture-head-sha> \
  --run-id <run-id> --attempt <attempt> --evidence /tmp/distribution-evidence
```

Success prints `complete current distribution evidence verified`. For a run with
Pages disabled, add `--public-only`; that validates only the source component and
must not be reported as complete Pages acceptance. Native and aggregate receipts
are retained for seven days; source and individual Pages report artifacts last
one day. Expired source/report artifacts can prevent partial reruns even while
aggregate receipts remain available. Missing required artifacts need a fresh run.

To test another automation candidate, update `AUTOMATION_SHA` and all three literal
reusable-workflow refs together in `.github/workflows/distribution-acceptance.yml`.
There is no `action-ref` dispatch input for this campaign. Before committing, run:

```sh
python3 test/distribution.py
python3 scripts/verify-distribution-candidate.py --candidate <full-automation-sha>
```

The pin-only check is not public execution evidence. Future official actions
releases require both the release-note suite and these complete distribution
receipts. Pass the successful Pages-enabled run as `distribution-run` to the
release workflow (`--distribution-run` to the checker). Its current-attempt artifact
must include all three native platforms and all three Pages modes; public-only
evidence cannot pass the release gate. Existing published releases retain their
historical gate policy.

## Verified v0.5.0 campaign

[Run 39226440359, attempt 1](https://github.com/releaseway/release-fixture/actions/runs/39226440359)
passed all 12 jobs at fixture commit
`ce4750878a78c5ded6526537fe9c085a97edf233` with automation
`1c0b9237f61ee66f68db880963ec03da46c8a6ed` (v0.5.0).
All six receipts were downloaded and checked locally at completion. This is
historical verification evidence; artifacts expire and the live fixture site can
be replaced by later successful campaigns.

## Verified v0.5.1 campaign

[Run 39244272575, attempt 1](https://github.com/releaseway/release-fixture/actions/runs/39244272575)
passed all 12 jobs at fixture commit
`e27e31d2c24e77bafa9e74f5d453ec7783ba28c7` using the historical v0.5.1 SHA
`7427110b565bedef79ab0f80e6821a706d7f21ed`. All six
receipts were downloaded and independently checked for the exact candidate, source,
run and attempt. The campaign covered all three real Pages deployment modes and
public source/script checks on Linux, macOS and Windows. Artifact retention and
site replacement limits described above still apply.
