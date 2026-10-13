"""Prepare a pinned WhisperLive backend without installing another runtime."""
import hashlib,json,urllib.request
from pathlib import Path

REVISION='f26bdd5294ace7d31020ca00e04e7b14c2b7d954'
FILES=['LICENSE','whisper_live/metrics.py','whisper_live/backend/base.py',
       'whisper_live/backend/faster_whisper_backend.py']

def install(target):
    target=Path(target)
    prepared=target/'manifest.json'
    if prepared.is_file():
        previous=json.loads(prepared.read_text())
        hashes=previous.get('installed_sha256',{})
        if previous.get('revision')==REVISION and hashes and all((target/name).is_file() and hashlib.sha256((target/name).read_bytes()).hexdigest()==digest for name,digest in hashes.items()):
            return
    target.mkdir(parents=True,exist_ok=True)
    manifest={'repository':'https://github.com/collabora/WhisperLive','revision':REVISION,'sha256':{}}
    for name in FILES:
        url=f'https://raw.githubusercontent.com/collabora/WhisperLive/{REVISION}/{name}'
        with urllib.request.urlopen(url,timeout=30) as response:data=response.read(2_000_001)
        if len(data)>2_000_000:raise ValueError('Fuente demasiado grande')
        manifest['sha256'][name]=hashlib.sha256(data).hexdigest()
        text=data.decode()
        if name.endswith('faster_whisper_backend.py'):
            # Torch was used only to probe CUDA. Reuse the already loaded CT2 model.
            text=text.replace('import torch\n','')
            text=text.replace('from whisper_live.transcriber.transcriber_faster_whisper import WhisperModel','from faster_whisper import WhisperModel')
            text=text.replace('device = "cuda" if torch.cuda.is_available() else "cpu"','device = device or ("cuda" if ctranslate2.get_cuda_device_count() else "cpu")')
            text=text.replace('major, _ = torch.cuda.get_device_capability(device)\n            self.compute_type = "float16" if major >= 7 else "float32"','self.compute_type = "float16" if "float16" in ctranslate2.get_supported_compute_types("cuda") else "float32"')
            if 'torch.' in text:raise ValueError('Revisión incompatible con adaptación CUDA')
        destination=target/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(text)
    for name in ['whisper_live/__init__.py','whisper_live/backend/__init__.py']:
        (target/name).write_text('')
    manifest['installed_sha256']={name:hashlib.sha256((target/name).read_bytes()).hexdigest() for name in FILES}
    manifest['adaptation']='CT2 device probing and preloaded model; streaming logic unchanged'
    (target/'manifest.json').write_text(json.dumps(manifest,indent=2))

if __name__=='__main__':
    install(Path(__file__).resolve().parents[1]/'.runtime/whisperlive')
    print('WhisperLive streaming backend prepared.')
