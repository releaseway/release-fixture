"""Require all literal candidate refs to agree before any fixture tap writes."""
import os
from pathlib import Path
import re
import json
import subprocess


def verify(sha, text, check_text=None, feature_text=None, negative_text=None):
    if not re.fullmatch(r'[0-9a-fA-F]{40}', sha):
        raise ValueError('automation-ref must be a full 40-character commit SHA')
    for selected in [text, check_text, feature_text, negative_text]:
        if selected is None:
            continue
        parsed = subprocess.run(['ruby', '-ryaml', '-rjson', '-e',
            'puts JSON.generate(YAML.safe_load(STDIN.read, aliases: true))'], input=selected,
            text=True, capture_output=True)
        try:
            model = json.loads(parsed.stdout)
            jobs = model['jobs']
            references = [job.get('uses', '') for job in jobs.values()]
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise ValueError('invalid candidate workflow') from error
        pins = [ref for ref in references if ref.startswith('releaseway/homebrew-actions/')]
        if not pins or any(not re.fullmatch(r'releaseway/homebrew-actions/\.github/workflows/(?:check|publish)\.yml@' + sha.lower(), pin.lower()) for pin in pins):
            raise ValueError('automation-ref must match every executed reusable-workflow pin')


if __name__ == '__main__':
    reference = os.environ.get('GITHUB_WORKFLOW_REF', '')
    name = reference.split('@', 1)[0].rsplit('/', 1)[-1] if reference else 'homebrew-acceptance.yml'
    if name not in ('homebrew-acceptance.yml', 'homebrew-features-acceptance.yml', 'homebrew-features-negative.yml'):
        raise ValueError('unsupported candidate workflow')
    child = Path('.github/workflows/homebrew-features-negative.yml').read_text() if name == 'homebrew-features-acceptance.yml' else None
    verify(os.environ['AUTOMATION_REF'], Path('.github/workflows', name).read_text(), negative_text=child)
