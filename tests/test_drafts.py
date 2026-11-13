import json
from pathlib import Path
import tempfile
import unittest
from services.pipeline.store import Store

class DraftTests(unittest.TestCase):
    def test_unverified_draft_never_public_and_never_overwrites_published(self):
        issue=json.loads(Path('packages/shared/fixtures/issues.json').read_text(encoding='utf-8'))[0]
        with tempfile.TemporaryDirectory() as directory:
            store=Store(str(Path(directory)/'test.sqlite'))
            try:
                store.save_draft(issue)
                self.assertEqual(store.published(),[])
                self.assertTrue(store.publish(issue))
                changed=dict(issue,title={'en':'unverified correction','zh':'unverified'})
                store.save_draft(changed)
                self.assertEqual(store.published()[0]['title'],issue['title'])
            finally:
                store.close()
