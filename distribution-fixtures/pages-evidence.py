"""Collect reports by exact artifact ID after successful reusable workflow jobs."""
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile

needs = json.loads(os.environ['NEEDS_JSON'])
for mode in ['latest', 'release', 'artifact']:
    outputs = needs['pages-' + mode]['outputs']
    artifact_id = outputs['report-artifact-id']
    if not artifact_id.isdecimal():
        raise ValueError('expected an immutable report artifact ID')
    archive = subprocess.check_output(['gh', 'api', '--hostname', 'github.com', f'repos/{os.environ["GITHUB_REPOSITORY"]}/actions/artifacts/{artifact_id}/zip'])
    if len(archive) > 32 * 1024**2:
        raise ValueError('report archive too large')
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        if z.namelist() != ['report.json'] or z.getinfo('report.json').file_size > 32 * 1024**2:
            raise ValueError('unexpected report artifact members')
        report = json.loads(z.read('report.json'))
    receipt = dict(schema=1, kind='pages', mode=mode, candidate=os.environ['AUTOMATION_SHA'],
                   sourceCommit=os.environ['GITHUB_SHA'], runId=os.environ['GITHUB_RUN_ID'],
                   attempt=os.environ['GITHUB_RUN_ATTEMPT'], report=report, served=True,
                   deploymentId=outputs['deployment-id'], pageUrl=outputs['page-url'],
                   reportArtifactId=artifact_id, deliveryDigest=outputs['delivery-digest'],
                   sourceArtifactId=os.environ['SOURCE_ARTIFACT_ID'] if mode == 'artifact' else '')
    folder = Path('evidence') / ('pages-' + mode)
    folder.mkdir(parents=True)
    (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
