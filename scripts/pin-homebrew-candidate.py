"""Pin reviewed candidates atomically across legacy, feature, negative and PR workflows."""
from pathlib import Path
import re
import sys

PATTERN = r'(uses: releaseway/homebrew-actions/\.github/workflows/(?:check|publish)\.yml@)[0-9a-fA-F]{40}(?: #[^\n]*)?'


def pin(sha, path=Path('.github/workflows/homebrew-acceptance.yml'), check_path=None, feature_path=None, negative_path=None):
    if not re.fullmatch(r'[0-9a-fA-F]{40}', sha):
        raise ValueError('candidate must be a full 40-character commit SHA')
    changes = []
    for selected, count, default in [(path, 4, True), (check_path, 2, False), (feature_path, 8, True), (negative_path, 1, False)]:
        if selected is None:
            continue
        text, actual = re.subn(PATTERN, lambda match: match[1] + sha.lower(), selected.read_text())
        if actual != count:
            raise ValueError(f'expected {count} literal reusable-workflow pins')
        if default:
            text, defaults = re.subn(r'(?m)^(        default: )[0-9a-fA-F]{40}$',
                                     lambda match: match[1] + sha.lower(), text)
            if defaults != 1:
                raise ValueError('expected one automation-ref default')
        changes.append((selected, text))
    for selected, text in changes:
        selected.write_text(text)


if __name__ == '__main__':
    pin(sys.argv[1], check_path=Path('.github/workflows/test.yml'),
        feature_path=Path('.github/workflows/homebrew-features-acceptance.yml'),
        negative_path=Path('.github/workflows/homebrew-features-negative.yml'))
