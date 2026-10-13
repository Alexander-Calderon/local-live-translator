"""Native capture adapters. All outputs are mono float32, 16 kHz, 100 ms blocks."""
import importlib.util
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
from fractions import Fraction
from pathlib import Path
np = None
def _numpy():
    global np
    if np is None:
        import numpy as library
        np = library
    return np
RATE, BLOCK = 16000, 1600
ROOT = Path(__file__).resolve().parents[1]

def check_capture(source, device=None, system=None):
    system = system or sys.platform
    if source not in {'system', 'mic', 'both'}:
        raise ValueError('Fuente de audio inválida')
    if system.startswith('linux'):
        if not all(shutil.which(name) for name in ('pactl', 'parec')):
            raise RuntimeError('Se necesitan pactl y parec (pulseaudio-utils).')
    elif system == 'win32':
        if importlib.util.find_spec('pyaudiowpatch') is None:
            raise RuntimeError('Falta PyAudioWPatch. Ejecuta python install.py.')
    elif system == 'darwin':
        if source in {'mic', 'both'} and importlib.util.find_spec('soundcard') is None:
            raise RuntimeError('Falta SoundCard. Ejecuta python install.py.')
        if source in {'system', 'both'}:
            version = tuple(int(x) for x in platform.mac_ver()[0].split('.')[:2])
            if version < (14, 2):
                raise RuntimeError('Capturar audio del sistema requiere macOS 14.2 o posterior.')
            if not (ROOT / '.runtime/audiotee/audiotee').is_file():
                raise RuntimeError('Falta AudioTee. Ejecuta python bin/install_capture.py.')
    else:
        raise RuntimeError('Sistema operativo no compatible con la captura.')

class BlockResampler:
    """FFmpeg/PyAV anti-alias resampling; PyAV is already a Faster Whisper dependency."""
    def __init__(self, rate):
        _numpy()
        import av
        self.av, self.rate, self.pts = av, rate, 0
        self.resampler = av.AudioResampler(format='flt', layout='mono', rate=RATE)
        self.pending = np.empty(0, np.float32)
    def convert(self, data):
        data = np.asarray(data, dtype=np.float32)
        mono = data.mean(axis=1) if data.ndim == 2 else data
        frame = self.av.AudioFrame.from_ndarray(mono.reshape(1, -1), format='flt', layout='mono')
        frame.sample_rate, frame.pts, frame.time_base = self.rate, self.pts, Fraction(1, self.rate)
        self.pts += len(mono)
        return self._blocks(self.resampler.resample(frame))
    def finish(self):
        blocks = self._blocks(self.resampler.resample(None))
        if len(self.pending):
            blocks.append(self.pending.copy()); self.pending = np.empty(0, np.float32)
        return blocks
    def _blocks(self, frames):
        chunks = [f.to_ndarray().reshape(-1) for f in frames]
        if chunks:
            self.pending = np.concatenate([self.pending, *chunks]).astype(np.float32)
        result = []
        while len(self.pending) >= BLOCK:
            result.append(self.pending[:BLOCK].copy()); self.pending = self.pending[BLOCK:]
        return result

