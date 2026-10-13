import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bin'))
import check_publication

class PublicationTests(unittest.TestCase):
    def test_media_change_requires_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'docs/media').mkdir(parents=True)
            (root / 'docs/media/poster.png').write_bytes(b'Unreviewed replacement')
            issues = check_publication.findings(root, ['docs/media/poster.png'])
            self.assertEqual(issues[0][1], 'medio distinto del artefacto revisado')
            self.assertFalse(check_publication.allowed('docs/media/private-recording.mp4'))

    def test_no_logs_backups_or_weights(self):
        for name in ['out/meeting.txt', 'benchmarks/results.json', 'models/model.bin',
                     'bin/listen.py.bak', 'vocab/private.local.txt', '.env']:
            self.assertFalse(check_publication.allowed(name), name)
        self.assertTrue(check_publication.allowed('vocab/tech-example.txt'))

    def test_paths_and_keys_are_rejected(self):
        private_path = '/'.join(['', 'home', 'sample', 'private'])
        fake_key = 'gh' + 'p_' + 'x' * 36
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'README.md').write_text(private_path + '\n' + fake_key)
            issues = check_publication.findings(root, ['README.md'])
            self.assertEqual(len(issues), 2)
            self.assertNotIn(fake_key, str(issues))
            self.assertNotIn(private_path, str(issues))

    def test_check_before_git_init_has_no_side_effect(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / '.gitignore').write_text('/*\n!/.gitignore\n!/README.md\n')
            (root / 'README.md').write_text('Public documentation.')
            (root / 'meeting.txt').write_text('Private fixture.')
            result = subprocess.run([sys.executable, str(ROOT / 'bin/check_publication.py'), '--root', str(root)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse((root / '.git').exists())
            self.assertIn('2 archivos revisados', result.stdout)

    def test_ci_rejects_forced_private_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(['git', 'init', '--quiet', str(root)], check=True)
            (root / '.gitignore').write_text('/out/\n')
            (root / 'out').mkdir()
            (root / 'out/meeting.txt').write_text('Private fixture.')
            subprocess.run(['git', '-C', str(root), 'add', '-f', 'out/meeting.txt'], check=True)
            result = subprocess.run([sys.executable, str(ROOT / 'bin/check_publication.py'), '--root', str(root), '--tracked-only'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('fuera de la lista publicable', result.stdout)
            self.assertNotIn('Private fixture.', result.stdout)

if __name__ == '__main__':
    unittest.main()
