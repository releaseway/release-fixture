#!/usr/bin/env bash
set -euo pipefail

[ "${GITHUB_ACTIONS:-}" = true ] && [ "${RUNNER_ENVIRONMENT:-}" = github-hosted ] || {
  echo "Feature installation consumers require an isolated GitHub-hosted runner" >&2; exit 1;
}
: "${PLATFORM:?}" "${VERSION:?}" "${TAP_ZERO:?}" "${TAP_ONE:?}" "${TAP_FINAL:?}"
: "${SOURCE_COMMIT:?}" "${SPEC_COMMIT:?}" "${AUTOMATION_REF:?}"
[ "$SOURCE_COMMIT" = "$GITHUB_SHA" ] || { echo "Consumer source differs from caller" >&2; exit 1; }
[ "$VERSION" = "1.$GITHUB_RUN_ID.$GITHUB_RUN_ATTEMPT" ] || { echo "Rerun all acceptance jobs for a fresh attempt" >&2; exit 1; }
for commit in "$TAP_ZERO" "$TAP_ONE" "$TAP_FINAL" "$SOURCE_COMMIT" "$SPEC_COMMIT" "$AUTOMATION_REF"; do
  [[ "$commit" =~ ^[a-f0-9]{40}$ ]] || { echo "Expected immutable fixture SHA" >&2; exit 1; }
done

export HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_CLEANUP=1
scratch="$(mktemp -d)"
validation_tap="releaseway/feature-upgrade-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
validation_checkout="$(brew --repository)/Library/Taps/releaseway/homebrew-feature-upgrade-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
tap_source="$PWD/tap"
originals=()
cleanup() {
  status="$?"
  set +e
  restore_failed=false
  for ((index=0; index<${#originals[@]}; index++)); do
    original="${originals[$index]}"
    backup="$scratch/taps/$index"
    [ -e "$backup" ] || [ -L "$backup" ] || continue
    if [ -e "$original" ] || [ -L "$original" ] || ! mv "$backup" "$original"; then
      restore_failed=true
    fi
  done
  if [ "$restore_failed" = true ]; then
    echo "Consumer tap backups retained for recovery at $scratch" >&2
    exit 1
  fi
  brew untap --force "$validation_tap" >/dev/null 2>&1
  brew untrust --tap "$tap_source" >/dev/null 2>&1
  rm -rf "$scratch"
  exit "$status"
}
trap cleanup EXIT

# Go is the only source build dependency and comes from core. Preserve other
# hosted-image taps without evaluating their unrelated, sometimes stale Formulae.
installed_taps="$(brew tap)"
mkdir -p "$scratch/taps"
while IFS= read -r tap; do
  [ -n "$tap" ] || continue
  case "$tap" in homebrew/*) continue ;; esac
  original="$(brew --repository "$tap")"
  index="${#originals[@]}"
  originals+=("$original")
  mv "$original" "$scratch/taps/$index"
done <<< "$installed_taps"

[ ! -e "$validation_checkout" ] || { echo "Unexpected existing consumer tap" >&2; exit 1; }
brew trust --tap "$tap_source"
mkdir -p "$(dirname "$validation_checkout")"
git clone --quiet --template= "$tap_source" "$validation_checkout"
qualified="$validation_tap/releaseway-source-platform-fixture"
formula_path="$validation_checkout/Formula/releaseway-source-platform-fixture.rb"
digest() { ruby -rdigest -e 'puts Digest::SHA256.file(ARGV.fetch(0)).hexdigest' "$formula_path"; }
package_version() { ruby -e 'puts File.basename(File.realpath(ARGV.fetch(0)))' "$(brew --prefix "$qualified")"; }

git -C "$validation_checkout" checkout --quiet --detach "$TAP_ZERO"
zero_sha="$(digest)"
brew install --build-from-source "$qualified"
brew test "$qualified"
initial_package="$(package_version)"
[ "$initial_package" = "$VERSION" ]
[ "$(digest)" = "$zero_sha" ]

git -C "$validation_checkout" checkout --quiet --detach "$TAP_ONE"
one_sha="$(digest)"
[ "$zero_sha" != "$one_sha" ]
brew upgrade "$qualified"
brew test "$qualified"
updated_package="$(package_version)"
[ "$updated_package" = "${VERSION}_1" ]
[ "$(digest)" = "$one_sha" ]
prefix="$(brew --prefix "$qualified")"
native_output="$("$prefix/bin/releaseway-native-fixture" --version)"
case "$PLATFORM" in
  macos-arm64) expected_target=darwin/arm64; unsupported=releaseway-prebuilt-linux-fixture; required=Linux ;;
  macos-x86_64) expected_target=darwin/amd64; unsupported=releaseway-prebuilt-macos-fixture; required=arm64 ;;
  linux-arm64) expected_target=linux/arm64; unsupported=releaseway-prebuilt-linux-fixture; required=x86_64 ;;
  linux-x86_64) expected_target=linux/amd64; unsupported=releaseway-prebuilt-macos-fixture; required=macOS ;;
  *) echo "Unexpected consumer platform" >&2; exit 1 ;;
esac
[[ "$native_output" == "releaseway-native-fixture $VERSION $expected_target "* ]]

git -C "$validation_checkout" checkout --quiet --detach "$TAP_FINAL"
bad_qualified="$validation_tap/$unsupported"
[ -z "$(brew list --versions "$bad_qualified" 2>/dev/null || true)" ]
if brew install --build-from-source "$bad_qualified" >"$scratch/unsupported.log" 2>&1; then
  echo "Unsupported platform installed successfully" >&2
  exit 1
fi
REQUIRED="$required" ruby -e '
  text = File.read(ARGV.fetch(0))
  abort "Unsupported install failed for an unrelated reason: #{text}" unless text.match?(/requir(?:ed|es)/i) && text.match?(/#{Regexp.escape(ENV.fetch("REQUIRED"))}/i)
' "$scratch/unsupported.log"
[ -z "$(brew list --versions "$bad_qualified" 2>/dev/null || true)" ]

export INITIAL_PACKAGE="$initial_package" UPDATED_PACKAGE="$updated_package" ZERO_SHA="$zero_sha" ONE_SHA="$one_sha"
export NATIVE_OUTPUT="$native_output" UNSUPPORTED_FORMULA="$unsupported" REQUIRED="$required"
python3 - <<'PY'
import json, os
from pathlib import Path
e = os.environ
record = dict(schema=1, kind='homebrew-feature-consumer', platform=e['PLATFORM'], candidate_sha=e['AUTOMATION_REF'],
              source_commit=e['SOURCE_COMMIT'], spec_commit=e['SPEC_COMMIT'], fixture_commit=e['GITHUB_SHA'],
              run_id=int(e['GITHUB_RUN_ID']), run_attempt=int(e['GITHUB_RUN_ATTEMPT']), version=e['VERSION'],
              tap_zero=e['TAP_ZERO'], tap_one=e['TAP_ONE'], tap_final=e['TAP_FINAL'],
              zero_formula_sha256=e['ZERO_SHA'], one_formula_sha256=e['ONE_SHA'],
              initial_package=e['INITIAL_PACKAGE'], updated_package=e['UPDATED_PACKAGE'], native_output=e['NATIVE_OUTPUT'],
              unsupported_formula=e['UNSUPPORTED_FORMULA'], unsupported_requirement=e['REQUIRED'], unsupported_rejected=True)
Path('consumer.json').write_text(json.dumps(record, sort_keys=True, indent=2) + '\n')
PY