def windows_blocks(source, stop, device=None):
    _numpy()
    import pyaudiowpatch as pa
    # Keep all native channels, then downmix. No unsupported mono loopback request.
    with pa.PyAudio() as p:
        info = (p.get_default_wasapi_loopback() if source == 'system'
                else p.get_default_input_device_info())
        if device is not None:
            info = p.get_device_info_by_index(int(device))
        rate, channels = int(info['defaultSampleRate']), int(info['maxInputChannels'])
        if channels < 1:
            raise RuntimeError('El dispositivo no permite capturar audio.')
        converter = BlockResampler(rate)
        with p.open(format=pa.paInt16, channels=channels, rate=rate, input=True,
                    input_device_index=info['index'], frames_per_buffer=max(1, rate//10)) as stream:
            while not stop.is_set():
                raw = stream.read(max(1, rate//10), exception_on_overflow=False)
                data = np.frombuffer(raw, dtype='<i2').reshape(-1, channels).astype(np.float32)/32768
                yield from converter.convert(data)
        yield from converter.finish()

def mac_mic_blocks(stop, device=None):
    _numpy()
    import soundcard as sc
    mic = sc.get_microphone(device) if device is not None else sc.default_microphone()
    if mic is None:
        raise RuntimeError('No se detecta micrófono; revisa el permiso de macOS.')
    # CoreAudio performs the requested rate conversion; no Windows mono path here.
    with mic.recorder(samplerate=RATE, blocksize=BLOCK) as recorder:
        while not stop.is_set():
            data = np.asarray(recorder.record(numframes=BLOCK), dtype=np.float32)
            yield data.mean(axis=1) if data.ndim == 2 else data

def mac_system_blocks(stop):
    _numpy()
    process = subprocess.Popen([str(ROOT/'.runtime/audiotee/audiotee'),
                                '--sample-rate', str(RATE), '--chunk-duration', '0.1'],
                               stdout=subprocess.PIPE, stderr=None)
    try:
        while not stop.is_set():
            raw = process.stdout.read(BLOCK*2)
            if not raw:
                if not stop.is_set():
                    raise RuntimeError('AudioTee terminó; revisa el permiso de grabación de audio del sistema.')
                break
            yield np.frombuffer(raw, dtype='<i2').astype(np.float32)/32768
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        process.stdout.close()

def mixed_blocks(generators, stop):
    """Keep two bounded queues and a paced mono mix. Never change default devices."""
    _numpy()
    queues = [queue.Queue(maxsize=20) for _ in generators]
    def pump(generator, target):
        try:
            for block in generator:
                if stop.is_set(): break
                try: target.put(block, timeout=.5)
                except queue.Full: raise RuntimeError('La captura acumuló demasiado audio sin procesar.')
        except Exception as error:
            # A failed source must not be disguised as silence.
            while not stop.is_set():
                try: target.put(error, timeout=.1); break
                except queue.Full: continue
        finally:
            try: target.put(None, timeout=.1)
            except queue.Full: pass
    threads = [threading.Thread(target=pump, args=(g, q), daemon=True) for g, q in zip(generators, queues)]
    for thread in threads: thread.start()
    deadline = time.monotonic()
    try:
        while not stop.is_set():
            deadline += BLOCK/RATE
            if stop.wait(max(0, deadline-time.monotonic())): break
            chunks = []
            for target in queues:
                try: item = target.get_nowait()
                except queue.Empty: item = np.zeros(BLOCK, np.float32)
                if isinstance(item, Exception): raise item
                if item is None: return
                if len(item) != BLOCK: item = np.pad(item[:BLOCK], (0, max(0, BLOCK-len(item))))
                chunks.append(item)
            yield np.clip(np.mean(chunks, axis=0), -1, 1).astype(np.float32)
    finally:
        stop.set()
        for thread in threads: thread.join(timeout=1)

def portable_blocks(source, stop, device=None, system=None):
    system = system or sys.platform
    if source == 'both' and device:
        raise ValueError('Un dispositivo concreto requiere elegir sistema o micrófono.')
    def one(kind):
        if system == 'win32': return windows_blocks(kind, stop, device)
        if system == 'darwin': return mac_system_blocks(stop) if kind == 'system' else mac_mic_blocks(stop, device)
        raise RuntimeError('El adaptador portátil no sustituye la captura PulseAudio de Linux.')
    if source == 'both': yield from mixed_blocks([one('system'), one('mic')], stop)
    else: yield from one(source)

def devices():
    if sys.platform == 'win32':
        import pyaudiowpatch as pa
        with pa.PyAudio() as p:
            return [{'id':d['index'], 'name':d['name'], 'loopback':bool(d.get('isLoopbackDevice'))}
                    for d in p.get_device_info_generator() if d['maxInputChannels'] > 0]
    if sys.platform == 'darwin':
        import soundcard as sc
        return [{'id':str(d.id), 'name':d.name} for d in sc.all_microphones()]
    return []
