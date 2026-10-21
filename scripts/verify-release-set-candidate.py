"""Check the candidate pin and the separate release-set aggregate receipt."""
import argparse
import json
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parent
verify_pin = runpy.run_path(str(ROOT / 'verify-distribution-candidate.py'))['verify_pin']
verify_receipt = runpy.run_path(str(ROOT / 'verify-release-set-receipts.py'))['verify_receipt']

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('candidate', 'source', 'run-id', 'attempt', 'receipt'):
        p.add_argument('--' + name, required=True)
    args = p.parse_args()
    verify_pin(args.candidate, Path('.github/workflows/distribution-acceptance.yml').read_text())
    verify_receipt(args.candidate, args.source, args.run_id, args.attempt, json.loads(Path(args.receipt).read_text()))
    print('complete current release-set acceptance verified')
