import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bin'))
from caption_view import CaptionView

class LatencyProfileTests(unittest.TestCase):
    @unittest.skipIf(sys.platform=='win32','Unix shell menu; portable menu is tested separately')
    def test_menu_selects_stream_or_phrase_without_loading_models(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            launcher = root / 'run.sh'
            launcher.write_text((ROOT / 'run.sh').read_text())
            executable = root / '.venv/bin/python'
            executable.parent.mkdir(parents=True)
            executable.write_text('#!/usr/bin/env python3\nimport json,sys\nprint("/tmp/lib" if sys.argv[1]=="-c" else json.dumps(sys.argv[2:]))\n')
            executable.chmod(0o755)
            for choice, model, streaming in [('1', 'base', True), ('2', 'small', True),
                                             ('3', 'medium', False), ('4', 'medium', True)]:
                result = subprocess.run(['bash', str(launcher), '--choose', '--offline', '--keywords', 'vocab/tech-example.txt'],
                                        input=choice+'\n', capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                args = json.loads(result.stdout)
                self.assertEqual(args[args.index('--model')+1], model)
                self.assertEqual('--live' in args, streaming)
                self.assertIn('--offline', args)
                if not streaming:
                    self.assertEqual(args[args.index('--mode')+1], 'phrase')
                    self.assertEqual(args[args.index('--segment')+1], '8')

    def test_metrics_do_not_replace_status_or_caption(self):
        view = CaptionView.__new__(CaptionView)
        view.lock = threading.Lock()
        view.state = {'version': 0, 'status': 'Translation error', 'source': 'Original'}
        view.metrics(12, 3.5, 4)
        self.assertIn('3.50s', view.state['runtime'])
        self.assertIn('cola de audio pendiente', view.state['runtime'])
        self.assertEqual(view.state['status'], 'Translation error')
        self.assertEqual(view.state['source'], 'Original')

if __name__ == '__main__':
    unittest.main()
