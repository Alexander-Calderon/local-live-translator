"""Local web controls. Owns only the subprocess it starts."""
import argparse,json,os,re,secrets,signal,subprocess,sys,threading,urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from caption_view import PAGE
from sessions import SessionStore
from audio_mix import AudioMix
ROOT=Path(__file__).resolve().parents[1]
PROFILES={
 'ultralight':['--profile','balanced','--no-translate','--threads','2','--view','web'],
 'base':['--live','--model','base'],
 'small':['--live','--model','small'],
 'medium':['--asr','whisper','--model','medium','--mode','phrase','--segment','8','--view','web'],
 'whistle':['--profile','balanced','--view','web']}
CONTROLS='''
<style>.settings{border:1px solid #303e4e;border-radius:10px;padding:18px;margin:20px 0}.options,.toggles{display:flex;gap:18px;flex-wrap:wrap}.options label{display:grid;gap:7px}.toggles{margin:18px 0}select,textarea{background:#19212b;color:#eef2f6;border:1px solid #425268;border-radius:6px;padding:8px;font:inherit}textarea{display:block;width:95%;margin:10px 0}a{color:#a6d3ff}.actions{margin-top:16px}summary{cursor:pointer}</style>
<details class="settings" open aria-label="Controles del traductor"><summary><strong>Configuración</strong></summary><div class="options" style="margin-top:16px">
<label>Modo<select id="profile"><option value="base">En vivo · Whisper base</option><option value="small">En vivo · Whisper small</option><option value="medium">Por segmentos · Whisper medium</option><option value="whistle">Ligero CPU · Whistle</option><option value="ultralight">Mínimo CPU · solo transcripción</option></select></label>
<label>Idioma original<select id="speech-language"><option value="en">English</option><option value="es">Español</option><option value="de">Deutsch</option><option value="fr">Français</option><option value="it">Italiano</option><option value="nl">Nederlands</option><option value="pl">Polski</option></select></label><label>Salida<select id="target-language"><option value="es">Traducción al español</option><option value="en">Traducción al inglés</option><option value="none">Solo transcripción</option></select></label><label>Audio<select id="audio"><option value="system">Audio del sistema</option><option value="mic">Micrófono</option><option value="both">Sistema y micrófono</option></select></label>
</div><div class="toggles"><label><input type="checkbox" id="save"> Guardar transcripción</label></div><details style="margin-top:16px"><summary>Configuración avanzada</summary><div class="options"><label>Frases<select id="chunks"><option value="18">Equilibradas</option><option value="12">Más cortas</option><option value="26">Más contexto</option></select></label></div>
<div class="toggles"><label><input type="checkbox" id="technical"> Vocabulario técnico</label><label><input type="checkbox" id="draft"> Borrador de traducción</label><label><input type="checkbox" id="offline" checked> Solo modelos descargados</label></div>
<details><summary>Personalizar vocabulario</summary><label>Términos esperados, uno por línea<textarea id="terms" rows="4" spellcheck="false"></textarea></label><p class="note">Son pistas. «T mux» y «T-mux» se normalizan a tmux solo al traducir. No se sustituyen otras palabras parecidas.</p></details>
<details><summary>Opciones experimentales</summary><label><input type="checkbox" id="pauses" disabled> Pausas experimentales · solo CLI legacy</label><br><label><input type="checkbox" id="fillers" disabled> Marcar posibles muletillas</label><p class="note">Las pausas no mejoraron de forma consistente las pruebas. Las muletillas requieren pesos FDT preparados aparte, con límites de uso de investigación. No se borran palabras del original.</p></details>
</details></details><p id="mode-cost" class="note" aria-live="polite"></p><div class="actions"><button id="start">Iniciar</button> <button id="stop" disabled>Detener</button> <button id="shortcut">Crear acceso al menú</button> <button id="quit">Cerrar app</button> <a id="export" hidden>Descargar transcripción</a></div><details id="session-pane" style="margin-top:18px"><summary>Sesiones guardadas</summary><p class="note">Archivos locales en .runtime/app/sessions/, fuera de Git. Retomar añade nueva captura; no reproduce audio anterior ni conserva memoria semántica.</p><label>Nombre de sesión <input id="session-name" maxlength="120" placeholder="Reunión o clase"></label><p><select id="sessions" aria-label="Sesiones guardadas"><option value="">Nueva sesión</option></select> <button id="load-session">Abrir</button> <button id="rename-session">Renombrar</button> <button id="resume-session">Retomar</button></p><pre id="session-content" style="white-space:pre-wrap;overflow-wrap:anywhere;max-height:40vh;overflow:auto"></pre><a id="session-export" hidden>Descargar sesión</a></details><p id="app-message" role="status" class="note">Elige un modo y pulsa Iniciar. Inglés ↔ español. Captura local en Linux.</p>'''
CONTROL_JS='''
let busy=false,termsReady=false,closedApp=false,selectedSession="";
const uiEnglish={"Whistle CPU sin traducción: 81 MiB RAM en el replay público medido, sin navegador. No requiere GPU ni carga el paquete de traducción. Medidas de este equipo, no requisitos universales. Whisper excluye traducción y navegador; el uso real varía con el audio y hardware.":"Whistle CPU without translation: 81 MiB RAM in the measured public replay, excluding browser. No GPU or translation package. This is a measurement, not a universal requirement; actual use depends on hardware and audio.","Escuchando":"Listening","Sistema y micrófono":"System and microphone","Idioma original":"Source language","Salida":"Output","Traducción al español":"Spanish translation","Traducción al inglés":"English translation","Solo transcripción":"Transcription only","Palabras confirmadas":"Confirmed words","Provisional · puede corregirse":"Provisional · may change","Mínimo CPU · solo transcripción":"Minimal CPU · transcription only","Configuración avanzada":"Advanced settings","Sesiones guardadas":"Saved sessions","Nombre de sesión":"Session name","Nueva sesión":"New session","Abrir":"Open","Renombrar":"Rename","Retomar":"Resume","Descargar sesión":"Download session","Archivos locales en .runtime/app/sessions/, fuera de Git. Retomar añade nueva captura; no reproduce audio anterior ni conserva memoria semántica.":"Local files in .runtime/app/sessions/, excluded from Git. Resume adds new audio; it does not replay previous audio or preserve semantic memory.","Subtítulos en vivo": "Live captions", "Ventana flotante": "Floating window", "Pausar lectura": "Pause reading", "Continuar lectura": "Resume reading", "Configuración": "Settings", "Modo": "Mode", "Audio": "Audio", "Frases": "Phrase length", "En vivo · Whisper base": "Live · Whisper base", "En vivo · Whisper small": "Live · Whisper small", "Por segmentos · Whisper medium": "Segments · Whisper medium", "Ligero CPU · Whistle": "Light CPU · Whistle", "Audio del sistema": "System audio", "Micrófono": "Microphone", "Equilibradas": "Balanced", "Más cortas": "Shorter", "Más contexto": "More context", "Vocabulario técnico": "Technical vocabulary", "Borrador de traducción": "Translation draft", "Guardar transcripción": "Save transcript", "Solo modelos descargados": "Downloaded models only", "Personalizar vocabulario": "Edit vocabulary", "Términos esperados, uno por línea": "Expected terms, one per line", "Opciones experimentales": "Experimental options", "Pausas experimentales · solo CLI legacy": "Split live Whisper by pauses", "Marcar posibles muletillas": "Mark possible fillers", "Iniciar": "Start", "Detener": "Stop", "Crear acceso al menú": "Create application shortcut", "Cerrar app": "Quit app", "Descargar transcripción": "Download transcript", "Elige un modo y pulsa Iniciar.": "Choose a mode and press Start.", "Aplicar y reiniciar": "Apply and restart", "Original": "Original", "Última traducción confirmada": "Latest confirmed translation", "Original de esa traducción": "Source of this translation", "La traducción confirmada permanece hasta que termine otro bloque.": "The confirmed translation stays until another block finishes.", "Detenido": "Stopped", "Sesión finalizada.": "Session ended.", "Capturando audio. Detener cierra solo esta sesión.": "Capturing audio. Stop ends only this session.", "Cargando modelo…": "Loading model…", "Elige un modo y pulsa Iniciar. Inglés ↔ español. Captura local en Linux.": "Choose a mode and press Start. English ↔ Spanish. Local capture on Linux.", "App cerrada. Puedes cerrar esta pestaña.": "App closed. You can close this tab.", "La última frase permanece arriba hasta que llegue la siguiente. El historial conserva las frases confirmadas; el texto provisional puede corregirse al llegar más audio.": "The latest phrase stays above until the next arrives. History keeps confirmed phrases; provisional text may change as more audio arrives.", "Son pistas. «T mux» y «T-mux» se normalizan a tmux solo al traducir. No se sustituyen otras palabras parecidas.": "These are hints. “T mux” and “T-mux” become tmux only during translation. Other similar words are not replaced.", "Las pausas no mejoraron de forma consistente las pruebas. Las muletillas requieren pesos FDT preparados aparte, con límites de uso de investigación. No se borran palabras del original.": "Pauses did not consistently improve the tests. Fillers require separately prepared FDT weights with research use limits. Original words are kept.", "No se pudo iniciar. Revisa opciones, vocabulario, entorno Python y audio disponible.": "Could not start. Check settings, vocabulary, Python environment and available audio.", "Detenido. Puedes cambiar el modo y volver a iniciar.": "Stopped. You can change the mode and start again.", "Cargando modelo. Para descargar pesos por primera vez, desmarca Solo modelos descargados.": "Loading model. To download weights for the first time, uncheck Downloaded models only.", "El motor se detuvo. Revisa modelos y audio disponible o prueba otro modo.": "The engine stopped. Check models and audio, or try another mode.", "Acceso creado. Busca Traductor local en el menú de aplicaciones.": "Shortcut created. Find Traductor local in your application menu.", "Whisper base: 847 MiB RAM + 280 MiB VRAM en la prueba ASR con CUDA. Recomendado para empezar en vivo. Medidas de este equipo, no requisitos universales. Whisper excluye traducción y navegador; el uso real varía con el audio y hardware.": "Whisper base: 847 MiB RAM + 280 MiB VRAM in the CUDA ASR test. Start here for live text. Measurements from this machine, not universal requirements. Whisper excludes translation and browser; actual use depends on audio and hardware.", "Whisper small: 897 MiB RAM + 504 MiB VRAM en la prueba ASR con CUDA. No mejoró la precisión frente a base en todos los clips. Medidas de este equipo, no requisitos universales. Whisper excluye traducción y navegador; el uso real varía con el audio y hardware.": "Whisper small: 897 MiB RAM + 504 MiB VRAM in the CUDA ASR test. It was not more accurate than base on every clip. Measurements from this machine, not universal requirements. Whisper excludes translation and browser; actual use depends on audio and hardware.", "Whisper medium: 1680 MiB RAM + 1240 MiB VRAM en la prueba ASR con CUDA. Trabaja por segmentos y tarda más en mostrar texto. Medidas de este equipo, no requisitos universales. Whisper excluye traducción y navegador; el uso real varía con el audio y hardware.": "Whisper medium: 1680 MiB RAM + 1240 MiB VRAM in the CUDA ASR test. Segment mode takes longer to show text. Measurements from this machine, not universal requirements. Whisper excludes translation and browser; actual use depends on audio and hardware.", "Whistle CPU: unos 230 MiB RAM para reconocimiento, traducción y visor en otro replay. Requiere preparar su motor. Medidas de este equipo, no requisitos universales. Whisper excluye traducción y navegador; el uso real varía con el audio y hardware.": "Whistle CPU: about 230 MiB RAM for recognition, translation and caption server in a different replay. Requires its engine. Measurements from this machine, not universal requirements. Whisper excludes translation and browser; actual use depends on audio and hardware."};
let uiLanguage='es';try{uiLanguage=localStorage.getItem('translator-ui-language')==='en'?'en':'es'}catch(_){}
function localizedText(text){if(uiLanguage!=='en'||typeof text!=='string')return text;return uiEnglish[text]||text.replace(/^Modelo: /,'Model: ').replace('pistas de vocabulario','vocabulary hints').replace(/^Audio analizado /,'Analyzed audio ').replace('reconocimiento ','recognition ').replace('cola ≈','queue ≈').replace('cola de audio pendiente','audio backlog').replace(/^Borrador, puede cambiar: /,'Draft, may change: ')}
const fixedText=[];const textWalker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
while(textWalker.nextNode()){const node=textWalker.currentNode;if(['SCRIPT','STYLE'].includes(node.parentElement.tagName))continue;const raw=node.textContent,key=raw.trim();if(uiEnglish[key])fixedText.push({node,raw,key})}
function applyUILanguage(){document.documentElement.lang=uiLanguage;document.title=localizedText('Subtítulos en vivo');for(const item of fixedText){if(item.node.isConnected)item.node.textContent=item.raw.replace(item.key,localizedText(item.key))}showCost();version=-1;}
document.querySelector('#ui-language').value=uiLanguage;
document.querySelector('#ui-language').onchange=function(){uiLanguage=this.value;try{localStorage.setItem('translator-ui-language',uiLanguage)}catch(_){}applyUILanguage()};

const modeCosts={ultralight:'Whistle CPU sin traducción: 81 MiB RAM en el replay público medido, sin navegador. No requiere GPU ni carga el paquete de traducción.',
 base:'Whisper base: 847 MiB RAM + 280 MiB VRAM en la prueba ASR con CUDA. Recomendado para empezar en vivo.',
 small:'Whisper small: 897 MiB RAM + 504 MiB VRAM en la prueba ASR con CUDA. No mejoró la precisión frente a base en todos los clips.',
 medium:'Whisper medium: 1680 MiB RAM + 1240 MiB VRAM en la prueba ASR con CUDA. Trabaja por segmentos y tarda más en mostrar texto.',
 whistle:'Whistle CPU: unos 230 MiB RAM para reconocimiento, traducción y visor en otro replay. Requiere preparar su motor.'};
function showCost(){const lang=document.querySelector('#speech-language').value;const target=document.querySelector('#target-language');const minimal=document.querySelector('#profile').value==='ultralight';for(const code of ['es','en'])target.querySelector('[value='+code+']').disabled=minimal||lang!==(code==='es'?'en':'es');if(target.selectedOptions[0].disabled)target.value=minimal||!['en','es'].includes(lang)?'none':(lang==='en'?'es':'en');change(document.querySelector('#mode-cost'),modeCosts[document.querySelector('#profile').value]+' Medidas de este equipo, no requisitos universales. Whisper excluye traducción y navegador; el uso real varía con el audio y hardware.')}
document.querySelector('#speech-language').addEventListener('change',showCost);document.querySelector('#profile').addEventListener('change',showCost);showCost();applyUILanguage();
async function listSessions(){try{const response=await fetch('sessions');const data=await response.json();const select=document.querySelector('#sessions');select.replaceChildren();const empty=document.createElement('option');empty.value='';empty.textContent=localizedText('Nueva sesión');select.append(empty);for(const session of data.sessions){const option=document.createElement('option');option.value=session.id;option.textContent=session.name+' · '+new Date(session.updated).toLocaleString();select.append(option)}select.value=selectedSession}catch(error){change(document.querySelector('#app-message'),error.message)}}
async function loadSession(){selectedSession='';const id=document.querySelector('#sessions').value;if(!id){selectedSession='';change(document.querySelector('#session-content'),'');return}try{const response=await fetch('session/'+id);const data=await response.json();if(!response.ok)throw Error(data.error);selectedSession=id;document.querySelector('#session-name').value=data.metadata.name;document.querySelector('#session-content').textContent=data.transcript;document.querySelector('#session-export').href='session/'+id+'/export';document.querySelector('#session-export').hidden=false;const c=data.metadata.config;document.querySelector('#speech-language').value=c.language||'en';document.querySelector('#target-language').value=c.target||'es';document.querySelector('#profile').value=c.profile;document.querySelector('#audio').value=c.source;document.querySelector('#chunks').value=c.chunk_words;for(const key of ['technical','draft','offline','pauses','fillers'])document.querySelector('#'+key).checked=Boolean(c[key]);document.querySelector('#terms').value=c.terms||'';document.querySelector('#save').checked=true;showCost()}catch(error){change(document.querySelector('#app-message'),error.message)}}
document.querySelector('#session-pane').ontoggle=function(){if(this.open)listSessions()};
document.querySelector('#sessions').onchange=()=>{selectedSession='';document.querySelector('#session-export').hidden=true};
document.querySelector('#load-session').onclick=loadSession;
document.querySelector('#resume-session').onclick=async()=>{await loadSession();if(selectedSession)control('start')};
document.querySelector('#rename-session').onclick=async()=>{try{const id=document.querySelector('#sessions').value;if(!id)return;const response=await fetch('rename',{method:'POST',headers:{'Content-Type':'application/json','X-Translator-Control':'1'},body:JSON.stringify({session_id:id,name:document.querySelector('#session-name').value})});const data=await response.json();if(!response.ok)throw Error(data.error);selectedSession=id;listSessions()}catch(error){change(document.querySelector('#app-message'),error.message)}};
async function control(action){
 if(busy)return;busy=true;document.querySelector('#start').disabled=document.querySelector('#stop').disabled=true;
 try{const config={language:document.querySelector('#speech-language').value,target:document.querySelector('#target-language').value,profile:document.querySelector('#profile').value,source:document.querySelector('#audio').value,chunk_words:Number(document.querySelector('#chunks').value),technical:document.querySelector('#technical').checked,terms:document.querySelector('#terms').value,draft:document.querySelector('#draft').checked,save:document.querySelector('#save').checked,offline:document.querySelector('#offline').checked};
 config.session_id=config.save?selectedSession:'';config.session_name=document.querySelector('#session-name').value;
 config.pauses=false;config.fillers=document.querySelector('#fillers').checked;
 const response=await fetch(action,{method:'POST',headers:{'Content-Type':'application/json','X-Translator-Control':'1'},body:JSON.stringify(config)});const data=await response.json();if(!response.ok)throw Error(data.error);
 if(data.session_id){selectedSession=data.session_id;listSessions()}
 if(action==='quit'){closedApp=true;cancelPoll();change(document.querySelector('#app-message'),'App cerrada. Puedes cerrar esta pestaña.')}
 }catch(error){change(document.querySelector('#app-message'),error.message)}finally{busy=false}
}
document.querySelector('#start').onclick=()=>control('start');document.querySelector('#stop').onclick=()=>control('stop');
document.querySelector('#shortcut').onclick=()=>control('shortcut');document.querySelector('#quit').onclick=()=>control('quit');
function appState(state){if(!state.app)return;const app=state.app;change(document.querySelector('#app-message'),app.message);
 if(!termsReady){document.querySelector('#terms').value=app.terms;termsReady=true}
 if(!busy){document.querySelector('#start').disabled=false;document.querySelector('#stop').disabled=!app.running}
 change(document.querySelector('#start'),app.running?'Aplicar y reiniciar':'Iniciar');
 document.querySelector('#export').hidden=!app.download;document.querySelector('#export').href='export';
 for(const option of document.querySelector('#profile').options)option.disabled=['whistle','ultralight'].includes(option.value)&&!app.whistle;
 document.querySelector('#fillers').disabled=!app.fillers;
}'''
def page():
 return PAGE.replace('<div><button id="floating">','<div><label>UI <select id="ui-language"><option value="es">Español</option><option value="en">English</option></select></label> <button id="floating">',1).replace('<p class="note">La última frase',CONTROLS+'<p class="note">La última frase',1).replace('async function refresh(){',CONTROL_JS+'\nasync function refresh(){',1).replace('if(polling)return;','if(polling||closedApp)return;',1).replace('const state=await response.json();','const state=await response.json();appState(state);',1)
