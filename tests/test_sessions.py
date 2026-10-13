import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bin'))
from sessions import SessionStore

class SessionTests(unittest.TestCase):
    def test_resume_keeps_transcript_and_rename_survives_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            store=SessionStore(directory)
            saved=store.create('Meeting',{'profile':'base'})
            transcript=store.paths(saved['id'])[1]
            transcript.write_text('[10:00] Public fixture\n -> Traducción\n')
            store.resume(saved['id'],{'profile':'small'})
            store.rename(saved['id'],'Class')
            reopened=SessionStore(directory)
            self.assertEqual(reopened.list()[0]['name'],'Class')
            self.assertIn('Public fixture',reopened.content(saved['id'])['transcript'])
            self.assertEqual(reopened.read(saved['id'])['config']['profile'],'small')
            self.assertEqual(transcript.stat().st_mode & 0o777,0o600)

    def test_concurrent_renames_keep_valid_metadata(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as directory:
            store=SessionStore(directory);saved=store.create('Fixture',{})
            with ThreadPoolExecutor(max_workers=8) as workers:
                list(workers.map(lambda n:store.rename(saved['id'],'Fixture '+str(n)),range(32)))
            self.assertTrue(store.read(saved['id'])['name'].startswith('Fixture '))
            self.assertFalse(list(Path(directory).glob('*.tmp')))

    def test_paths_and_symlinks_do_not_escape_session_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            store=SessionStore(directory)
            with self.assertRaises(ValueError):store.content('../outside')
            saved=store.create('Example',{})
            metadata,transcript=store.paths(saved['id'])
            transcript.unlink();transcript.symlink_to(metadata)
            with self.assertRaises(ValueError):store.content(saved['id'])

    def test_unsaved_store_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'sessions'
            self.assertEqual(SessionStore(root).list(),[])
            self.assertFalse(root.exists())
