"""Prepare the existing environment or a Python 3.12 venv on Linux, Windows or macOS."""
import os, shutil, subprocess, sys, venv
from pathlib import Path
ROOT = Path(__file__).resolve().parent

def main():
    if sys.version_info[:2] != (3,12): raise SystemExit('Ejecuta este instalador con Python 3.12.')
    if sys.platform.startswith('linux') and not all(shutil.which(x) for x in ('pactl','parec')):
        raise SystemExit('Instala pulseaudio-utils para tener pactl y parec.')
    candidates=[ROOT/'.venv/Scripts/python.exe'] if os.name=='nt' else [ROOT/'.venv/bin/python',ROOT/'faster-whisper/.venv/bin/python']
    python=next((p for p in candidates if p.is_file()),None)
    if python is None:
        venv.create(ROOT/'.venv',with_pip=True); python=candidates[0]
    # Reuse the user's environment; uv can prepare an environment without pip.
    pip=[str(python),'-m','pip']
    if subprocess.run(pip+['--version'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        if not shutil.which('uv'): raise SystemExit('Este entorno no tiene pip ni uv. Prepara pip antes de instalar.')
        command=['uv','pip','install','--python',str(python),'-r',str(ROOT/'requirements.txt')]
    else:command=pip+['install','-r',str(ROOT/'requirements.txt')]
    subprocess.run(command,check=True)
    for file,args in [('install_translation.py',[]),('install_translation.py',['--pair','es_en']),('install_streaming.py',[])]:
        subprocess.run([str(python),str(ROOT/'bin'/file),*args],check=True)
    if sys.platform=='darwin': subprocess.run([str(python),str(ROOT/'bin/install_capture.py')],check=True)
    print('Preparado. Windows: app.cmd; Linux/macOS: ./app.sh. Los permisos se conceden al iniciar la captura.')
if __name__=='__main__':main()
