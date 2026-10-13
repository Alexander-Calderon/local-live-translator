"""Linux ASR-only replay of public PCM16 audio; no microphone or translation."""
import argparse,hashlib,json,queue,re,resource,subprocess,threading,time,urllib.request,wave
from pathlib import Path
from types import SimpleNamespace
import numpy as np

def words(text):
    return re.findall(r"[a-z]+(?:'[a-z]+)?",re.sub(r'\bmr\.?\b','mister',text.lower()))

def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        following=[i]
        for j,y in enumerate(b,1):following.append(min(following[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=following
    return row[-1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',choices=['legacy','integrated'],required=True)
    parser.add_argument('--manifest',type=Path,default=Path('docs/streaming-corpus.json'))
    parser.add_argument('--audio-dir',type=Path,required=True)
    parser.add_argument('--download-audio',action='store_true',help='explicitly download and normalize public fixtures; requires ffmpeg')
    parser.add_argument('--model',required=True,help='installed CT2 directory or cached model name')
    parser.add_argument('--device',choices=['cpu','cuda'],default='cuda')
    parser.add_argument('--compute',default='float16')
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();clips=json.loads(args.manifest.read_text())['clips'];audio=[]
    for clip in clips:
        filename=Path(clip['wav'])
        if filename.name!=clip['wav']:raise ValueError('Fixture filename must be a basename')
        path=args.audio_dir/filename
        if not path.exists() and args.download_audio:
            args.audio_dir.mkdir(parents=True,exist_ok=True)
            url=clip['source_url']
            if not url.startswith('https://datasets-server.huggingface.co/'):raise ValueError('Unexpected fixture origin')
            with urllib.request.urlopen(url,timeout=45) as response:data=response.read(20_000_001)
            if len(data)>20_000_000 or hashlib.sha256(data).hexdigest()!=clip['source_sha256']:raise ValueError('Fixture download hash mismatch')
            source=path.with_suffix('.source');source.write_bytes(data)
            subprocess.run(['ffmpeg','-v','error','-y','-i',str(source),'-ar','16000','-ac','1','-c:a','pcm_s16le',str(path)],check=True)
        with wave.open(str(path),'rb') as f:
            if (f.getnchannels(),f.getsampwidth(),f.getframerate())!=(1,2,16000):raise ValueError('Fixture must be PCM16 mono 16 kHz')
            audio.extend([np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(np.float32)/32768,np.zeros(8000,dtype=np.float32)])
    audio=np.concatenate(audio+[np.zeros(80000,dtype=np.float32)])
    from faster_whisper import WhisperModel
    reference_model=args.model
    if not Path(args.model).is_dir():
        from faster_whisper.utils import download_model
        root=Path(__file__).resolve().parents[1]
        for cache in (root/'models',Path.home()/'.cache/huggingface/hub',Path.home()/'AI/Models/huggingface/hub'):
            try:reference_model=download_model(args.model,cache_dir=str(cache),local_files_only=True);break
            except Exception:continue
    model=WhisperModel(reference_model,device=args.device,compute_type=args.compute,local_files_only=True)
    events=[];calls=[];started=time.monotonic();actual=model.transcribe
    def measured(*a,**kw):
        kw.update(beam_size=1,vad_filter=True,condition_on_previous_text=False)
        began=time.monotonic();result,info=actual(*a,**kw);result=list(result);calls.append(time.monotonic()-began);return result,info
    model.transcribe=measured
    def record(kind,text):
        if text.strip():events.append(dict(seconds=time.monotonic()-started,kind=kind,text=text))
    class Output:
        def __init__(self,*a):self.q=queue.Queue();self.log=None;self.view=True;self.pending=''
        def add(self,text):record('committed',text)
        def preview(self,text):record('partial',text)
        def flush(self,*a):pass
    q=queue.Queue()
    def feed():
        for i in range(0,len(audio),1600):
            time.sleep(max(0,started+(i+1600)/16000-time.monotonic()));q.put(audio[i:i+1600])
        q.put(None)
    feeder=threading.Thread(target=feed);feeder.start();settings=SimpleNamespace(lang='en',stats=False,preview=True,beam_size=1,device_kind=args.device)
    if args.backend=='legacy':
        import listen
        listen.Output=Output;listen.run_stream(model,q,settings,None)
    else:
        from whisperlive_adapter import run
        run(model,q,settings,None,None,Output)
    feeder.join();reference=' '.join(c['reference'] for c in clips);text=''.join(e['text'] for e in events if e['kind']=='committed')
    errors=distance(words(reference),words(text));count=len(words(reference))
    report=dict(backend=args.backend,audio_seconds=len(audio)/16000,reference_words=count,errors=errors,wer=errors/count,
        model=args.model,device=args.device,compute=args.compute,beam=1,vad=True,word_timestamps=True,condition_on_previous_text=False,
        first_partial_seconds=next((e['seconds'] for e in events if e['kind']=='partial'),None),peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,
        asr_compute_seconds=sum(calls),wall_seconds=time.monotonic()-started,reference=reference,text=text,events=events)
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('reference','text','events')}))
if __name__=='__main__':main()
