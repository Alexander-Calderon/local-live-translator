"""Prepare a digest-pinned AudioTee helper on macOS; no global install or audio capture."""
import hashlib, json, os, platform, shutil, subprocess, sys, tarfile, tempfile, urllib.request
from pathlib import Path
REVISION = '56ac954369a09318e46b88a6eec33c2d2b0d32a3'
SHA256 = '233e8ea460e6116be15f0ee3ce4610c2c69f508a21d42b3064ee733adaf00af5'
URL = 'https://codeload.github.com/makeusabrew/audiotee/tar.gz/'+REVISION
ROOT = Path(__file__).resolve().parents[1]

def install():
    if sys.platform != 'darwin':
        print('AudioTee se prepara solo en macOS.'); return
    version = tuple(int(x) for x in platform.mac_ver()[0].split('.')[:2])
    if version < (14,2): raise RuntimeError('El audio del sistema requiere macOS 14.2 o posterior.')
    target = ROOT/'.runtime/audiotee'; manifest = target/'manifest.json'
    if manifest.is_file() and (target/'audiotee').is_file():
        data = json.loads(manifest.read_text())
        if data.get('revision') == REVISION and data.get('binary_sha256') == hashlib.sha256((target/'audiotee').read_bytes()).hexdigest():
            print('AudioTee ya está preparado; se conserva.'); return
    if not shutil.which('swift'):
        raise RuntimeError('Faltan las herramientas Swift. Instala Command Line Tools de Apple y vuelve a ejecutar este comando.')
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target, prefix='build-') as temporary:
        staging = Path(temporary)
        with urllib.request.urlopen(URL, timeout=45) as response: data=response.read(2_000_001)
        if len(data)>2_000_000 or hashlib.sha256(data).hexdigest()!=SHA256:
            raise ValueError('Las fuentes no coinciden con el archivo revisado.')
        archive=staging/'source.tar.gz'; archive.write_bytes(data)
        with tarfile.open(archive) as bundle: bundle.extractall(staging, filter='data')
        source=staging/('audiotee-'+REVISION)
        subprocess.run(['swift','build','-c','release'],cwd=source,check=True,timeout=240)
        output=subprocess.check_output(['swift','build','-c','release','--show-bin-path'],cwd=source,text=True,timeout=30).strip()
        binary=Path(output)/'audiotee'
        shutil.copy2(binary,target/'audiotee'); (target/'audiotee').chmod(0o755)
        shutil.copy2(source/'README.md',target/'UPSTREAM-README.md')
        (target/'manifest.json').write_text(json.dumps({'repository':'https://github.com/makeusabrew/audiotee','revision':REVISION,'archive_sha256':SHA256,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()},indent=2))
    print('AudioTee preparado. macOS pedirá permiso de audio al iniciar la captura.')
if __name__=='__main__': install()
