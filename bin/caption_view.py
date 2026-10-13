"""Local caption view. No frameworks, external assets or audio uploads."""
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAGE = '''<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Subtítulos en vivo</title><style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#10151b;color:#eef2f6}
body{max-width:1120px;margin:24px auto;padding:0 20px}header{display:flex;justify-content:space-between;align-items:center}
h1{font-size:20px;font-weight:600}button{background:#253242;color:inherit;border:1px solid #425268;border-radius:6px;padding:8px 12px;cursor:pointer}button:disabled{opacity:.5;cursor:not-allowed}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}.label{font-size:13px;color:#aab6c5;margin-bottom:12px}
.current{background:#19212b;border:1px solid #303e4e;border-radius:10px;padding:20px;min-height:190px}
.words{font-size:26px;line-height:1.5;white-space:pre-wrap;overflow-wrap:anywhere}.draft{color:#bdcad9}
.transcription-only .pair{grid-template-columns:1fr}.transcription-only #translation-column,.transcription-only .entry>div:nth-child(2){display:none}
.possible-filler{color:#a7aeba;text-decoration:underline dotted;text-underline-offset:5px}
.note{font-size:13px;color:#aab6c5;line-height:1.5}#history{max-height:48vh;overflow:auto;margin:20px 0}
.entry{padding:18px 0;border-bottom:1px solid #303e4e}.entry .words{font-size:21px}
#status{min-height:1.5em;font-size:12px;color:#9bacbf}@media(max-width:700px){.pair{grid-template-columns:1fr;gap:14px}.words{font-size:22px}}
</style><header><h1>Subtítulos en vivo</h1><div><button id="floating">Ventana flotante</button> <button id="freeze">Pausar lectura</button></div></header>
<p class="note">La última frase permanece arriba hasta que llegue la siguiente. El historial conserva las frases confirmadas; el texto provisional puede corregirse al llegar más audio.</p>
<p class="note" id="configuration"></p>
<p class="note" id="runtime"></p>
<p class="note" id="view-message" role="status"></p>
<section class="pair current"><div><div class="label">Original</div><div class="label">Palabras confirmadas</div><div class="words" id="source"></div><div id="provisional-panel"><hr style="border:0;border-top:1px solid #425268;margin:16px 0"><div class="label">Provisional · puede corregirse</div><div class="words draft" id="preview"></div></div></div>
<div id="translation-column"><div class="label">Última traducción confirmada</div><div class="words" id="translation"></div><p class="note"><strong id="translation-source-label">Original de esa traducción</strong><br><span id="translation-source"></span></p></div></section>
<p class="note draft" id="translation-preview"></p>
<div id="history" aria-label="Frases confirmadas"></div><div id="status"></div>
<script>
let version=-1,frozen=false;const nodes=new Map();
const sourceNode=document.querySelector('#source'),previewNode=document.querySelector('#preview'),translationNode=document.querySelector('#translation');
const provisionalPanel=document.querySelector('#provisional-panel'),translationSourceNode=document.querySelector('#translation-source');
let floatingWindow=null,pollTimer=null,pollOwner=window,polling=false;
function cancelPoll(){if(pollTimer!==null){try{pollOwner.clearTimeout(pollTimer)}catch(_){}pollTimer=null}}
const change=(node,text)=>{text=['mode-cost','app-message','start','stop','status','freeze','floating','view-message','configuration','runtime','translation-preview'].includes(node.id)&&typeof localizedText==='function'?localizedText(text):text;if(node.textContent!==text)node.textContent=text};
function annotated(node,text,spans=[]){
 const signature=JSON.stringify([text,spans]);if(node.dataset.signature===signature)return;
 node.dataset.signature=signature;node.replaceChildren();let cursor=0;const chars=Array.from(text);
 for(const span of spans){if(span.start<cursor||span.end>chars.length||span.end<=span.start)continue;
 node.append(document.createTextNode(chars.slice(cursor,span.start).join('')));
 const hint=document.createElement('span');hint.className='possible-filler';hint.title='Posible disfluencia; el original se conserva';hint.textContent=chars.slice(span.start,span.end).join('');node.append(hint);cursor=span.end}
 node.append(document.createTextNode(chars.slice(cursor).join('')));
}
document.querySelector('#freeze').onclick=()=>{frozen=!frozen;change(document.querySelector('#freeze'),frozen?'Continuar lectura':'Pausar lectura')};
const floatingButton=document.querySelector('#floating');
if(!('documentPictureInPicture' in window)){
 floatingButton.disabled=true;floatingButton.textContent='Ventana flotante no disponible';floatingButton.title='Este navegador no ofrece Document Picture-in-Picture. Usa un navegador de escritorio compatible.';
}else floatingButton.onclick=async()=>{
 try{
 if(floatingWindow&&!floatingWindow.closed){floatingWindow.close();return}
 const panel=document.querySelector('.current'),anchor=document.createComment('panel');
 floatingWindow=await documentPictureInPicture.requestWindow({width:680,height:280});
 panel.before(anchor);
 const style=floatingWindow.document.createElement('style');style.textContent=document.querySelector('style').textContent+'body{margin:12px;padding:0}.current{min-height:130px}.words{font-size:23px}.pair{grid-template-columns:1fr 1fr}';floatingWindow.document.head.append(style);
 floatingWindow.document.body.className=document.body.className;floatingWindow.document.title='Subtítulos en vivo';floatingWindow.document.body.append(panel);
 floatingWindow.addEventListener('pagehide',()=>{cancelPoll();anchor.before(panel);anchor.remove();floatingWindow=null;floatingButton.textContent='Ventana flotante';refresh()},{once:true});
 floatingButton.textContent='Volver al visor';
 cancelPoll();refresh();
 }catch(error){change(document.querySelector('#view-message'),'No se pudo abrir la ventana flotante: '+error.message)}
};
async function refresh(){
 if(polling)return;polling=true;
 try{const response=await fetch('state',{cache:'no-store'});if(!response.ok)throw Error('Conexión finalizada');
 const state=await response.json();if(!frozen&&state.version!==version){version=state.version;
 if(state.info)change(document.querySelector('#configuration'),'Modelo: '+state.info.model+' · '+state.info.device+' / '+state.info.compute+' · '+state.info.keywords+' pistas de vocabulario');
 change(document.querySelector('#runtime'),state.runtime||'');
 document.body.classList.toggle('transcription-only',state.info?.translation_enabled===false);if(floatingWindow&&!floatingWindow.closed)floatingWindow.document.body.className=document.body.className;
 annotated(sourceNode,state.source,state.spans);change(previewNode,state.preview);provisionalPanel.hidden=!state.preview;
 change(translationNode,state.translation);
 change(translationSourceNode,state.translation_source?state.translation_source:'La traducción confirmada permanece hasta que termine otro bloque.');
 change(document.querySelector('#translation-preview'),state.translation_preview?'Borrador, puede cambiar: '+state.translation_preview:'');
 const history=document.querySelector('#history');const nearBottom=history.scrollHeight-history.scrollTop-history.clientHeight<50;
 for(const row of state.history){let pair=nodes.get(row.id);if(!pair){const entry=document.createElement('div');entry.className='entry pair';
 const src=document.createElement('div'),target=document.createElement('div');src.className=target.className='words';
 entry.append(src,target);history.append(entry);pair={entry,src,target};nodes.set(row.id,pair)}
 annotated(pair.src,row.source,row.spans);change(pair.target,row.translation||'Traducción pendiente…')}
 const keep=new Set(state.history.map(row=>row.id));for(const [id,pair] of nodes){if(!keep.has(id)){pair.entry.remove();nodes.delete(id)}}
 if(nearBottom)history.scrollTop=history.scrollHeight;
 change(document.querySelector('#status'),state.status)}
 }catch(error){change(document.querySelector('#status'),'Conexión con el traductor finalizada o no disponible')}finally{polling=false;pollOwner=floatingWindow&&!floatingWindow.closed?floatingWindow:window;cancelPoll();pollTimer=pollOwner.setTimeout(refresh,250)}
}refresh();
</script></html>'''

