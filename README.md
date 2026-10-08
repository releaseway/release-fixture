# release-fixture

Deterministic product/source fixture for shared release and Homebrew automation.

This repository behaves like a small product repository. It owns fixture source,
versioned Git tags, immutable GitHub Releases, release assets, and Homebrew specs. Shared
automation is tested from here through its public interfaces rather than by importing
implementation files.

Release creation and notes acceptance use `releaseway/actions v0.4.1`; Homebrew
checks and acceptance use `releaseway/homebrew-actions v0.3.5`. Workflow references
remain pinned to the full release commit SHA. Candidate acceptance can select a
different SHA through the documented inputs and pinning helper.

## Release fixture

Dispatch `release.yml` with `mode=prepare` to calculate the next patch from
`.github/releaseway.yml`, create the unchanged-tree release commit and tag, and push
both atomically through Releaseway. The workflow keeps only the deterministic
product build command and release settings. `mode=resolve` with `tag=vX.Y.Z` verifies
and publishes an existing tag. Both paths use `latest: current-series`; a failed
build/publication can rerun preparation and resume the same release. The verified
`v1.2.8` fixture was generated through this complete preparation/publication flow.

`scripts/build-fixtures.py` produces byte-identical archives for:

- macOS arm64;
- macOS x86_64;
- Linux arm64;
- Linux x86_64.

Each archive contains an executable `release-fixture` command.

The `release fixture` workflow publishes an existing stable `vX.Y.Z` tag with
`release-actions`. It does not implement GitHub Release lifecycle logic itself.

## Homebrew acceptance

Two specs exercise the public Homebrew workflows:

- `.github/homebrew/source-formula.yml`: source-archive validation;
- `.github/homebrew/formula.yml`: GitHub Release asset validation and publishing.

Both specs retain `version_scheme: 1`; acceptance verifies the corresponding
Ruby stanza in both published Formulas.

Run `Homebrew public API acceptance` from the same fixture tag whose immutable GitHub
Release is being validated, and pass that tag as the workflow input. This keeps the
pull-request-style check source and publish source on one immutable commit. The workflow:

1. runs both public `homebrew-actions/check.yml` paths;
2. publishes both source-archive and GitHub Release Formulae with the public
   `homebrew-actions/publish.yml`;
3. writes to the selected allowlisted test tap;
4. verifies reusable-workflow outputs and both resulting Formulae.

Publishing requires an Actions secret named `HOMEBREW_TAP_DEPLOY_KEY` containing a
write deploy key for `releaseway/homebrew-tap-fixture`. No production tap credential
belongs in this repository.

The default destination is `releaseway/homebrew-tap-fixture`. Starter acceptance can
select `releaseway/homebrew-starter-smoke` with the `STARTER_TAP_DEPLOY_KEY` secret.
Only these matching test tap/credential pairs are accepted. The smoke tap is
temporary; its repository and credential are removed after acceptance.

## Local validation

```sh
python3 test/fixtures.py
python3 test/candidates.py
```

CI also lints all fixture workflows.

## Candidate release readiness

Each action repository's `release.yml` requires an existing stable `tag` and
`acceptance-runs` containing comma-separated fixture run IDs. It checks the latest
push CI at the tag's exact SHA and all matching acceptance before publication.

| Candidate | Required CI | Required acceptance |
| --- | --- | --- |
| `releaseway/actions` | `test.yml` | `release-notes-acceptance.yml`, `suite=all` |
| `releaseway/npm-actions` | `check.yml` including platform matrix | npm fixture `publish.yml` staged + `direct.yml` fresh published; at least one `version-source=git-tag` |
| `releaseway/homebrew-actions` | `test.yml` | `homebrew-acceptance.yml` source + release Formulae |

For actions, supply full `action-ref` and an existing `notes-acceptance-*`
`publish-tag`. All three suites must succeed. Individual suites remain diagnostic.
Set `upload-concurrency` to exercise the candidate's upload limit (default `1`,
range `1`–`8`). Publication, identical rerun and explicit verification use the
same value; complete acceptance evidence records it. Candidates accepting this
input are required when selecting concurrency above `1`.

For Homebrew, reusable workflow refs must be literal. Before committing the fixture
candidate, run `python3 scripts/pin-homebrew-candidate.py <full-candidate-sha>`.
Review the four changed refs, prepare the corresponding fixture tag and immutable
Release, then dispatch from that fixture tag with matching `automation-ref` and
`tag`. A mismatch fails before tap writes. Internal scripts/rendering come from the
pinned automation checkout. Reruns can report unchanged Formulae; rollback uses the
automation's explicit `allow-downgrade` policy.

Follow the [npm candidate guide](https://github.com/releaseway/npm-actions-fixture#candidate-acceptance)
for fresh versions and tag-derived prereleases. Stage success proves submission;
direct success proves matching live SHA-512 and installed Node 22/24/26 consumers.

Complete successful runs upload `releaseway-acceptance-<run_attempt>` containing one
`acceptance.json`, retained for 30 days. Readiness compares provider repository,
workflow, fixture commit, current attempt and success with the JSON and candidate
SHA. Expired/missing artifacts, another SHA, partial suites and failed runs fail.
Preserve run IDs; rerun acceptance when evidence expires.

Release workflows request `actions: read` plus existing `contents: write`. If their
token cannot download cross-repository artifacts, configure optional
`RELEASEWAY_EVIDENCE_TOKEN` with Actions read access to candidate and fixture repos;
it is used only by the read-only gate. Run the checker locally from an action repo:

```sh
python3 scripts/verify-release-evidence.py \
  --repository releaseway/npm-actions --candidate <full-candidate-sha> \
  --acceptance-runs <staged-run-id>,<direct-run-id>
```

Publication is an explicit dispatch. GitHub Releases need fixture `contents: write`;
npm needs `id-token: write` and its Trusted Publishers; Homebrew writes only to an
allowlisted fixture tap using its deploy key. Reuse compatible immutable Releases
and retry against current tap state after conflicts. The checker performs no writes.
