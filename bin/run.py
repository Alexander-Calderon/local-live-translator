"""Run the recognition worker with the current Python, on any supported OS."""
import os, runpy, site, sys
from pathlib import Path

def main():
    args = sys.argv[1:]
    if args[:1] == ['--choose']:
        choice = input('Whisper: 1 base en vivo, 2 small en vivo, 3 medium por segmentos [1]: ').strip() or '1'
        from runtime_launcher import choose_mode
        args = choose_mode(args[1:],choice)
    handles = []
    if os.name == 'nt':
        for root in site.getsitepackages():
            for directory in Path(root).glob('nvidia/*/bin'):
                os.environ['PATH'] = str(directory)+os.pathsep+os.environ.get('PATH','')
                handles.append(os.add_dll_directory(str(directory)))
    sys.argv = [str(Path(__file__).with_name('listen.py')), *args]
    runpy.run_path(sys.argv[0], run_name='__main__')
if __name__ == '__main__': main()