class CaptionView:
    def __init__(self, assisted=False, info=None):
        self.lock = threading.Lock()
        self.state = dict(version=0, source='', preview='', translation='', spans=[], history=[], status='Escuchando · posibles disfluencias marcadas' if assisted else 'Escuchando')
        self.state['info']=info
        self.sequence = 0
        self.displayed_identity = None
        self.token = secrets.token_urlsafe(24)
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == f'/{owner.token}/':
                    body, kind = PAGE.encode(), 'text/html; charset=utf-8'
                elif self.path == f'/{owner.token}/state':
                    with owner.lock: body = json.dumps(owner.state, ensure_ascii=False).encode()
                    kind = 'application/json; charset=utf-8'
                else:
                    self.send_error(404); return
                self.send_response(200)
                self.send_header('Content-Type', kind)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.end_headers(); self.wfile.write(body)
            def log_message(self, *_): pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.url = f'http://127.0.0.1:{self.server.server_port}/{self.token}/'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def current(self, source, preview=''):
        with self.lock:
            # Keep the last sentence readable during pauses and empty updates.
            if not (source.strip() or preview.strip()):
                return
            self.displayed_identity = None
            self.state.update(source=source or self.state['source'], preview=preview, spans=[])
            self.state['version'] += 1

    def draft(self, text):
        with self.lock:
            if self.displayed_identity is not None:
                return
            self.state['translation_preview'] = text
            self.state['version'] += 1

    def begin(self, source):
        with self.lock:
            self.sequence += 1
            self.state['history'].append(dict(id=self.sequence, source=source, translation=''))
            self.state['history'] = self.state['history'][-100:]
            self.state['translation_preview'] = ''
            self.state.update(source=source, preview='', spans=[])
            self.displayed_identity = self.sequence
            self.state['version'] += 1
            return self.sequence

    def finish(self, identity, translation):
        with self.lock:
            for row in self.state['history']:
                if row['id'] == identity: row['translation'] = translation or '(sin traducción)'
            if identity >= self.state.get('last_translated_identity',0):
                row=next((row for row in self.state['history'] if row['id']==identity),None)
                if row:
                    self.state['translation'] = translation or '(sin traducción)'
                    self.state['translation_source'] = row['source']
                    self.state['last_translated_identity'] = identity
            self.state['version'] += 1

    def annotate(self, identity, spans):
        with self.lock:
            for row in self.state['history']:
                if row['id']==identity: row['spans']=spans
            if identity==self.displayed_identity: self.state['spans']=spans
            self.state['version']+=1

    def status(self, text):
        with self.lock:
            self.state['status'] = text
            self.state['version'] += 1

    def metrics(self, buffer_seconds, recognition_seconds, queued_seconds):
        with self.lock:
            warning = ' · cola de audio pendiente' if queued_seconds > 2 else ''
            self.state['runtime'] = (f'Audio analizado {buffer_seconds:.1f}s · '
                                     f'reconocimiento {recognition_seconds:.2f}s · '
                                     f'cola ≈{queued_seconds:.1f}s{warning}')
            self.state['version'] += 1

    def close(self):
        self.server.shutdown()
        self.server.server_close()
