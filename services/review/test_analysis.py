"""Heuristic regression tests use artificial evidence, never actual approvals."""
from copy import deepcopy
import unittest
from services.review.analysis import analyze, suggest


def issue():
    evidence='The laboratory tested an industrial inspection prototype with 12 cameras. The result remains a prototype.'
    zh='\u5b9e\u9a8c\u5ba4\u6d4b\u8bd5\u4e86\u4e00\u4e2a\u5de5\u4e1a\u68c0\u6d4b\u539f\u578b\uff0c\u4f7f\u7528\u4e86 12 \u4e2a\u76f8\u673a\u3002\u8be5\u7cfb\u7edf\u4ecd\u4e3a\u539f\u578b\u3002'
    text={'en':evidence,'zh':zh}
    return {'id':'artificial-issue','title':dict(text),'introduction':dict(text),
        'sources':[{'id':'s1','excerpt':dict(text)}],
        'stories':[{'id':'story1','sourceIds':['s1'],'title':dict(text),'summary':dict(text),
                    'why':{'en':'Independent analysis remains a human judgment.','zh':'\u72ec\u7acb\u5206\u6790\u9700\u8981\u4eba\u5de5\u5224\u65ad\u3002'},'limitation':dict(text)}]}


class AnalysisTests(unittest.TestCase):
    def test_copied_bilingual_story_and_issue_expression_is_flagged_without_certification(self):
        findings=analyze(issue())
        self.assertTrue(any(f['kind']=='copied_passage' and '.zh' in f['reason'] for f in findings))
        self.assertTrue(any(f['kind']=='translated_dependence' for f in findings))
        self.assertTrue(any(f['storyId']=='issue:artificial-issue' for f in findings))
        self.assertTrue(any(f['kind']=='human_fact_review' for f in findings))
        self.assertEqual(len({f['id'] for f in findings}),len(findings))

    def test_findings_are_deterministic_and_full_revision_bound(self):
        value=issue();before=deepcopy(value)
        first=analyze(value);self.assertEqual(first,analyze(value));self.assertEqual(value,before)
        value['privateEvidence']='changed'
        self.assertTrue(set(f['id'] for f in first).isdisjoint(f['id'] for f in analyze(value)))

    def test_unsupported_metrics_and_missing_citations_require_review(self):
        value=issue();value['stories'][0]['summary']['en']='The system achieved 99% improvement with 50 cameras.'
        value['stories'][0]['sourceIds']=['missing']
        findings=analyze(value)
        self.assertTrue(any(f['kind']=='missing_citation' for f in findings))
        self.assertTrue(any(f['kind']=='unsupported_number' and '99%' in f['reason'] for f in findings))

    def test_nested_unknown_assets_and_near_copy_raise_prompts(self):
        value=issue();value['stories'][0]['private']={'images':['unreviewed.png']}
        value['stories'][0]['summary']['en']='The laboratory assessed an industrial inspection prototype with 12 cameras. The result remains a prototype.'
        kinds={f['kind'] for f in analyze(value)}
        self.assertIn('asset_review',kinds)
        self.assertTrue({'copied_passage','near_copied_passage'} & kinds)

    def test_guidance_is_unapplied_bilingual_placeholders_not_a_copied_draft(self):
        value=issue();before=deepcopy(value);guidance=suggest(value)['story1']
        self.assertEqual(value,before)
        self.assertIn('s1',guidance['en']);self.assertIn('[',guidance['zh'])
        self.assertIn('NOT A FACTUAL ARTICLE OR APPROVAL',guidance['en']);self.assertIn('Lede template:',guidance['en'])
        self.assertNotIn(value['sources'][0]['excerpt']['en'],guidance['en'])
        self.assertNotIn('99%',guidance['en'])

    def test_nonjson_and_oversize_inputs_fail_before_analysis(self):
        for bad in (None,{'sources':[],'stories':None},dict(issue(),extra=float('nan')),dict(issue(),extra='x'*(3*1024*1024))):
            with self.subTest(kind=type(bad)),self.assertRaises(ValueError): analyze(bad)


if __name__=='__main__':unittest.main()
