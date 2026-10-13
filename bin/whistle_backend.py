"""Offline Whistle CLI adapter: PCM16 WAV, explicit pinned files, bounded subprocess."""
import json, subprocess, tempfile, wave
from pathlib import Path
from types import SimpleNamespace
import numpy as np

class WhistleModel:
    def __init__(self, binary, weights, threads=4, keywords=None, normalize=False):
        self.binary = str(Path(binary).resolve(strict=True))
        self.weights = str(Path(weights).resolve(strict=True))
        self.threads = threads
        self.last_seconds = 0.0
        self.normalize = normalize
        self.keywords = None
        if keywords:
            file = Path(keywords).resolve(strict=True)
            if file.stat().st_size > 8192:
                raise ValueError("El vocabulario Whistle admite como máximo 8 KiB")
            text = file.read_text(encoding="utf-8")
            if '\x00' in text or len(text.splitlines()) > 100:
                raise ValueError("Vocabulario inválido: máximo 100 términos sin NUL")
            self.keywords = str(file)

    def transcribe(self, audio, language="en", **kwargs):
        if language not in ("en", "es", "de", "fr", "it", "nl", "pl"):
            raise ValueError("Whistle no admite el idioma: " + language)
        samples = np.asarray(audio, dtype=np.float32)
        if samples.ndim != 1 or not np.all(np.isfinite(samples)):
            raise ValueError("El audio debe ser mono y finito")
        if len(samples) > 16000 * 30:
            raise ValueError("Una pasada Whistle admite hasta 30 segundos")
        if not len(samples):
            return [], None
        # Bounded gain for quiet sources; never magnify near-silent buffers.
        if self.normalize:
            peak = float(np.max(np.abs(samples)))
            if 0.0005 < peak < 0.5:
                samples = samples * min(16.0, 0.5 / peak)
        with tempfile.TemporaryDirectory(prefix="translator-whistle-") as tmp:
            wav = Path(tmp)/"audio.wav"
            with wave.open(str(wav), "wb") as f:
                f.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                f.writeframes((np.clip(samples, -1, 1)*32767).astype("<i2").tobytes())
            command = [self.binary, "--model", self.weights, "--audio", str(wav),
                                  "--audio-language", language, "--audio-word-timestamps",
                                  "--threads", str(self.threads)]
            if self.keywords: command += ["--audio-keywords", self.keywords]
            run = subprocess.run(command, capture_output=True, text=True, timeout=30)
            if run.returncode:
                raise RuntimeError("Whistle falló: " + run.stderr[-500:])
            data = json.loads(run.stdout)
        words = [SimpleNamespace(word=" " + w["word"], start=w["start"], end=w["end"], probability=w["probability"])
                 for w in data.get("words", [])]
        for w in words:
            if not 0 <= w.start <= w.end <= len(samples)/16000 + 0.1:
                raise ValueError("Whistle devolvió timestamps fuera del audio")
        return [SimpleNamespace(text=data["text"], words=words)] if data["text"] else [], None
