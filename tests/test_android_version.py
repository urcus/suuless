"""Stable release ordering across CI platforms and retries."""
from pathlib import Path
import subprocess
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/ci/android-version-code.sh'


class AndroidVersionTest(unittest.TestCase):
    def run_code(self, tag):
        return subprocess.run(['bash', str(SCRIPT), tag], capture_output=True, text=True)

    def test_ordering_and_limits(self):
        tags = ['v0.0.0', 'v0.7.0', 'v0.7.1', 'v0.999.999', 'v1.0.0', 'v1099.999.999']
        codes = []
        for tag in tags:
            result = self.run_code(tag)
            self.assertEqual(result.returncode, 0, result.stderr)
            codes.append(int(result.stdout))
        self.assertEqual(codes, sorted(set(codes)))
        self.assertEqual(codes[1], 1000007000)
        self.assertLessEqual(codes[-1], 2100000000)

    def test_invalid_release_components_fail(self):
        for tag in ['v01.0.0', 'v1.00.0', 'v1.0.01', 'v1100.0.0', 'v0.1000.0', 'v0.0.1000', 'v999999999999.0.0']:
            self.assertNotEqual(self.run_code(tag).returncode, 0, tag)

    def test_development_and_prerelease_codes(self):
        for tag in ['', 'v1.0.0-rc1', 'experiment']:
            self.assertEqual(self.run_code(tag).stdout.strip(), '1')
