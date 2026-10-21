# Generic distribution acceptance

Test `releaseway/actions/distribute` and its optional Pages workflow through their
public interfaces. The separate `distribution-acceptance.yml` workflow pins a
reviewed release-set candidate in `AUTOMATION_SHA` and all literal
reusable-workflow refs. Read the workflow at the run's fixture SHA for its exact
candidate. The candidate must implement schema 2 and `site-artifact-id`.

The default run publishes a new `distribution-<run>-<attempt>` prerelease with
`latest=false`. It keeps the stable latest Release unchanged and exercises public
reads, cross-repository read access, tamper rejection, repeat preparation and
native fixture scripts on Linux, macOS and Windows. It also checks the release-set
merge and its deterministic rejection cases on those platforms. It does not deploy Pages.
The [consumer guide](https://github.com/releaseway/actions/tree/main/distribute)
describes the source interfaces and explains how to select a supporting ref.

Before a new candidate/source campaign, commit a fresh prefix in both tracked
`.github/distribution/release-set-{initial,final}.json` policies and their explicit
alias tags. Tags and assets are immutable campaign data. A partial rerun of the
same fixture commit reuses them only after checking the exact tag commit, asset
names, sizes and provider digests. Changing the fixture commit requires a fresh
prefix, even for a documentation-only change. Prefixes are not runtime templates.

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
allows `main`. Dispatch from an allowed ref rather than bypassing that restriction.

```sh
gh workflow run distribution-acceptance.yml \
  --repo releaseway/release-fixture --ref main -f pages=true
```

This replaces only the fixture site. It tests latest-stable assets, exact fixture
Release mappings and generated same-run artifact files in sequence. After the
artifact site's real 404 and wrong-digest probes finish, it deploys documentation
plus A/B version files, observes their served hashes, publishes C, and deploys a
fresh documentation artifact with A/B/C. The final release-set site remains live.
All five deployments check actual served bytes, including hidden files. Script
execution runs separately from Pages deploy jobs and has no publication credential.

## Verify complete evidence

The legacy checker still requires six receipts: three native and three Pages modes
for the same automation/source/run/attempt. A separate aggregate contains three
release-set core receipts and the initial/final Pages receipts. Reports include
immutable artifact IDs and environment deployment IDs matched to the relevant run/job.

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
are retained for seven days; legacy source and individual Pages report artifacts last
one day. Expired source/report artifacts can prevent partial reruns even while
aggregate receipts remain available. Missing required artifacts need a fresh run.

Verify the separate release-set aggregate from that same run:

```sh
gh run download <run-id> --repo releaseway/release-fixture \
  --name release-set-evidence-<run-id>-<attempt> --dir /tmp/release-set-evidence
python3 scripts/verify-release-set-candidate.py \
  --candidate <full-automation-sha> --source <fixture-head-sha> \
  --run-id <run-id> --attempt <attempt> \
  --receipt /tmp/release-set-evidence/acceptance.json
```

Success prints `complete current release-set acceptance verified`. This checks
all eleven cases, expected fixture bytes, old version paths, alias advancement,
empty skip, two fresh documentation artifacts and mixed provenance. Release-set
documentation/core/phase/aggregate artifacts last seven days; individual Pages
reports last one day. The Release fixtures are prereleases with `latest=false`;
the publisher checks that stable latest is unchanged. Explicit alias tags let the
campaign exercise these prerelease fixtures without relabeling them as stable.

To test another automation candidate, update `AUTOMATION_SHA` and all literal
reusable-workflow refs together in `.github/workflows/distribution-acceptance.yml`.
Also choose the fresh campaign prefix described above.
There is no `action-ref` dispatch input for this campaign. Before committing, run:

```sh
python3 test/distribution.py
python3 test/distribution-release-set.py
python3 scripts/verify-distribution-candidate.py --candidate <full-automation-sha>
```

The pin-only check is not public execution evidence. Official actions
releases require the release-note suite, the six legacy distribution receipts and
the separate release-set aggregate from the same complete run. Pass the successful
Pages-enabled run as `distribution-run` to the
release workflow (`--distribution-run` to the checker). Both current-attempt
artifacts are required; public-only evidence cannot pass the release gate.
Existing published releases retain their
historical gate policy.

### Archive provider evidence without publishing

The actions repository's `verify-release-candidate.yml` workflow runs the real
release gate with read-only permissions. It checks the original report/docs ZIPs,
their provider digests and the exact successful native/deployment jobs. It preserves
those ZIPs and API snapshots in `releaseway-evidence.json`, replays it with an empty
`PATH`, then uploads a `release-candidate-evidence-<run>-<attempt>` artifact for
30 days. The configured `RELEASEWAY_EVIDENCE_TOKEN`, when needed, must read the
fixture's Actions artifacts and deployment metadata.

```sh
gh workflow run verify-release-candidate.yml --repo releaseway/actions --ref main \
  -f candidate=<full-automation-sha> -f acceptance-runs=<notes-suite-all-run> \
  -f distribution-run=<complete-pages-run> -f evidence-tag=<prospective-version>
```

`evidence-tag` is only the prospective tag recorded in the bundle; this workflow
creates no tag or Release. Download the bundle while the collector artifact exists
and retain it for later offline verification. Future stable publication still uses
the official release workflow and freezes its own approval asset. A final candidate
SHA needs its own push CI and acceptance, including after documentation changes.

### Verified first release-set campaign

[Distribution run 39565288341](https://github.com/releaseway/release-fixture/actions/runs/39565288341)
and [notes run 39565371787](https://github.com/releaseway/release-fixture/actions/runs/39565371787)
passed for candidate `6f2d04d9c825e1efaed1a9089dc02be22ddef627` at fixture
`b5232e6f240be00e1752d774b64875cca75795ee`.
[Gate collector 39567182206](https://github.com/releaseway/actions/actions/runs/39567182206)
verified the seven original ZIPs and offline replay using checker
`6c7681ec6a71f5db0f60e013db6c38e61f9ffb0f`. These are candidate acceptance
results, not a stable automation release. Later campaigns replace the live site.

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
