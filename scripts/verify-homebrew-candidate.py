"""GitHub requires reusable workflow refs to be literal; verify them before tap writes."""
import os
from pathlib import Path
import re


def verify(sha, text):
    if not re.fullmatch(r'[0-9a-fA-F]{40}', sha):
        raise ValueError('automation-ref must be a full 40-character commit SHA')
    pins = re.findall(r'uses: releaseway/homebrew-actions/\.github/workflows/(?:check|publish)\.yml@([0-9a-fA-F]{40})', text)
    if len(pins) != 4 or any(pin.lower() != sha.lower() for pin in pins):
        raise ValueError('automation-ref must match all four committed reusable-workflow pins')


if __name__ == '__main__':
    verify(os.environ['AUTOMATION_REF'], Path('.github/workflows/homebrew-acceptance.yml').read_text())
