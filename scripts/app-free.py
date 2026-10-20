"""App-free candidate fixture: deterministic assets and narrowly scoped evidence."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import urllib.request


def require(value, message):
    if not value:
        raise ValueError(message)


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def build(version, destination, native=False):
    require(re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-rc\.(?:0|[1-9][0-9]*))?', version), 'invalid fixture version')
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    (root / 'version.txt').write_text(version + '\n')
    if native:
        data = ('#!/bin/sh\nset -eu\ncase "${1:-}" in\n --version) printf \'%s\\n\' \'' + version + '\' ;;\n --probe) printf \'%s\\n\' npm-actions-native-fixture-ok ;;\n *) exit 64 ;;\nesac\n').encode()
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as archive:
            info = tarfile.TarInfo('bin/npm-actions-native-fixture')
            info.mode = 0o755
            info.size = len(data)
            info.mtime = 0
            archive.addfile(info, io.BytesIO(data))
        compressed = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed, mode='wb', filename='', mtime=0) as gz:
            gz.write(stream.getvalue())
        (root / 'npm-actions-native-fixture_linux_x64.tar.gz').write_bytes(compressed.getvalue())


def package():
    require(os.environ['GITHUB_REPOSITORY'] == 'releaseway/npm-actions-fixture', 'fixture repository mismatch')
    path = Path('package.json')
    manifest = json.loads(path.read_text())
    require(manifest.get('name') == '@releaseway/npm-actions-fixture', 'fixture package identity mismatch')
    manifest['bin'] = {'npm-actions-native-fixture': 'bin/npm-actions-native-fixture'}
    path.write_text(json.dumps(manifest, indent=2) + '\n')
    Path('.github/npm/packages.yml').write_text('''version:
  source: git-tag
  prefix: app-free-v
publish:
  mode: direct
  channels:
    stable: app-free-stable
    prerelease: app-free-rc
packages:
  "@releaseway/npm-actions-fixture":
    distribution:
      type: github-release
      tag: "app-free-v{version}"
      targets:
        linux-x64-gnu:
          asset: npm-actions-native-fixture_linux_x64.tar.gz
          executable: bin/npm-actions-native-fixture
''')


def validate():
    require(os.environ.get('GITHUB_REPOSITORY') in ('releaseway/release-fixture', 'releaseway/npm-actions-fixture'), 'fixture repository mismatch')
    for key in ['ACTIONS_REF', 'NPM_REF']:
        value = os.environ.get(key, '')
        if key == 'NPM_REF' and not value:
            continue
        require(re.fullmatch(r'[0-9a-f]{40}', value) and value != '0' * 40, key + ' must be a real full candidate SHA')
    require(bool(os.environ.get('RC_TAG')) == bool(os.environ.get('STABLE_TAG')), 'supply both existing tags or neither')


def collect(kind):
    require(kind in ('git', 'npm'), 'invalid evidence scenario')
    candidates = {'actions': os.environ['ACTIONS_REF']}
    if kind == 'npm':
        candidates['npm'] = os.environ['NPM_REF']
    require(git('-C', 'release-action', 'rev-parse', 'HEAD') == candidates['actions'], 'actions checkout mismatch')
    if kind == 'npm':
        require(git('-C', 'npm-action', 'rev-parse', 'HEAD') == candidates['npm'], 'npm checkout mismatch')
    source = os.environ['GITHUB_SHA']
    channels = {}
    for channel in ['RC', 'STABLE']:
        tag, version = os.environ[channel + '_TAG'], os.environ[channel + '_VERSION']
        require(tag == 'app-free-v' + version, 'tag/version mismatch')
        remote = subprocess.check_output(['git', 'ls-remote', 'origin', 'refs/tags/' + tag, 'refs/tags/' + tag + '^{}'], text=True)
        refs = dict((ref, sha) for sha, ref in (line.split() for line in remote.splitlines()))
        require(refs.get('refs/tags/' + tag + '^{}') == source, 'annotated tag must peel to fixture source')
        url = f'https://github.com/{os.environ["GITHUB_REPOSITORY"]}/releases/download/{tag}/version.txt'
        with urllib.request.urlopen(url, timeout=60) as response:
            data = response.read(4096)
        require(data == (version + '\n').encode(), 'public asset version differs')
        result = {'tag': tag, 'version': version, 'commit': source, 'asset_sha256': hashlib.sha256(data).hexdigest(), 'tag_object': refs['refs/tags/' + tag]}
        if kind == 'npm':
            packages = json.loads(os.environ[channel + '_PACKAGES'])
            require(packages == [{'name': '@releaseway/npm-actions-fixture', 'version': version, 'state': 'published'}], 'readiness requires fresh verified publication, not historical existence/stage')
            report = json.loads(Path(os.environ[channel + '_REPORT']).read_text())
            require(report['status'] == 'success' and report['source']['commit'] == source and len(report['plan']) == 1, 'npm report identity mismatch')
            require(report['plan'][0]['mode'] == 'direct', 'must be direct publication')
            result['integrity'] = report['plan'][0]['integrity']
            require(re.fullmatch(r'sha512-[A-Za-z0-9+/]{86}==', result['integrity']), 'invalid planned SHA512')
        channels[channel.lower()] = result
    require(channels['rc']['version'] == channels['stable']['version'] + '-rc.0' or channels['rc']['version'].split('-')[0] == channels['stable']['version'], 'rc and stable core differ')
    if kind == 'git':
        missing = f'app-free-missing-v0.0.0-rc.{os.environ["GITHUB_RUN_ID"]}'
        require(not subprocess.check_output(['git', 'ls-remote', 'origin', 'refs/tags/' + missing], text=True).strip(), 'missing resolve created a tag')
        diagnostic = json.loads(Path(os.environ['MISSING_DIAGNOSTICS']).read_text())
        require(diagnostic['error']['code'] == 'TAG_NOT_FOUND' and diagnostic['error']['remoteState'] == 'unchanged', 'missing resolve was not read-only')
    branch = subprocess.check_output(['git', 'ls-remote', 'origin', 'refs/heads/main'], text=True).split()[0]
    require(branch == source, 'source branch moved during acceptance')
    evidence = {'branch_commit': branch, 'schema': 1, 'scenario': 'app-free-' + kind, 'candidates': candidates, 'fixture_repository': os.environ['GITHUB_REPOSITORY'], 'fixture_commit': source, 'run_id': int(os.environ['GITHUB_RUN_ID']), 'run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT']), 'workflow': 'app-free-acceptance.yml' if kind == 'git' else 'direct.yml', 'channels': channels}
    if kind == 'npm':
        evidence['installed_node_versions'] = ['22', '24', '26']
    Path('app-free-acceptance.json').write_text(json.dumps(evidence, indent=2) + '\n')



def delivery():
    path = Path('app-free-acceptance.json')
    evidence = json.loads(path.read_text())
    evidence['homebrew'] = None
    evidence['pages'] = None
    if os.environ['HOMEBREW'] == 'success':
        commit = subprocess.check_output(['gh', 'api', 'repos/releaseway/homebrew-tap-fixture/commits/main', '--jq', '.sha'], text=True).strip()
        require(re.fullmatch(r'[0-9a-f]{40}', commit), 'invalid tap commit')
        formula = subprocess.check_output(['gh', 'api', f'repos/releaseway/homebrew-tap-fixture/contents/Formula/release-fixture-app-free.rb?ref={commit}', '-H', 'Accept: application/vnd.github.raw+json'], text=True)
        require('# releaseway-source-commit: ' + evidence['fixture_commit'] in formula, 'tap source mismatch')
        require('# releaseway-version: ' + evidence['channels']['stable']['version'] in formula, 'tap version mismatch')
        require(os.environ['TAP_FORMULA'] == 'release-fixture-app-free' and os.environ['TAP_VERSION'] == evidence['channels']['stable']['version'], 'tap outputs mismatch')
        evidence['homebrew'] = {'repository': 'releaseway/homebrew-tap-fixture', 'commit': commit, 'formula': 'release-fixture-app-free'}
    if os.environ['PAGES'] == 'success':
        url = os.environ['PAGE_URL']
        require(url.startswith('https://releaseway.github.io/'), 'unexpected fixture Pages host')
        with urllib.request.urlopen(url.rstrip('/') + '/version.txt', timeout=60) as response:
            data = response.read(4096)
        require(hashlib.sha256(data).hexdigest() == evidence['channels']['stable']['asset_sha256'], 'Pages served version differs from Release')
        require(re.fullmatch(r'[0-9a-f]{64}', os.environ['CONTENT_DIGEST']), 'invalid Pages content digest')
        evidence['pages'] = {'url': url, 'deployment_id': int(os.environ['DEPLOYMENT_ID']), 'content_digest': os.environ['CONTENT_DIGEST'], 'served_sha256': hashlib.sha256(data).hexdigest()}
    path.write_text(json.dumps(evidence, indent=2) + '\n')

if __name__ == '__main__':
    command = sys.argv[1]
    if command == 'validate': validate()
    elif command == 'build': build(sys.argv[2], sys.argv[3], len(sys.argv) > 4 and sys.argv[4] == 'native')
    elif command == 'package': package()
    elif command == 'collect': collect(sys.argv[2])
    elif command == 'delivery': delivery()
    else: raise ValueError('unknown fixture command')
