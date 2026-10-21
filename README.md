# release-fixture

Deterministic product/source fixture for shared release, Homebrew and generic file distribution automation.

The Homebrew specs also verify command aliases created by `homebrew-actions`:
`rw-fixture` and `release-fixture-cli` run the release asset's `release-fixture`,
and `rw-source-fixture` runs `release-source-fixture`. Assets contain only the
original executable. Product tests execute every name on the existing native
validation runners, and acceptance artifacts record the verified aliases.

`scripts/pin-homebrew-candidate.py <full-sha>` updates both PR check pins, all four
acceptance check/publish pins and the dispatch default together. Candidate identity
verification rejects mismatched pins before tap publication.

This repository behaves like a small product repository. It owns fixture source,
versioned Git tags, immutable GitHub Releases, release assets, and Homebrew specs. Shared
automation is tested from here through its public interfaces rather than by importing
implementation files.

Workflow files are the source of truth for automation dependencies. Release
creation and notes acceptance have their own actions defaults; Homebrew checks and
acceptance have their own homebrew-actions pins. References use full commit SHAs.
Candidate acceptance can select a different SHA through the documented inputs and
pinning helper. Read the workflow at the fixture commit being tested for its exact
dependency identities.

## Generic distribution acceptance

The [distribution fixture guide](distribution-fixtures/README.md) covers the
separate `distribution-acceptance.yml` campaign: public Release reads on Linux,
macOS and Windows, generated same-run artifacts, and optional real Pages deployment.
Its automation candidate is recorded in `AUTOMATION_SHA` and all literal reusable
workflow refs in `.github/workflows/distribution-acceptance.yml`; it can differ
from the release-creation and notes defaults.

Notes acceptance selects its candidate with `action-ref`. The release-readiness
gate requires complete notes evidence, legacy distribution evidence and the
separate release-set aggregate with Pages enabled, all for the same actions SHA.

## Release fixture

Dispatch `release.yml` with `mode=prepare` to calculate the next patch from
`.github/releaseway.yml`, create the unchanged-tree release commit and tag, and push
both atomically through Releaseway. The workflow keeps only the deterministic
product build command and release settings. `mode=resolve` with `tag=vX.Y.Z` verifies
and publishes an existing tag. Both paths use `latest: current-series`; a failed
build/publication can rerun preparation and resume the same release.

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
Only these matching test tap/credential pairs are accepted. Keep the smoke tap
and its dedicated credential available for repeatable starter acceptance; they
are separate from the permanent fixture tap and any production repository.

The revision/platform campaign uses a separate set of Formula names and
real Go binaries. See [the feature campaign guide](homebrew-features/README.md) for
four native upgrades, single/asymmetric architectures, rejection cases and original
native receipt preservation. Run it and the legacy campaign sequentially against
the shared fixture tap.

## Local validation

```sh
python3 test/fixtures.py
python3 test/candidates.py
python3 test/expected-failure.py
python3 test/distribution.py
python3 test/distribution-release-set.py
python3 test/homebrew-features.py
```

CI also lints all fixture workflows.

## Candidate release readiness

Each action repository's `release.yml` requires an existing stable `tag` and
`acceptance-runs` containing comma-separated fixture run IDs. It checks the latest
push CI at the tag's exact SHA and all matching acceptance before publication.
Pushing a new tag starts another push CI run, so wait for that newest run before
dispatching publication. An earlier successful branch run does not hide a newer
pending or failed run.

| Candidate | Required CI | Required acceptance |
| --- | --- | --- |
| `releaseway/actions` | `test.yml` + `distribution.yml` | `release-notes-acceptance.yml`, `suite=all`, plus full `distribution-acceptance.yml` with legacy and release-set evidence and Pages enabled |
| `releaseway/npm-actions` | `check.yml` including platform matrix | npm fixture `publish.yml` staged + `direct.yml` fresh published; at least one `version-source=git-tag` |
| `releaseway/homebrew-actions` | `test.yml` | `homebrew-acceptance.yml` source + release Formulae and `homebrew-features-acceptance.yml` 21-case revision/platform campaign |