def desktop_shortcut():
 directory=Path(os.environ.get('XDG_DATA_HOME',str(Path.home()/'.local/share')))/'applications'
 directory.mkdir(parents=True,exist_ok=True)
 target=directory/'local-live-translator.desktop'
 marker='X-Local-Translator-Managed=true'
 if target.exists() and marker not in target.read_text():raise ValueError('Ya existe otro acceso con ese nombre')
 executable=str(ROOT/'app.sh')
 if '\n' in executable or '\r' in executable:raise ValueError('Ruta no compatible con el acceso')
 for character in ('\\','"', '$',chr(96)):executable=executable.replace(character,'\\'+character)
 target.write_text('[Desktop Entry]\nType=Application\nName=Traductor local\nComment=Subtítulos y traducción local de audio\nExec="'+executable+'"\nIcon=accessories-dictionary\nTerminal=false\nCategories=AudioVideo;Audio;\n'+marker+'\n')
 target.chmod(0o644)
 return target
def validate(config):
 if not isinstance(config,dict) or config.get('profile') not in PROFILES or config.get('source') not in {'system','mic','both'}:raise ValueError('Modo o audio inválidos')
 if type(config.get('chunk_words')) is not int or config['chunk_words'] not in {12,18,26}:raise ValueError('Longitud inválida')
 if any(type(config.get(name)) is not bool for name in ('technical','draft','save','offline')):raise ValueError('Opción inválida')
 if any(type(config.get(name,False)) is not bool for name in ('pauses','fillers')):raise ValueError('Opción experimental inválida')
 if config.get('session_id') and (not isinstance(config['session_id'],str) or not re.fullmatch(r'[a-f0-9]{32}',config['session_id'])):raise ValueError('Sesión inválida')
 if config.get('session_id') and not config['save']:raise ValueError('Retomar requiere guardar')
 if config.get('language','en') not in {'en','es','de','fr','it','nl','pl'} or config.get('target','es') not in {'es','en','none'}:raise ValueError('Idioma inválido')
 if config.get('target','es')!='none' and (config.get('language','en'),config.get('target','es')) not in {('en','es'),('es','en')}:raise ValueError('Elige inglés a español o español a inglés')
 SessionStore(ROOT/'.runtime/app/sessions').name(config.get('session_name',''))
 if config.get('pauses'):raise ValueError('Las pausas experimentales requieren el CLI legacy')
 terms=config.get('terms','')
 if not isinstance(terms,str) or len(terms.encode())>8192 or len(terms.splitlines())>100 or '\0' in terms or any(len(term)>160 for term in terms.splitlines()):raise ValueError('Vocabulario inválido')
 return config
