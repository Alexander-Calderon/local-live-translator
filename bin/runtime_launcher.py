"""Portable worker launch and scoped shutdown."""
import os
import signal
import subprocess
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def runtime_python():
    candidates = [ROOT/'.venv/Scripts/python.exe'] if sys.platform == 'win32' else [ROOT/'.venv/bin/python', ROOT/'faster-whisper/.venv/bin/python']
    for path in candidates:
        if path.is_file(): return str(path)
    return sys.executable

def worker_command(args):
    return [runtime_python(), str(ROOT/'bin/run.py'), *args]

def worker_environment():
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    if sys.platform.startswith('linux'):
        prefix = Path(runtime_python()).parent.parent
        libraries = sorted(prefix.glob('lib/python*/site-packages/nvidia/*/lib'))
        if libraries:
            env['LD_LIBRARY_PATH'] = os.pathsep.join([*(str(path) for path in libraries), env.get('LD_LIBRARY_PATH', '')])
    return env

def process_options():
    return {'creationflags':getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',512)} if sys.platform == 'win32' else {'start_new_session':True}

def stop_process(process):
    if process.poll() is not None: return
    if sys.platform == 'win32':
        try: process.send_signal(getattr(signal,'CTRL_BREAK_EVENT',1))
        except (OSError, ValueError): pass
        try: process.wait(timeout=5); return
        except subprocess.TimeoutExpired: pass
        # Windows kills only this owned worker. Native recorders have no daemon.
        process.terminate()
        try: process.wait(timeout=2)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=2)
    else:
        for sig, timeout in [(signal.SIGINT,5),(signal.SIGTERM,2),(signal.SIGKILL,2)]:
            if process.poll() is not None: break
            try: os.killpg(process.pid, sig)
            except ProcessLookupError: break
            try: process.wait(timeout=timeout)
            except subprocess.TimeoutExpired: pass

def choose_mode(args, choice):
    modes = {'1':['--live','--model','base'], '2':['--live','--model','small'],
             '3':['--asr','whisper','--model','medium','--mode','phrase','--segment','8','--view','web'],
             '4':['--live','--model','medium']}
    if choice not in modes: raise ValueError('Opción inválida')
    return list(args)+modes[choice]
