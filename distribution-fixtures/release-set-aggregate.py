"""Merge separately transported receipts after both observed Pages deployments."""
import json
import os
from pathlib import Path
import runpy

api = runpy.run_path('scripts/verify-release-set-receipts.py')
policy = json.loads(Path('.github/distribution/release-set-final.json').read_text())
receipt = dict(schema=1, kind='release-set', candidate=os.environ['AUTOMATION_SHA'],
               sourceCommit=os.environ['GITHUB_SHA'], runId=os.environ['GITHUB_RUN_ID'],
               attempt=os.environ['GITHUB_RUN_ATTEMPT'], prefix=policy['releases']['tag-prefix'],
               cases=sorted(api['CASES']),
               core=[json.loads(p.read_text()) for p in Path('release-set-core').rglob('receipt.json')],
               pages=[json.loads(p.read_text()) for p in Path('release-set-pages').rglob('receipt.json')])
api['verify_receipt'](receipt['candidate'], receipt['sourceCommit'], receipt['runId'], receipt['attempt'], receipt)
Path('release-set-acceptance').mkdir(exist_ok=True)
Path('release-set-acceptance/acceptance.json').write_text(json.dumps(receipt, indent=2) + '\n')
