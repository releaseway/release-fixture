"""Pin the four reusable acceptance calls to a reviewed candidate SHA."""
from pathlib import Path
import re
import sys


def pin(sha, path=Path('.github/workflows/homebrew-acceptance.yml')):
    if not re.fullmatch(r'[0-9a-fA-F]{40}', sha):
        raise ValueError('candidate must be a full 40-character commit SHA')
    text, count = re.subn(r'(uses: releaseway/homebrew-actions/\.github/workflows/(?:check|publish)\.yml@)[0-9a-fA-F]{40}(?: #[^\n]*)?',
                         lambda match: match[1] + sha.lower(), path.read_text())
    if count != 4:
        raise ValueError('expected four literal reusable-workflow pins')
    text, defaults = re.subn(r'(?m)^(        default: )[0-9a-fA-F]{40}$',
                            lambda match: match[1] + sha.lower(), text)
    if defaults != 1:
        raise ValueError('expected one automation-ref default')
    path.write_text(text)


if __name__ == '__main__':
    pin(sys.argv[1])
