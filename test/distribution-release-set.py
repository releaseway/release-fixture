"""Exercise the separate receipt contract, including hostile nested identities."""
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
api = runpy.run_path(str(ROOT / 'scripts/verify-release-set-receipts.py'))
CANDIDATE, SOURCE, RUN, ATTEMPT = 'a' * 40, 'b' * 40, '20', '1'
PREFIX = json.loads((ROOT / '.github/distribution/release-set-initial.json').read_text())['releases']['tag-prefix']


def hash_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def identity():
    return dict(candidate=CANDIDATE, sourceCommit=SOURCE, runId=RUN, attempt=ATTEMPT)


def report(phase, pages=False):
    # Report policy is canonical; user syntax must not become its expected shape.
    policy = api['expected_policy'](PREFIX, phase)
    files, releases = [], []
    versions = ['0.9.0', '1.0.0', '1.1.0', '1.3.0-beta.1'] + (['1.2.0'] if phase == 'final' else [])
    for index, v in enumerate(versions):
        r = dict(releaseId=100 + index, tag=PREFIX + v, commit=SOURCE, prerelease=True,
                 immutable=True, status='skipped-empty' if v == '0.9.0' else 'selected', assets=[])
        releases.append(r)
        if v == '0.9.0':
            continue
        data = [f"#!/bin/sh\nprintf '%s\\n' 'release-set:{v}'\n",
                f"Write-Output 'release-set:{v}'\n", f'{{"version":"{v}"}}\n']
        for j, (mapping, text) in enumerate(zip(policy['files'], data)):
            raw = text.encode(); aid = 1000 + index * 3 + j
            r['assets'].append(dict(id=aid, name=mapping['from'], size=len(raw), digest='sha256:' + hash_bytes(raw), state='uploaded'))
            f = dict(path=r['tag'] + '/' + mapping['to'], size=len(raw), sha256=hash_bytes(raw),
                     origin='selected', releaseId=r['releaseId'], assetId=aid, **{'from': mapping['from']})
            files.append(f)
            if r['tag'] == policy['aliases']['tag'] and j < 2:
                files.append(dict(f, path=mapping['to'], aliasOf=f['path']))
    for path, text in [('index.html', f'<!doctype html><title>Release set {phase}</title>\n'),
                       ('.well-known/release-set.json', f'{{"phase":"{phase}"}}\n')]:
        files.append(dict(path=path, size=len(text.encode()), sha256=hash_bytes(text.encode()), origin='base'))
    def digest():
        entries = sorted([[f['path'], f['size'], f['sha256']] for f in files])
        return 'sha256:' + hash_bytes(json.dumps(entries, separators=(',', ':')).encode())
    src = dict(kind='github-release-set', repository='releaseway/release-fixture', verification='digest',
               policy=policy, policyDigest='sha256:' + hash_bytes(json.dumps(policy, separators=(',', ':')).encode()),
               destination='', releases=releases, aliasTag=policy['aliases']['tag'])
    result = dict(schema=2, base=True, baseline={'kind': 'local-site'}, files=files, source=src)
    if pages:
        result['contentDigest'] = digest()
        result['baseline'] = dict(kind='workflow-artifact', repository='releaseway/release-fixture',
                                  artifactId='300' if phase == 'initial' else '301', artifactDigest='sha256:' + ('c' if phase == 'initial' else 'd') * 64,
                                  runId=RUN, callerSha=SOURCE, headSha=SOURCE)
        files.append(dict(path='.nojekyll', size=0, sha256=hash_bytes(b''), origin='selected', generatedBy='pages'))
    result['digest'] = digest()
    return result


def receipt():
    core = []
    for platform in ('Linux', 'macOS', 'Windows'):
        r = report('initial')
        core.append(dict(identity(), schema=1, kind='release-set-core', platform=platform, report=r,
                         rerunDigest=r['digest'], nativeMarker='release-set:1.1.0', cases=sorted(api['CORE_CASES'])))
    pages = []
    for i, phase in enumerate(('initial', 'final')):
        r = report(phase, pages=True)
        pages.append(dict(identity(), schema=1, kind='release-set-pages', phase=phase, report=r,
                          reportSha='sha256:' + 'e' * 64, reportArtifactId=str(400 + i),
                          reportArtifactDigest='sha256:' + 'f' * 64, siteArtifactId=r['baseline']['artifactId'],
                          siteArtifactDigest=r['baseline']['artifactDigest'], served=True,
                          deploymentId=str(500 + i), pageUrl='https://releaseway.github.io/release-fixture/', deliveryDigest=r['digest']))
    return dict(identity(), schema=1, kind='release-set', prefix=PREFIX, cases=sorted(api['CASES']), core=core, pages=pages)


