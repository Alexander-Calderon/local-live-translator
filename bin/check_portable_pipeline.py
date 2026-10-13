"""Bounded acceptance replay. Downloads only public fixture/model when --prepare is explicit."""
import argparse, hashlib, json, subprocess, sys, time, urllib.request, wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bin'))
FIXTURE_URL='https://raw.githubusercontent.com/collabora/WhisperLive/f26bdd5294ace7d31020ca00e04e7b14c2b7d954/assets/jfk.flac'
FIXTURE_HASH='63a4b1e4c1dc655ac70961ffbf518acd249df237e5a0152faae9a4a836949715'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');args=parser.parse_args()
    import av
    from app import Manager, PROFILES
    from faster_whisper.utils import download_model
    target=ROOT/'.runtime/portability';target.mkdir(parents=True,exist_ok=True)
    fixture=target/'public-fixture.flac';wav=target/'public-fixture.wav'
    if not fixture.exists():
        if not args.prepare:raise RuntimeError('Falta muestra pública; usa --prepare.')
        with urllib.request.urlopen(FIXTURE_URL,timeout=30) as response:data=response.read(2_000_001)
        if hashlib.sha256(data).hexdigest()!=FIXTURE_HASH:raise ValueError('Muestra diferente a la revisada.')
        fixture.write_bytes(data)
    if hashlib.sha256(fixture.read_bytes()).hexdigest()!=FIXTURE_HASH:raise ValueError('Muestra local alterada.')
    with av.open(str(fixture)) as media,wave.open(str(wav),'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000)
        converter=av.AudioResampler(format='s16',layout='mono',rate=16000)
        for frame in media.decode(audio=0):
            for chunk in converter.resample(frame):output.writeframes(chunk.to_ndarray().tobytes())
        for chunk in converter.resample(None):output.writeframes(chunk.to_ndarray().tobytes())
    if args.prepare:
        try:download_model('base',local_files_only=True)
        except Exception:download_model('base',cache_dir=str(ROOT/'models'))
        for file in ['install_translation.py','install_streaming.py']:
            subprocess.run([sys.executable,str(ROOT/'bin'/file)],check=True,timeout=180)
    # Full application manager + worker, finite WAV replay instead of hardware.
    PROFILES['base']=['--live','--model','base','--cpu','--threads','2']
    manager=Manager(wav);start=time.monotonic()
    config=dict(profile='base',source='system',chunk_words=18,technical=False,terms='',draft=False,save=False,offline=True,language='en',target='es')
    try:
        manager.start(config);manager.process.wait(timeout=120)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline and not manager.snapshot.get('history'):time.sleep(.1)
        rows=manager.snapshot.get('history',[])
        if manager.process.returncode:raise RuntimeError('El worker terminó con error: '+str(manager.process.returncode))
        original=' '.join(row.get('source','') for row in rows)
        translations=' '.join(row.get('translation','') for row in rows)
        if 'country' not in original.lower() or not translations.strip():
            raise AssertionError('El replay no produjo original y traducción.')
        if manager.snapshot.get('preview') or manager.snapshot.get('translation_preview'):
            raise AssertionError('Quedó una hipótesis sin confirmar después del cierre.')
        report={'platform':sys.platform,'python':sys.version.split()[0],'fixture_sha256':FIXTURE_HASH,'elapsed_seconds':round(time.monotonic()-start,3),'source':original,'translation':translations,'worker_exit':manager.process.returncode,'scope':'application/CPU/model/translation/replay; excludes native audio devices'}
        (target/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in report.items() if k not in {'source','translation'}},indent=2))
    finally:manager.stop()
if __name__=='__main__':main()
