"""Require all literal candidate refs to agree before any fixture tap writes."""
import os
from pathlib import Path
import re


def verify(sha, text, check_text=None, feature_text=None, negative_text=None):
    if not re.fullmatch(r'[0-9a-fA-F]{40}', sha):
        raise ValueError('automation-ref must be a full 40-character commit SHA')
    for selected, count in [(text, 4), (check_text, 2), (feature_text, 8), (negative_text, 1)]:
        if selected is None:
            continue
        pins = re.findall(r'uses: releaseway/homebrew-actions/\.github/workflows/(?:check|publish)\.yml@([0-9a-fA-F]{40})', selected)
        if len(pins) != count or any(pin.lower() != sha.lower() for pin in pins):
            raise ValueError(f'automation-ref must match all {count} committed reusable-workflow pins')


if __name__ == '__main__':
    verify(os.environ['AUTOMATION_REF'], Path('.github/workflows/homebrew-acceptance.yml').read_text(),
           Path('.github/workflows/test.yml').read_text(), Path('.github/workflows/homebrew-features-acceptance.yml').read_text(),
           Path('.github/workflows/homebrew-features-negative.yml').read_text())
