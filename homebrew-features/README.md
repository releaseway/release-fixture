# Homebrew revision and platform acceptance

Use this campaign to approve a homebrew-actions candidate. It operates
only on `releaseway/homebrew-tap-fixture`, using `HOMEBREW_TAP_DEPLOY_KEY`. It creates
isolated `homebrew-features-*` immutable prereleases with `latest=false` and
`homebrew-feature-spec-*` branches. Consumers and the final collector have no tap
write credential. Keep other campaigns that write this tap idle while it runs:
the negative cases compare the entire tap head before and after each rejection.

## Pin and run the candidate

With Python 3, Git, Ruby and Go meeting
[`native-fixture/go.mod`](../native-fixture/go.mod), update all literal refs and
both dispatch defaults from this fixture checkout:

```sh
python3 scripts/pin-homebrew-candidate.py "$CANDIDATE_SHA"
AUTOMATION_REF="$CANDIDATE_SHA" python3 scripts/verify-homebrew-candidate.py
python3 test/candidates.py
python3 test/homebrew-features.py
```

`CANDIDATE_SHA` must be a reviewed full 40-character commit. Review 15 reusable refs
(4 legacy, 2 PR, 8 feature, 1 negative) and 2 defaults. Commit and push them, then
wait for fixture CI and GitHub workflow registration. A pin mismatch stops before
tap writes. Dispatch the feature workflow from that fixture main commit:

```sh
gh workflow run homebrew-features-acceptance.yml \
  --repo releaseway/release-fixture --ref main \
  -f automation-ref="$CANDIDATE_SHA"
```

It fixes source A to the caller SHA, builds real Go ELF/Mach-O binaries for
four targets, and publishes deterministic archives. A separate Git index creates
B, a direct child of A changing only the source spec's `revision: 0` to `1`.
The caller checkout/index and upstream program stay intact. Version is
`1.<run_id>.<attempt>`; rerun **all jobs** for a fresh attempt. Downloading older
attempt receipts cannot satisfy the current attempt.

After the feature run finishes, prepare a new normal fixture release through the
existing `release.yml` workflow. Run `homebrew-acceptance.yml` from that immutable
fixture tag, with both `tag` and matching `automation-ref`. The official
Homebrew gate requires both successful run IDs at the same candidate SHA. The two
campaigns may use different fixture commits; each is checked against its own run.

## Required results

The source campaign publishes r0, snapshots tap T0, publishes r1 from A/spec B,
snapshots T1, and repeats r1 with unchanged Formula bytes. Each of four native
consumer jobs installs T0 then upgrades the same installed keg using T1, asserting
package version `<upstream>_1` and executable OS/architecture. The final tap snapshot
also supplies unsupported-host installation cases.

Prebuilt campaigns exercise Linux x86_64 only, macOS arm64 only, and asymmetric
macOS arm64 + Linux x86_64. Their real compiled binaries receive native tests.
Separate child workflows must fail at the specified revision-decrease,
source-replacement or missing-asset rejection, leaving the tap unchanged. The
controller rejects unrelated failures and also exercises the production missing
receipt and actual native architecture guards.

The final `releaseway-acceptance-<attempt>` artifact contains one `acceptance.json`
(schema 2, scenario `homebrew-revision-platforms`) and is retained for 30 days.
It records 21 required cases, four upgrade consumers, five rejection proofs and
six original native aggregate ZIPs with their provider metadata/digests: source
r0/r1/rerun plus the three prebuilt invocations, totaling 16 native receipts.
There is no approval artifact when required jobs fail or skip. Native invocation
and individual receipt artifacts also retain 30 days.

The automation's release gate independently verifies the complete contract and
compares embedded ZIPs to the provider's original bytes. The durable release
bundle preserves both acceptance ZIPs and all six native ZIPs for offline replay.
See [archive verification](https://github.com/releaseway/actions/blob/main/docs/release-evidence.md).

Initial complete feature run [39543238690](https://github.com/releaseway/release-fixture/actions/runs/39543238690)
and legacy run [39545069610](https://github.com/releaseway/release-fixture/actions/runs/39545069610)
passed candidate `150c151323dd3d979d0b62d2804b9c0b22c8a3aa`. These are historical
candidate results; a later candidate needs its own successful runs and exact-SHA CI.
