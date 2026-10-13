import sys, threading, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bin'))
import audio_capture as audio
import runtime_launcher as launcher

class PortableAudioTests(unittest.TestCase):
    def test_resampling_rejects_aliases_and_keeps_low_frequency(self):
        rate=48000; t=np.arange(rate,dtype=np.float32)/rate
        def convert(hz):
            converter=audio.BlockResampler(rate); result=[]
            for start in range(0,rate,4800): result+=converter.convert(np.sin(2*np.pi*hz*t[start:start+4800]))
            result+=converter.finish(); return np.concatenate(result)
        low,high=convert(1000),convert(12000)
        self.assertEqual(len(low),16000)
        self.assertGreater(np.sqrt(np.mean(low[100:-100]**2)),.65)
        self.assertLess(np.sqrt(np.mean(high[100:-100]**2)),.02)

    def test_windows_mono_microphone_and_stereo_loopback_cleanup(self):
        for kind,channels in [('mic',1),('system',2)]:
            stop=threading.Event(); calls=[]
            raw=np.full((4800,channels),8192,dtype='<i2').tobytes()
            class Stream:
                def __enter__(self):return self
                def __exit__(self,*_):calls.append('closed')
                def read(self,n,**kwargs):stop.set();return raw
            class PA:
                def __enter__(self):return self
                def __exit__(self,*_):calls.append('terminated')
                def get_default_wasapi_loopback(self):return {'defaultSampleRate':48000,'maxInputChannels':channels,'index':7}
                def get_default_input_device_info(self):return {'defaultSampleRate':48000,'maxInputChannels':channels,'index':8}
                def open(self,**kwargs):calls.append(kwargs);return Stream()
            with patch.dict(sys.modules,{'pyaudiowpatch':SimpleNamespace(PyAudio=PA,paInt16=8)}):
                blocks=list(audio.windows_blocks(kind,stop))
            self.assertEqual(calls[0]['channels'],channels)
            self.assertEqual(calls[0]['input_device_index'],7 if kind=='system' else 8)
            self.assertEqual(calls[-2:],['closed','terminated'])
            data=np.concatenate(blocks)
            self.assertAlmostEqual(float(data[100:-100].mean()),.25,places=3)

    def test_mix_does_not_disguise_a_failed_source_as_silence(self):
        stop=threading.Event()
        def fail():
            raise RuntimeError('Permission denied')
            yield
        with self.assertRaisesRegex(RuntimeError,'Permission denied'):
            list(audio.mixed_blocks([fail(),iter([np.zeros(1600,np.float32)])],stop))
        self.assertTrue(stop.is_set())

    def test_mix_preserves_both_frequencies_without_clipping(self):
        t=np.arange(1600)/16000
        a=.8*np.sin(2*np.pi*440*t);b=.8*np.sin(2*np.pi*880*t)
        result=list(audio.mixed_blocks([iter([a]),iter([b])],threading.Event()))
        self.assertEqual(len(result),1)
        spectrum=abs(np.fft.rfft(result[0]));self.assertGreater(spectrum[44],200);self.assertGreater(spectrum[88],200)
        self.assertLessEqual(float(abs(result[0]).max()),1)

    def test_windows_shutdown_never_uses_posix_groups(self):
        from subprocess import TimeoutExpired
        class Worker:
            pid=4321
            calls=[]
            def poll(self):return None
            def send_signal(self,sig):self.calls.append('break')
            def wait(self,timeout):
                if timeout==5:raise TimeoutExpired('fixture',5)
            def terminate(self):self.calls.append('terminate')
        worker=Worker()
        with patch.object(launcher.sys,'platform','win32'),patch.object(launcher.os,'killpg',create=True) as kill:
            launcher.stop_process(worker);kill.assert_not_called()
            self.assertIn('creationflags',launcher.process_options())
        self.assertEqual(worker.calls,['break','terminate'])

    def test_macos_old_system_fails_before_starting_capture(self):
        with patch.object(audio.platform,'mac_ver',return_value=('13.6',(),'')):
            with self.assertRaisesRegex(RuntimeError,'14.2'):audio.check_capture('system',system='darwin')

if __name__=='__main__':unittest.main()
