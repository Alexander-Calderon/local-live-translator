"""Use WhisperLive's real backend locally with the already loaded ASR model."""
import json,sys,time
from pathlib import Path
import numpy as np

def run(model,q,args,translate,log_path,Output,view=None):
    root=Path(__file__).resolve().parents[1]/'.runtime/whisperlive'
    if not (root/'manifest.json').is_file():
        raise RuntimeError('Ejecuta python bin/install_streaming.py antes del modo en vivo')
    sys.path.insert(0,str(root))
    from whisper_live.backend.faster_whisper_backend import ServeClientFasterWhisper
    out=Output(translate,log_path);seen=set();partial=''
    class Socket:
        def close(self):pass
        def send(self,payload):
            nonlocal partial
            message=json.loads(payload)
            if message.get('status')=='ERROR':raise RuntimeError(message.get('message','ASR error'))
            rows=message.get('segments',[])
            for row in rows:
                if row.get('completed'):
                    identity=(row.get('start'),row.get('end'))
                    if identity not in seen:
                        seen.add(identity);out.add(row['text'])
            partial=' '.join(row['text'] for row in rows if not row.get('completed'))
            if getattr(args,'preview',False):out.preview(partial)
    class Prepared(ServeClientFasterWhisper):
        def create_model(self,device):self.transcriber=model
        def transcribe_audio(self,audio):
            began=time.monotonic()
            segments,info=model.transcribe(audio,language=args.lang,beam_size=getattr(args,'beam_size',1),
                vad_filter=True,word_timestamps=True,condition_on_previous_text=False)
            segments=list(segments)
            if view:
                frames=self.frames_np
                buffered=(len(frames)/16000 if frames is not None else 0)+self.frames_offset-self.timestamp_offset
                newly_arrived=max(0,buffered-len(audio)/16000)
                view.metrics(len(audio)/16000,time.monotonic()-began,newly_arrived+q.qsize()*.1)
            return segments
    backend=Prepared(Socket(),model='preloaded',language=args.lang,client_uid='local',
                     use_vad=True,word_timestamps=True,device=getattr(args,'device_kind',None))
    try:
        while True:
            audio=q.get()
            if audio is None:
                backend.add_frames(np.zeros(32000,dtype=np.float32))
                time.sleep(2)
                break
            backend.add_frames(audio)
    finally:
        backend.cleanup();backend.trans_thread.join(timeout=10)
        if backend.trans_thread.is_alive():raise RuntimeError('El hilo ASR no terminó')
        out.flush();out.q.join()
        if out.log:out.log.close()
