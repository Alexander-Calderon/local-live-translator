import subprocess,sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bin'))
from audio_mix import AudioMix

class AudioMixTests(unittest.TestCase):
    def test_failure_removes_only_owned_modules(self):
        calls=[]
        def run(args,**kwargs):
            calls.append(args)
            if args[1]=='load-module':
                if args[2]=='module-loopback':raise subprocess.CalledProcessError(1,args)
                return SimpleNamespace(stdout='81\n')
            return SimpleNamespace(stdout='')
        mix=AudioMix(run)
        with self.assertRaises(subprocess.CalledProcessError):mix.open('fixture.monitor','fixture-mic')
        self.assertEqual(calls[-1],['pactl','unload-module','81'])
        self.assertEqual(mix.modules,[])
        self.assertFalse(any('set-default' in str(call) for call in calls))

    def test_normal_shutdown_is_idempotent(self):
        calls=[];identities=iter(['71','72','73'])
        def run(args,**kwargs):
            calls.append(args)
            return SimpleNamespace(stdout=next(identities) if args[1]=='load-module' else '')
        mix=AudioMix(run);self.assertTrue(mix.open('fixture.monitor','fixture-mic').endswith('.monitor'))
        mix.close();mix.close()
        self.assertEqual([x[-1] for x in calls if x[1]=='unload-module'],['73','72','71'])
