"""Temporary PulseAudio/PipeWire mix. Never changes default devices."""
import secrets
import subprocess

class AudioMix:
    def __init__(self, run=None):
        self.run=run or subprocess.run
        self.modules=[]
        self.sink='translator_mix_'+secrets.token_hex(8)

    def call(self,*args):
        return self.run(['pactl',*args],check=True,capture_output=True,text=True).stdout.strip()

    def load(self,module,*args):
        identity=self.call('load-module',module,*args)
        if not identity.isdigit():
            raise OSError('No se pudo identificar el módulo de audio')
        self.modules.append(identity)

    def open(self,system=None,microphone=None):
        if self.modules:
            raise ValueError('La mezcla ya está abierta')
        system=system or self.call('get-default-sink')+'.monitor'
        if microphone is None:
            microphone=self.call('get-default-source')
            if microphone.endswith('.monitor'):
                raise ValueError('Selecciona un micrófono real como entrada predeterminada')
        try:
            self.load('module-null-sink','sink_name='+self.sink,'rate=16000','channels=1')
            for source in (system,microphone):
                self.load('module-loopback','source='+source,'sink='+self.sink,
                          'latency_msec=50','source_dont_move=true','sink_dont_move=true')
            return self.sink+'.monitor'
        except Exception:
            self.close()
            raise

    def close(self):
        errors=[]
        for identity in reversed(self.modules):
            try:self.call('unload-module',identity)
            except (OSError,subprocess.SubprocessError):errors.append(identity)
        self.modules=list(reversed(errors))