For actions, supply full `action-ref` and an existing `notes-acceptance-*`
`publish-tag`. All three suites must succeed. Individual suites remain diagnostic.
Set `upload-concurrency` to exercise the candidate's upload limit (default `1`,
range `1`–`8`). Publication, identical rerun and explicit verification use the
same value; complete acceptance evidence records it. Candidates accepting this
input are required when selecting concurrency above `1`.

For Homebrew, reusable workflow refs must be literal. Before committing the fixture
candidate, run `python3 scripts/pin-homebrew-candidate.py <full-candidate-sha>`.
Review the 15 changed refs and two dispatch defaults, prepare the corresponding
fixture tag and immutable Release, then dispatch from that fixture tag with matching `automation-ref` and
`tag`. A mismatch fails before tap writes. Internal scripts/rendering come from the
pinned automation checkout. Reruns can report unchanged Formulae; rollback uses the
automation's explicit `allow-downgrade` policy.

Dispatch the feature campaign from fixture main after committing the pins; dispatch
the legacy campaign from its prepared fixture tag. Follow the
[feature guide](homebrew-features/README.md) for their separate source/spec datasets.

Follow the [npm candidate guide](https://github.com/releaseway/npm-actions-fixture#candidate-acceptance)
for fresh versions and tag-derived prereleases. Stage success proves submission;
direct success proves matching live SHA-512 and installed Node 22/24/26 consumers.

Complete successful runs upload `releaseway-acceptance-<run_attempt>` containing one
`acceptance.json`, retained for 30 days. Readiness compares provider repository,
workflow, fixture commit, current attempt and success with the JSON and candidate
SHA. Expired/missing artifacts, another SHA, partial suites and failed runs fail.
Preserve run IDs. Before a new collection, rerun complete acceptance when original
evidence expires. Distribution evidence has a separate 7-day artifact lifetime;
native Homebrew and final acceptance artifacts retain 30 days. The
official publication workflows preserve original ZIPs in an immutable approval
asset, so already-archived approvals survive later Actions expiry. See
[archive verification and recovery](https://github.com/releaseway/actions/blob/main/docs/release-evidence.md).

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

For actions releases, also supply the official release dispatch input
`distribution-run` (checker flag `--distribution-run`). Run distribution acceptance
at the same full actions candidate SHA with `pages=true`: the gate requires native
Linux/macOS/Windows receipts and latest/release/artifact Pages receipts, plus the
separate release-set aggregate and both documentation deployments from that same
attempt. The latest exact-candidate distribution push CI must also pass. A
public-only run or notes suite alone is insufficient. Pin every reusable Pages
workflow reference and `AUTOMATION_SHA` to the candidate before running the fixture.
Follow the [distribution campaign guide](distribution-fixtures/README.md) for
fresh dataset prefixes and original provider-artifact checks.

## App-free source-tag acceptance

`app-free-acceptance.yml` accepts a full `action-ref` candidate SHA. It prepares rc
and stable on the same original fixture commit, builds deterministic version and
platform assets, publishes both immutable Releases, and checks missing-tag resolve
without writes. The isolated `app-free-v` namespace preserves existing fixture tags.
For the complete readiness gate, enable both `homebrew` and `pages`: the existing
tap deploy key publishes only `release-fixture-app-free`, and the existing Pages
workflow verifies the served stable version. This updates the dedicated fixture
site; it is not a product deployment. These modes require the existing tap secret,
Homebrew access and configured isolated Pages environment.

After stable exists, automatic rc planning deliberately closes. To reconcile that
same source, supply both `rc-tag` and `stable-tag`; the workflow resolves their exact
source bindings instead of searching tags or changing versions. Deterministic
assets let an existing immutable Release be verified again.

Final evidence is `app-free-acceptance-<run_attempt>` and binds candidate SHA,
fixture source, workflow/run/attempt, annotated tag objects, same-core versions,
public assets, tap commit and actual Pages deployment/served digest. It is useful
only after a real successful run. The local fixture tests do not establish public
release, tap or Pages readiness.
