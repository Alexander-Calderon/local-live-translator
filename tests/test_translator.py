import sys,unittest,tempfile,re,importlib.util,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'bin'))
from vocabulary import read_keywords,WhisperVocabulary,PreserveTerms
import listen
import install_translation

class VocabularyTests(unittest.TestCase):
    def test_hints_keep_backend_options(self):
        class Model:
            def transcribe(self,*args,**kwargs):return kwargs
        opts=WhisperVocabulary(Model(),['Excalidraw']).transcribe(None,beam_size=3)
        self.assertEqual(opts,{'beam_size':3,'hotwords':'Excalidraw'})
    def test_preserve_terms_and_boundaries(self):
        translation=PreserveTerms(lambda text:text,['Warp Terminal','GitHub Actions'])
        self.assertEqual(translation('warp terminal uses GitHub Actions'),'Warp Terminal uses GitHub Actions')
        self.assertEqual(translation('GitHub ActionsExtra'),'GitHub ActionsExtra')
    def test_bad_marker_falls_back(self):
        translation=PreserveTerms(lambda text:text.replace('QZTERM0ZQ',''),['Excalidraw'])
        self.assertEqual(translation('Use Excalidraw'),'Use Excalidraw')
        self.assertEqual(translation.fallbacks,1)
    def test_caption_term_not_split(self):
        previous=listen.VOCABULARY_PATTERN
        try:
            listen.VOCABULARY_PATTERN=PreserveTerms(lambda text:text,['GitHub Actions']).pattern
            # No worker/server is needed to test sentence boundary policy.
            output=listen.Output.__new__(listen.Output)
            output.pending='word '*21+'GitHub Actions and more words'
            self.assertTrue(output.pending[:output._cut()].endswith('GitHub Actions'))
            output.pending='Mr. Quilter uses version 3.12.'
            self.assertEqual(output._cut(),len(output.pending))
        finally:listen.VOCABULARY_PATTERN=previous
    def test_bounded_file_and_unique_terms(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'terms.txt';path.write_text('Excalidraw\nExcalidraw\nWarp Terminal\n')
            self.assertEqual(read_keywords(path),['Excalidraw','Warp Terminal'])
            path.write_text('x'*8200)
            with self.assertRaises(ValueError):read_keywords(path)
    def test_zip_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            archive=Path(directory)/'bad.zip'
            with zipfile.ZipFile(archive,'w') as bundle:bundle.writestr('../outside.txt','x')
            with self.assertRaises(ValueError):install_translation.safe_extract(archive,Path(directory)/'unpacked')

if __name__=='__main__':unittest.main()