class ReleaseSetTests(unittest.TestCase):
    def verify(self, value):
        api['verify_receipt'](CANDIDATE, SOURCE, RUN, ATTEMPT, value)

    def test_complete_three_os_two_deployments(self):
        self.verify(receipt())

    def test_rejects_missing_duplicate_unknown_and_stale_receipts(self):
        for mutate in [lambda r: r['cases'].pop(), lambda r: r['cases'].append('unknown'),
                       lambda r: r['cases'].append(r['cases'][0]), lambda r: r['core'].pop(),
                       lambda r: r['core'][0].update(platform='Windows'), lambda r: r['pages'].pop(),
                       lambda r: r['core'][0].update(candidate='c' * 40), lambda r: r.update(sourceCommit='c' * 40),
                       lambda r: r['pages'][0].update(runId='19'), lambda r: r['pages'][1].update(attempt='2')]:
            bad = receipt(); mutate(bad)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.verify(bad)

    def test_rejects_nested_provenance_and_byte_tampering(self):
        mutations = [lambda r: r['pages'][0].update(deploymentId=True),
                     lambda r: r['pages'][1].update(reportArtifactId=r['pages'][0]['reportArtifactId']),
                     lambda r: r['pages'][0].update(served=False),
                     lambda r: r['pages'][0].update(siteArtifactDigest='sha256:' + '0' * 64),
                     lambda r: r['pages'][0]['report']['baseline'].update(headSha='d' * 40),
                     lambda r: r['pages'][1]['report']['source']['releases'][0].update(status='selected'),
                     lambda r: r['core'][0]['report']['source']['releases'][1]['assets'][0].update(id=True),
                     lambda r: r['core'][0]['report']['source'].update(aliasTag=PREFIX + '1.0.0'),
                     lambda r: r['core'][0]['report']['source']['policy']['releases'].update(range='*'),
                     lambda r: r['core'][0]['report']['files'][0].update(sha256='0' * 64),
                     lambda r: r['core'][0].update(rerunDigest='sha256:' + '0' * 64)]
        for mutate in mutations:
            bad = receipt(); mutate(bad)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.verify(bad)

    def test_generator_matches_independent_fixture_bytes(self):
        helper = ROOT / 'distribution-fixtures/release-set-fixtures.mjs'
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory); (tmp / '.github/distribution').mkdir(parents=True)
            for phase in ('initial', 'final'):
                config = ROOT / f'.github/distribution/release-set-{phase}.json'
                (tmp / '.github/distribution' / config.name).write_bytes(config.read_bytes())
                subprocess.run(['node', str(helper), 'build', phase], cwd=tmp, check=True)
            self.assertEqual((tmp / 'release-set-payload/1.1.0/bootstrap.sh').read_text(), "#!/bin/sh\nprintf '%s\\n' 'release-set:1.1.0'\n")
            self.assertEqual(list((tmp / 'release-set-payload/0.9.0').iterdir()), [])
            self.assertEqual([p.name for p in (tmp / 'release-set-payload/partial-v1.0.0').iterdir()], ['bootstrap.sh'])
            self.assertNotEqual((tmp / 'release-set-site-initial/index.html').read_bytes(), (tmp / 'release-set-site-final/index.html').read_bytes())

    def test_workflow_preserves_old_evidence_before_advancing(self):
        text = (ROOT / '.github/workflows/distribution-acceptance.yml').read_text()
        self.assertIn('needs: [publish, evidence]', text)
        self.assertIn('name: distribution-evidence-${{ github.run_id }}-${{ github.run_attempt }}', text)
        self.assertIn('name: release-set-evidence-${{ github.run_id }}-${{ github.run_attempt }}', text)
        self.assertLess(text.index('run: python3 distribution-fixtures/release-set-pages-evidence.py'), text.index('run: node distribution-fixtures/release-set-fixtures.mjs publish final'))
        self.assertIn('contents: read\n    steps:', text[text.index('  public-source:'):text.index('  pages-preflight:')])

    def test_source_change_probe_preserves_full_page_contract(self):
        helper = (ROOT / 'distribution-fixtures/release-set-fixtures.mjs').as_uri()
        code = f"""
          import assert from 'node:assert/strict';
          import {{supersedingInventory}} from {json.dumps(helper)};
          const page=Array.from({{length:100}},(_,i)=>({{id:i+1,tag_name:'old-'+i}}));
          const changed=supersedingInventory(page,'fixture-v');
          assert.equal(changed.length,100);
          assert.equal(new Set(changed.map(r=>r.id)).size,100);
          assert.ok(changed.some(r=>r.tag_name==='fixture-v1.1.1'));
          assert.equal(page[0].tag_name,'old-0');
        """
        subprocess.run(['node', '--input-type=module', '-e', code], check=True)


if __name__ == '__main__':
    unittest.main()