class Manager:
 def __init__(self,test_wav=None):
  self.lock=threading.RLock();self.process=None;self.child_url=None;self.log_path=None;self.counter=0;self.test_wav=test_wav
  self.sessions=SessionStore(ROOT/'.runtime/app/sessions');self.session_id=None;self.mix=None
  self.message='Elige un modo y pulsa Iniciar.'
  self.terms=(ROOT/'vocab/tech-example.txt').read_text()
  self.snapshot=dict(version=0,source='',preview='',translation='',spans=[],history=[],status='Detenido')
 def stop(self):
  with self.lock:
   process=self.process
   if process and process.poll() is None:
    for sig,timeout in [(signal.SIGINT,5),(signal.SIGTERM,2),(signal.SIGKILL,2)]:
     if process.poll() is not None:break
     try:os.killpg(process.pid,sig)
     except ProcessLookupError:break
     try:process.wait(timeout=timeout)
     except subprocess.TimeoutExpired:pass
   if self.mix:self.mix.close();self.mix=None
   self.child_url=None;self.message='Detenido. Puedes cambiar el modo y volver a iniciar.'
 def start(self,config):
  config=validate(config)
  if config.get('session_id'):self.sessions.read(config['session_id'])
  if config['profile'] in {'whistle','ultralight'} and not self.whistle():raise ValueError('Whistle no está preparado')
  if not self.test_wav and subprocess.run(['pactl','info'],capture_output=True).returncode:raise ValueError('No se detecta PulseAudio/PipeWire')
  if config.get('target','es')!='none' and config['profile']!='ultralight':
   pair=config.get('language','en')+'_'+config.get('target','es')
   if not (ROOT/'.runtime/translation'/pair/'metadata.json').is_file():raise ValueError('Falta traducción '+pair+'. Ejecuta python bin/install_translation.py --pair '+pair)
  with self.lock:
   self.stop();runtime=ROOT/'.runtime/app';runtime.mkdir(parents=True,exist_ok=True,mode=0o700)
   command=[str(ROOT/'run.sh')]+PROFILES[config['profile']]+['--source',config['source'],'--chunk-words',str(config['chunk_words']),'--min-phrase-words','6','--state-json']
   command+=['--lang',config.get('language','en'),'--to',config.get('language','en') if config.get('target')=='none' else config.get('target','es')]
   if config.get('target')=='none':command.append('--no-translate')
   if config['offline']:command.append('--offline')
   if config['draft']:command.append('--translation-preview')
   if config.get('pauses'):command+=['--utterance-pause','1.0']
   if config.get('fillers'):
    model=ROOT/'.runtime/disfluency-research/fdt-q8'
    if not model.is_dir():raise ValueError('Detector no preparado')
    command+=['--disfluency-model',str(model)]
   if config['technical']:
    path=runtime/'vocabulary.local.txt';path.write_text(config['terms']);path.chmod(0o600)
    command+=['--keywords',str(path)]
    if 'tmux' in config['terms'].splitlines():command+=['--term-aliases',str(ROOT/'vocab/tech-aliases.json')]
   self.log_path=None;self.session_id=None
   if config['save']:
    settings={k:v for k,v in config.items() if k not in {'session_id','session_name'}}
    saved=self.sessions.resume(config['session_id'],settings) if config.get('session_id') else self.sessions.create(config.get('session_name',''),settings)
    self.session_id=saved['id'];self.log_path=self.sessions.paths(self.session_id)[1]
    command+=['--save',str(self.log_path)]
   if self.test_wav:command+=['--input-wav',str(self.test_wav)]
   self.snapshot=dict(version=0,source='',preview='',translation='',spans=[],history=[],status='Cargando modelo…')
   self.message='Cargando modelo. Para descargar pesos por primera vez, desmarca Solo modelos descargados.'
   if config['source']=='both':
    command[command.index('--source')+1]='system'
    if not self.test_wav:
     self.mix=AudioMix();command+=['--device',self.mix.open()]
   try:self.process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
   except OSError:
    if self.mix:self.mix.close();self.mix=None
    raise
   self.child_url=None;threading.Thread(target=self.read_worker,args=(self.process,),daemon=True).start()
   threading.Thread(target=self.read_final,args=(self.process,),daemon=True).start()
 def whistle(self):return all((ROOT/'.runtime/whistle'/name).is_file() for name in ('needle','whistle.cact'))
 def read_final(self,process):
  for line in process.stdout:
   if not line.startswith('STATE_JSON:'):continue
   try:state=json.loads(line[len('STATE_JSON:'):])
   except ValueError:continue
   with self.lock:
    if process is self.process:self.snapshot=state;self.child_url=None
 def read_worker(self,process):
  for line in process.stderr:
   match=re.search(r'subtítulos:\s+(http://127\.0\.0\.1:\d+/[A-Za-z0-9_-]+/)',line)
   with self.lock:
    if process is not self.process:return
    if match:self.child_url=match.group(1)+'state';self.message='Capturando audio. Detener cierra solo esta sesión.'
  with self.lock:
   if process is self.process:
    self.message='Sesión finalizada.' if process.wait()==0 else 'El motor se detuvo. Revisa modelos y audio disponible o prueba otro modo.'
    if self.mix:self.mix.close();self.mix=None
 def state(self):
  with self.lock:url,process=self.child_url,self.process
  incoming=None
  if url:
   try:
    with urllib.request.urlopen(url,timeout=1) as response:incoming=json.load(response)
   except (OSError,ValueError):pass
  with self.lock:
   if incoming and url==self.child_url:self.snapshot=incoming
   self.counter+=1;result=dict(self.snapshot);result['version']=self.counter
   if not process or process.poll() is not None:result['status']='Detenido'
   result['app']=dict(running=bool(process and process.poll() is None),message=self.message,terms=self.terms,download=bool(self.log_path and self.log_path.exists()),whistle=self.whistle(),fillers=(ROOT/'.runtime/disfluency-research/fdt-q8/model.onnx').is_file())
   return result
