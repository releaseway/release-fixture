"""Collect the exact report artifact and independently observe every served file."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile

env = os.environ
phase = env['RELEASE_SET_PHASE']
assert phase in ('initial', 'final')
outputs = json.loads(env['PAGES_OUTPUTS'])
artifact_id = outputs['report-artifact-id']
assert artifact_id.isdecimal() and int(artifact_id) > 0
endpoint = f'repos/{env["GITHUB_REPOSITORY"]}/actions/artifacts/{artifact_id}'
def api(path):
    return subprocess.check_output(['gh', 'api', '--hostname', 'github.com', path])
metadata = json.loads(api(endpoint))
assert metadata['id'] == int(artifact_id) and not metadata['expired']
assert metadata['workflow_run']['id'] == int(env['GITHUB_RUN_ID'])
assert metadata['workflow_run']['head_sha'] == env['GITHUB_SHA']
archive = api(endpoint + '/zip')
assert len(archive) <= 1024**2
assert metadata['digest'] == 'sha256:' + hashlib.sha256(archive).hexdigest()
with zipfile.ZipFile(io.BytesIO(archive)) as z:
    assert z.namelist() == ['report.json'] and z.getinfo('report.json').file_size <= 100 * 1024
    raw = z.read('report.json')
report = json.loads(raw)
folder = Path('release-set-pages') / phase
folder.mkdir(parents=True, exist_ok=True)
report_path = folder / 'report.json'
report_path.write_bytes(raw)
subprocess.run(['node', 'distribution-fixtures/release-set-served.mjs', str(report_path)],
               env=dict(env, PAGE_URL=outputs['page-url']), check=True)
site_id = env['SITE_ARTIFACT_ID']
site = json.loads(api(f'repos/{env["GITHUB_REPOSITORY"]}/actions/artifacts/{site_id}'))
assert site['id'] == int(site_id) and not site['expired']
assert site['workflow_run']['id'] == int(env['GITHUB_RUN_ID'])
assert site['workflow_run']['head_sha'] == env['GITHUB_SHA']
receipt = dict(schema=1, kind='release-set-pages', phase=phase, candidate=env['AUTOMATION_SHA'],
               sourceCommit=env['GITHUB_SHA'], runId=env['GITHUB_RUN_ID'], attempt=env['GITHUB_RUN_ATTEMPT'],
               report=report, reportSha='sha256:' + hashlib.sha256(raw).hexdigest(),
               reportArtifactId=artifact_id, reportArtifactDigest=metadata['digest'],
               siteArtifactId=site_id, siteArtifactDigest=site['digest'],
               served=True, deploymentId=outputs['deployment-id'], pageUrl=outputs['page-url'],
               deliveryDigest=outputs['delivery-digest'])
(folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
