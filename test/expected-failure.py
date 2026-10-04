from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/assert-action-failure.py"


class ExpectedFailureTests(unittest.TestCase):
    def run_case(self, source: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "fixture rejection", sys.executable, "-c", source],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_expected_rejection_has_no_error_annotation(self):
        result = self.run_case('print("::error::fixture rejection"); raise SystemExit(1)')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Verified expected rejection", result.stdout)
        self.assertFalse(any(line.startswith("::") for line in result.stdout.splitlines()))

    def test_unexpected_success_fails(self):
        result = self.run_case('print("fixture rejection")')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expected action exit code 1; got 0", result.stderr)

    def test_different_failure_reason_fails(self):
        result = self.run_case('print("::error::other failure"); raise SystemExit(1)')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expected rejection reason was not found", result.stderr)

    def test_crash_fails_even_when_reason_matches(self):
        result = self.run_case('print("fixture rejection"); raise SystemExit(2)')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Expected action exit code 1; got 2", result.stderr)


if __name__ == "__main__":
    unittest.main()