def serve(manager,port=0):
 base='/'+secrets.token_urlsafe(24)+'/'
 class Handler(BaseHTTPRequestHandler):
  def reply(self,status,body,kind='application/json'):
   if kind=='application/json':body=json.dumps(body,ensure_ascii=False).encode()
   elif isinstance(body,str):body=body.encode()
   self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
   if self.path==base+'export' or self.path.endswith('/export'):self.send_header('Content-Disposition','attachment; filename="transcription.txt"')
   self.end_headers();self.wfile.write(body)
  def do_GET(self):
   if self.path==base:self.reply(200,page(),'text/html; charset=utf-8')
   elif self.path==base+'sessions':self.reply(200,{'sessions':manager.sessions.list()})
   elif self.path.startswith(base+'session/'):
    try:
     tail=self.path[len(base+'session/'):];identity=tail.split('/')[0]
     data=manager.sessions.content(identity)
     if tail==identity:self.reply(200,data)
     elif tail==identity+'/export':self.reply(200,manager.sessions.paths(identity)[1].read_bytes(),'text/plain; charset=utf-8')
     else:self.reply(404,{'error':'No disponible'})
    except (OSError,ValueError):self.reply(404,{'error':'Sesión no disponible'})
   elif self.path==base+'state':self.reply(200,manager.state())
   elif self.path==base+'export' and manager.log_path and manager.log_path.exists():self.reply(200,manager.log_path.read_bytes(),'text/plain; charset=utf-8')
   else:self.reply(404,{'error':'No disponible'})
  def do_POST(self):
   if self.headers.get('Origin')!=f'http://127.0.0.1:{self.server.server_port}' or self.headers.get('X-Translator-Control')!='1':self.reply(403,{'error':'Control permitido solo desde la aplicación local'});return
   if self.path not in {base+'start',base+'stop',base+'shortcut',base+'quit',base+'rename'}:self.reply(404,{'error':'No disponible'});return
   try:
    length=int(self.headers.get('Content-Length','0'))
    if not 0<length<=16384:raise ValueError('Petición inválida')
    config=json.loads(self.rfile.read(length))
    if self.path==base+'start':manager.start(config)
    elif self.path==base+'rename':manager.sessions.rename(config.get('session_id'),config.get('name'))
    elif self.path==base+'shortcut':
     desktop_shortcut();manager.message='Acceso creado. Busca Traductor local en el menú de aplicaciones.'
    else:manager.stop()
    self.reply(200,{'ok':True,'session_id':getattr(manager,'session_id',None)})
    if self.path==base+'quit':threading.Thread(target=self.server.shutdown,daemon=True).start()
   except (ValueError,OSError,subprocess.SubprocessError):
    manager.message='No se pudo iniciar. Revisa opciones, vocabulario, entorno Python y audio disponible.'
    self.reply(400,{'error':manager.message})
  def log_message(self,*_):pass
 return ThreadingHTTPServer(('127.0.0.1',port),Handler),base
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--no-browser',action='store_true');parser.add_argument('--install-shortcut',action='store_true');parser.add_argument('--test-wav',type=Path,help='verificación local; no disponible en el formulario')
 args=parser.parse_args()
 if args.install_shortcut:desktop_shortcut();print('Acceso creado: Traductor local');return
 def interrupt(*_):raise KeyboardInterrupt
 signal.signal(signal.SIGTERM,interrupt)
 if hasattr(signal,'SIGHUP'):signal.signal(signal.SIGHUP,interrupt)
 manager=Manager(args.test_wav);server,base=serve(manager);url=f'http://127.0.0.1:{server.server_port}{base}';print(url,flush=True)
 if not args.no_browser:
  import webbrowser
  webbrowser.open(url)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:manager.stop();server.server_close()
if __name__=='__main__':main()
