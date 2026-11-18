import json
from pathlib import Path
import tempfile
import unittest

from .manifest import Catalog, TrackerError, alias_key, catalog_entries, load_changes, parse_change
from .store import timestamp


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = Catalog.load()

    def change(self, **changes):
        return dict(projectKey='qa-project', milestoneKey='research-report', expectedRevision=0,
                    issueId='stored-edition', issueHash='a' * 64, storyId='stored-story',
                    companies=[' ＳＩＥＭＥＮＳ ', '西门子'], technologies=[' \tPhysical    AI '], **changes)

    def test_alias_resolution_deduplicates_without_guessing_and_ids_are_opaque(self):
        manifest = self.change()
        resolved = parse_change(manifest, self.catalog)
        self.assertEqual(resolved.companies, ('siemens',))
        self.assertEqual(resolved.technologies, ('physical-ai',))
        self.assertRegex(resolved.project_id, r'^project-[a-f0-9]{24}$')
        self.assertRegex(resolved.milestone_id, r'^milestone-[a-f0-9]{24}$')
        same = parse_change({**manifest, 'companies': ['Siemens']}, self.catalog)
        self.assertEqual(same.revision_id, resolved.revision_id)
        self.assertEqual(alias_key(' ＡＢＢ  '), 'abb')
        with self.assertRaises(TrackerError):
            parse_change({**manifest, 'companies': ['Siemen']}, self.catalog)

    def test_expected_revision_and_evidence_bind_each_operation(self):
        manifest = self.change()
        first = parse_change(manifest, self.catalog)
        correction = parse_change({**manifest, 'expectedRevision': 1, 'sourceRoles': {'s1': 'vendor'}}, self.catalog)
        withdrawal = parse_change({key: value for key, value in manifest.items() if key in {'projectKey', 'milestoneKey'}}
                                  | {'expectedRevision': 2, 'withdraw': True}, self.catalog)
        self.assertEqual(first.milestone_id, withdrawal.milestone_id)
        self.assertEqual(len({first.revision_id, correction.revision_id, withdrawal.revision_id}), 3)
        self.assertTrue(withdrawal.withdraw)

    def test_rejects_bad_revision_hash_role_and_free_text(self):
        manifest = self.change()
        for invalid in ({'expectedRevision': True}, {'expectedRevision': -1}, {'issueHash': 'a' * 63},
                        {'sourceRoles': {'s1': 'assumed'}}, {'withdraw': True}, {'stage': 'pilot'},
                        {'summary': {'en': 'private text', 'zh': '原文'}}):
            with self.subTest(invalid=invalid), self.assertRaises(TrackerError):
                parse_change({**manifest, **invalid}, self.catalog)

    def test_json_duplicates_and_alias_collisions_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / 'manifest.json'
            file.write_text('{"version":1,"version":1,"changes":[]}', encoding='utf-8')
            with self.assertRaisesRegex(TrackerError, 'duplicate keys'):
                load_changes(file, self.catalog)
            file.write_text(json.dumps({'version': 1, 'changes': [self.change()]}), encoding='utf-8')
            self.assertEqual(len(load_changes(file, self.catalog)), 1)
        with self.assertRaisesRegex(TrackerError, 'ambiguous alias'):
            catalog_entries({'companies': [
                {'id': 'one', 'name': {'en': 'One', 'zh': '甲'}, 'aliases': ['测试']},
                {'id': 'two', 'name': {'en': 'Two', 'zh': '乙'}, 'aliases': ['测试']},
            ]}, 'companies')

    def test_canonical_timestamps_require_explicit_timezone_and_allow_unknown_event(self):
        self.assertIsNone(timestamp(None))
        self.assertEqual(timestamp('2026-11-12T00:30:00+01:00'), timestamp('2026-11-11T23:30:00Z'))
        with self.assertRaises(TrackerError):
            timestamp('2026-11-12T00:30:00')


if __name__ == '__main__':
    unittest.main()
