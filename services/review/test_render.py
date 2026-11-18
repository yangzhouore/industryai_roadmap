"""Private/offline report boundaries using only artificial or demo content."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree
from services.review.analysis import analyze,suggest
from services.review.render import render_review,render_preview

ROOT=Path(__file__).resolve().parents[2]


def fixture():
    return json.loads((ROOT/'packages/shared/fixtures/issues.json').read_text(encoding='utf-8'))[0]


def public_fixture():
    value=fixture()
    for source in value['sources']:del source['excerpt']
    return value


class RenderTests(unittest.TestCase):
    def test_private_review_escapes_malicious_evidence_and_displays_bilingual_records(self):
        value=fixture();value['sources'][0]['excerpt']={'en':'<script>alert(1)</script>PRIVATE_SENTINEL','zh':'\u79c1\u6709\u8bc1\u636e'}
        value['stories'][0]['summary']['en']='<img src=https://remote.test/x onerror=alert(1)>'
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'review';result=render_review(value,analyze(value),suggest(value),out)
            html=(out/'index.html').read_text(encoding='utf-8')
            self.assertEqual(result['files'],['index.html'])
            self.assertIn('PRIVATE_SENTINEL',html);self.assertIn('\u79c1\u6709\u8bc1\u636e',html)
            self.assertIn('&lt;script&gt;',html);self.assertNotIn('<script',html);self.assertNotIn('<img',html)
            self.assertIn("default-src &#x27;none&#x27;",html)
            self.assertIn('Citation mapping',html);self.assertIn('All scope findings',html)
            if os.name!='nt':self.assertEqual((out/'index.html').stat().st_mode&0o777,0o600)

    def test_unapproved_preview_is_withheld_everywhere_and_empty_rss(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'withheld';result=render_preview(None,out)
            self.assertEqual(len(result['files']),11)
            for locale in ('en','zh'):
                for name in ('index.html','digest.html','sources.html','archive.html'):
                    text=(out/locale/name).read_text(encoding='utf-8')
                    self.assertTrue('WITHHELD' in text or '\u672a\u901a\u8fc7' in text)
                    self.assertNotIn('PRIVATE_SENTINEL',text)
                self.assertEqual(ElementTree.parse(out/locale/'rss.xml').findall('./channel/item'),[])

    def test_projected_demo_preview_contains_no_source_excerpts_or_remote_embeds(self):
        value=public_fixture()
        for n,story in enumerate(value['stories']): story['summary']={'en':'Original editable context '+str(n),'zh':'\u539f\u521b\u7f16\u8f91\u80cc\u666f '+str(n)}
        before=deepcopy(value)
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'preview';render_preview(value,out)
            alltext='\n'.join(p.read_text(encoding='utf-8') for p in out.rglob('*') if p.is_file())
            self.assertEqual(value,before)
            self.assertIn('DEMONSTRATION',alltext);self.assertNotIn('<script',alltext);self.assertNotIn('<img',alltext)
            self.assertIn(value['stories'][0]['summary']['en'],alltext)
            for source in fixture()['sources']:
                self.assertNotIn(source['excerpt']['en'],alltext)
            self.assertEqual(len(ElementTree.parse(out/'en/rss.xml').findall('./channel/item')),1)

    def test_private_or_unknown_nested_fields_are_rejected_before_output_creation(self):
        for mutate in (lambda i:i['sources'][0].update(excerpt={'en':'PRIVATE','zh':'PRIVATE'}),
                       lambda i:i.update(assets=['PRIVATE']),lambda i:i['stories'][0]['summary'].update(extra='PRIVATE'),
                       lambda i:i.update(id={'private':'PRIVATE'})):
            value=public_fixture();mutate(value)
            with tempfile.TemporaryDirectory() as folder:
                out=Path(folder)/'unsafe'
                with self.assertRaises(ValueError):render_preview(value,out)
                self.assertFalse(out.exists())

    def test_outputs_never_overwrite_and_public_paths_are_forbidden(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)/'review';render_preview(None,out)
            before=(out/'index.html').read_bytes()
            with self.assertRaises(ValueError):render_preview(None,out)
            self.assertEqual((out/'index.html').read_bytes(),before)
            for tail in ('public/report','www/report','apps/web/report','.next/report','private/../report'):
                with self.subTest(tail=tail),self.assertRaises(ValueError):render_preview(None,Path(folder)/tail)

    def test_repository_reports_cannot_enter_tracked_source_directories(self):
        out=ROOT/'docs'/'must-not-create-private-review'
        self.assertFalse(out.exists())
        with self.assertRaises(ValueError):render_preview(None,out)
        self.assertFalse(out.exists())

    @unittest.skipIf(os.name=='nt','Windows symlink creation depends on host privilege; Linux CI exercises this boundary')
    def test_parent_symlinks_cannot_redirect_report_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'real').mkdir();(root/'redirect').symlink_to(root/'real',target_is_directory=True)
            with self.assertRaises(ValueError):render_preview(None,root/'redirect'/'report')
            self.assertFalse((root/'real'/'report').exists())


if __name__=='__main__':unittest.main()
