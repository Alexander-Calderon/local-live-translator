import json,sys,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bin'))
from caption_view import CaptionView
from vocabulary import PreserveTerms,read_aliases
from app import serve,validate,desktop_shortcut
from unittest.mock import patch
import os
import queue
import listen

class AppTests(unittest.TestCase):
 def test_capture_failure_ends_the_audio_queue(self):
  q=queue.Queue()
  with patch.object(listen.subprocess,'Popen',side_effect=OSError('device unavailable')):
   with self.assertRaises(OSError):listen.capture('fake-device',q)
  self.assertIsNone(q.get_nowait())
 def test_shortcut_is_scoped_and_does_not_overwrite_another_launcher(self):
  with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'XDG_DATA_HOME':directory}):
   target=desktop_shortcut()
   self.assertIn('Terminal=false',target.read_text())
   self.assertIn('X-Local-Translator-Managed=true',target.read_text())
   target.write_text('Another launcher')
   with self.assertRaises(ValueError):desktop_shortcut()
   self.assertEqual(target.read_text(),'Another launcher')
 def test_short_fragments_wait_but_negative_reply_is_kept(self):
  previous=listen.MIN_SENTENCE_WORDS
  try:
   listen.MIN_SENTENCE_WORDS=6
   out=listen.Output.__new__(listen.Output)
   out.pending='And so my fellow Americans. ask not.'
   self.assertEqual(out._cut(),-1)
   out.pending='No.'
   self.assertEqual(out._cut(),3)
   out.pending='We should not.'
   self.assertEqual(out._cut(),-1)
  finally:listen.MIN_SENTENCE_WORDS=previous
 def test_confirmed_translation_survives_new_speech_and_late_results(self):
  view=CaptionView()
  try:
   first=view.begin('First sentence.');view.finish(first,'Primera frase.')
   view.current('Second','provisional');view.draft('Borrador cambiante')
   self.assertEqual(view.state['translation'],'Primera frase.')
   second=view.begin('Second sentence.');view.finish(second,'Segunda frase.')
   view.finish(first,'Resultado antiguo')
   self.assertEqual(view.state['translation'],'Segunda frase.')
   self.assertEqual(view.state['translation_source'],'Second sentence.')
  finally:view.close()
 def test_aliases_are_exact_and_original_remains_available(self):
  translate=PreserveTerms(lambda text:text,['tmux'],{'T mux':'tmux','T-mux':'tmux'})
  self.assertEqual(translate('Use T mux here.'),'Use tmux here.')
  self.assertEqual(translate('Two mocks and T max.'),'Two mocks and T max.')
 def test_alias_target_must_be_in_glossary(self):
  with tempfile.TemporaryDirectory() as directory:
   file=Path(directory)/'terms.json';file.write_text('{"wrong":"unknown"}')
   with self.assertRaises(ValueError):read_aliases(file,['tmux'])
 def test_http_controls_reject_cross_origin_and_bad_profiles(self):
  class FakeManager:
   calls=0
   log_path=None
   def state(self):return {'version':0,'app':{}}
   def start(self,config):validate(config);self.calls+=1
   def stop(self):self.calls+=1
  manager=FakeManager();server,base=serve(manager)
  thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  url=f'http://127.0.0.1:{server.server_port}'
  config=dict(profile='base',source='system',chunk_words=18,technical=False,terms='',draft=False,save=False,offline=True)
  try:
   for origin,profile,code in [('https://example.com','base',403),(url,'arbitrary shell',400),(url,'base',200)]:
    config['profile']=profile
    request=urllib.request.Request(url+base+'start',data=json.dumps(config).encode(),headers={'Origin':origin,'Content-Type':'application/json','X-Translator-Control':'1'})
    try:
     with urllib.request.urlopen(request) as response:self.assertEqual(response.status,code)
    except urllib.error.HTTPError as error:self.assertEqual(error.code,code)
   self.assertEqual(manager.calls,1)
  finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main()
