"""Behavioral checks for metadata, path boundaries, and editable records."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('archive', Path(__file__).resolve().parents[1] / 'scripts/build_archive.py')
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.content = self.root / 'archive-content'
        self.section = self.content / '00-scope'
        self.section.mkdir(parents=True)
        (self.section / '_section.json').write_text(json.dumps({'title':'Scope', 'description':'Project scope'}))
        self.file = self.section / 'notes.txt'
        self.file.write_text('Initial observations')
        self.meta = self.section / 'notes.txt.meta.json'
        self.data = {'id':'scope-v1', 'title':'Scope note', 'created':'2026-10-26',
                     'description':'A test note', 'researchers':['Derek'], 'tags':['scope']}
        self.write_meta()

    def write_meta(self):
        self.meta.write_text(json.dumps(self.data))

    def test_manifest_preserves_credits_and_hashes_actual_file(self):
        manifest = archive.build_manifest(self.content)
        record = manifest['records'][0]
        self.assertEqual(record['researchers'], ['Derek'])
        self.assertEqual(record['file']['sha256'], archive.hashlib.sha256(self.file.read_bytes()).hexdigest())
        self.assertEqual(record['file']['path'], 'archive-content/00-scope/notes.txt')

    def test_unlisted_file_is_rejected(self):
        (self.section / 'forgotten.csv').write_text('x,y\n1,2')
        with self.assertRaisesRegex(ValueError, 'without metadata'):
            archive.build_manifest(self.content)

    def test_preview_and_revision_relationship(self):
        self.data['preview'] = 'notes.preview.pdf'
        (self.section / 'notes.preview.pdf').write_bytes(b'%PDF-1.4\n')
        self.write_meta()
        self.assertEqual(archive.build_manifest(self.content)['records'][0]['preview']['extension'], 'pdf')
        self.data['supersedes'] = 'nonexistent'
        self.write_meta()
        with self.assertRaisesRegex(ValueError, 'target does not exist'):
            archive.build_manifest(self.content)

    def test_invalid_date_and_duplicate_id(self):
        self.data['created'] = '2026-02-30'
        self.write_meta()
        with self.assertRaises(ValueError):
            archive.build_manifest(self.content)
        self.data['created'] = '2026-10-26'
        self.write_meta()
        (self.section / 'other.txt').write_text('More notes')
        (self.section / 'other.txt.meta.json').write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError, 'unique id'):
            archive.build_manifest(self.content)

    def test_symlinks_and_escaped_preview_rejected(self):
        self.data['preview'] = '../secret.pdf'
        self.write_meta()
        with self.assertRaisesRegex(ValueError, 'same folder'):
            archive.build_manifest(self.content)
        self.data.pop('preview')
        self.write_meta()
        (self.section / 'link.txt').symlink_to(self.file)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            archive.build_manifest(self.content)

    def test_json_notes_can_have_metadata(self):
        (self.section / 'data.json').write_text('{"sample":1}')
        data = dict(self.data, id='json-data')
        (self.section / 'data.json.meta.json').write_text(json.dumps(data))
        self.assertEqual(len(archive.build_manifest(self.content)['records']), 2)

    def test_version_cycle_rejected(self):
        self.data['supersedes'] = self.data['id']
        self.write_meta()
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            archive.build_manifest(self.content)

    def test_ids_allow_underscores_without_changing_deep_links(self):
        self.data['id'] = 'team_charter_team25'
        self.write_meta()
        self.assertEqual(archive.build_manifest(self.content)['records'][0]['id'], 'team_charter_team25')

    def test_existing_records_can_be_edited_renamed_and_deleted(self):
        original = archive.build_manifest(self.content)['records'][0]
        self.file.write_text('Revised observations')
        self.data['description'] = 'Updated analysis'
        self.write_meta()
        edited = archive.build_manifest(self.content)['records'][0]
        self.assertNotEqual(edited['file']['sha256'], original['file']['sha256'])
        self.assertEqual(edited['description'], 'Updated analysis')
        self.assertEqual(edited['id'], original['id'])
        renamed = self.section / 'renamed-notes.txt'
        renamed_meta = self.section / 'renamed-notes.txt.meta.json'
        self.file.rename(renamed)
        self.meta.rename(renamed_meta)
        current = archive.build_manifest(self.content)['records'][0]
        self.assertEqual(current['file']['name'], 'renamed-notes.txt')
        self.assertEqual(current['id'], original['id'])
        renamed.unlink()
        renamed_meta.unlink()
        self.assertEqual(archive.build_manifest(self.content)['records'], [])


if __name__ == '__main__':
    unittest.main()
