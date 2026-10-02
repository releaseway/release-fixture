from pathlib import Path
import runpy
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
verify = runpy.run_path(str(ROOT / 'scripts/verify-homebrew-candidate.py'))['verify']
pin = runpy.run_path(str(ROOT / 'scripts/pin-homebrew-candidate.py'))['pin']


class CandidateTests(unittest.TestCase):
    def test_literal_pins_and_mismatch(self):
        text = (ROOT / '.github/workflows/homebrew-acceptance.yml').read_text()
        current = re.search(r'uses: releaseway/homebrew-actions/[^@]+@([0-9a-f]{40})', text)[1]
        verify(current, text)
        for value in ['main', 'a' * 40]:
            with self.assertRaises(ValueError): verify(value, text)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'workflow.yml'
            path.write_text(text)
            pin('a' * 40, path)
            verify('a' * 40, path.read_text())
            self.assertIn('        default: ' + 'a' * 40, path.read_text())
            with self.assertRaises(ValueError): verify('a' * 40, path.read_text().replace('@' + 'a' * 40, '@' + 'b' * 40, 1))
            before = path.read_bytes()
            with self.assertRaises(ValueError): pin('main', path)
            self.assertEqual(path.read_bytes(), before)

    def test_aggregate_only_after_all_suites(self):
        text = (ROOT / '.github/workflows/release-notes-acceptance.yml').read_text()
        aggregate = text.split('  acceptance-evidence:')[1]
        self.assertIn("if: inputs.suite == 'all'", aggregate)
        self.assertIn('needs: [preview, pr, publish]', aggregate)
        self.assertNotIn('always()', aggregate)
        self.assertEqual(text.count('git -C release-action rev-parse HEAD'), 3)
        for path in ['homebrew-acceptance.yml', 'release-notes-acceptance.yml']:
            self.assertIn('releaseway-acceptance-${{ github.run_attempt }}', (ROOT / '.github/workflows' / path).read_text())


if __name__ == '__main__':
    unittest.main()
