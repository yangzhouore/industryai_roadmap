"""Exact Berlin-day boundaries and append-only PostgreSQL correction history."""
import copy
from datetime import timedelta
import json
import os
from pathlib import Path
import unittest
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import uuid4
from packages.db.audit_backfill import day_bounds, eligible_on_day
from packages.db.revisions import archive_current_issue

ROOT = Path(__file__).resolve().parents[1]
DATABASE = os.getenv('TEST_DATABASE_URL','')


class BackfillDateTests(unittest.TestCase):
    def test_november_berlin_midnight_is_previous_utc_evening(self):
        self.assertTrue(eligible_on_day('2026-10-31T23:00:00Z','2026-11-01'))
        self.assertFalse(eligible_on_day('2026-10-31T22:59:59Z','2026-11-01'))
        self.assertTrue(eligible_on_day('2026-11-01T22:59:59Z','2026-11-01'))
        self.assertFalse(eligible_on_day('2026-11-01T23:00:00Z','2026-11-01'))

    def test_explicit_offset_uses_the_same_instant(self):
        self.assertTrue(eligible_on_day('2026-11-13T00:00:00+01:00','2026-11-13'))
        self.assertFalse(eligible_on_day('2026-11-14T00:00:00+01:00','2026-11-13'))

    def test_dst_days_have_exact_calendar_boundaries(self):
        begin,end=day_bounds('2026-03-29')
        self.assertEqual(end-begin,timedelta(hours=23))
        begin,end=day_bounds('2026-10-25')
        self.assertEqual(end-begin,timedelta(hours=25))

    def test_naive_timestamps_and_off_day_old_news_are_ineligible(self):
        with self.assertRaisesRegex(ValueError,'timezone'):
            eligible_on_day('2026-11-13T12:00:00','2026-11-13')
        self.assertFalse(eligible_on_day('2026-10-21T10:20:00Z','2026-11-13'))


@unittest.skipUnless(DATABASE.startswith(('postgresql://','postgres://')),'TEST_DATABASE_URL required')
class EditionRevisionTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        self.admin=psycopg.connect(DATABASE,autocommit=True)
        self.schema='revision_test_'+uuid4().hex
        self.addCleanup(self.cleanup_schema)
        self.admin.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public')
        self.admin.execute('CREATE SCHEMA '+self.schema)
        parts=urlsplit(DATABASE)
        params=[(k,v) for k,v in parse_qsl(parts.query) if k!='options']
        params.append(('options','-c search_path='+self.schema+',public'))
        location=urlunsplit(parts._replace(query=urlencode(params,quote_via=quote)))
        self.db=psycopg.connect(location,autocommit=True)
        for migration in sorted((ROOT/'packages/db/prisma/migrations').glob('*/migration.sql')):
            self.db.execute(migration.read_text(encoding='utf-8'),prepare=False)
        self.issue=json.loads((ROOT/'packages/shared/fixtures/issues.json').read_text(encoding='utf-8'))[0]
        from psycopg.types.json import Jsonb
        self.db.execute('''INSERT INTO issues(id,slug,issue_date,state,validated,content,published_at)
            VALUES(%s,%s,%s,'published',true,%s,now())''',
            (self.issue['id'],self.issue['slug'],self.issue['date'],Jsonb(self.issue)))

    def cleanup_schema(self):
        if hasattr(self,'db'):
            self.db.close()
        self.admin.execute('DROP SCHEMA IF EXISTS '+self.schema+' CASCADE')
        self.admin.close()

    def test_requires_caller_transaction_and_published_current_version(self):
        with self.assertRaisesRegex(ValueError,'transaction'):
            archive_current_issue(self.db,self.issue['id'])
        with self.db.transaction():
            with self.assertRaisesRegex(ValueError,'missing'):
                archive_current_issue(self.db,'missing')
        self.db.execute("UPDATE issues SET state='draft',validated=false WHERE id=%s",(self.issue['id'],))
        with self.db.transaction():
            with self.assertRaisesRegex(ValueError,'published'):
                archive_current_issue(self.db,self.issue['id'])

    def test_archive_exact_content_and_matching_persisted_receipt(self):
        from services.pipeline.verification.review import issue_digest
        from psycopg.types.json import Jsonb
        receipt={'issueHash':issue_digest(self.issue),'historicalDay':False,'testAudit':'original'}
        self.db.execute('''INSERT INTO pipeline_runs(id,mode,status,stage,stats)
            VALUES('original-review','live','verified','publication',%s)''',
            (Jsonb({'issueId':self.issue['id'],'review':receipt}),))
        with self.db.transaction():
            revision=archive_current_issue(self.db,self.issue['id'],expected_content=self.issue)
        self.assertEqual(revision,1)
        row=self.db.execute('SELECT content,review FROM edition_revisions').fetchone()
        self.assertEqual(row,(self.issue,receipt))
        self.assertEqual(self.db.execute('SELECT content FROM issues').fetchone()[0],self.issue)

    def test_failed_replacement_rolls_back_archive_and_current_content(self):
        from psycopg.types.json import Jsonb
        changed=copy.deepcopy(self.issue)
        changed['title']['en']='Replacement must roll back'
        with self.assertRaisesRegex(RuntimeError,'injected'):
            with self.db.transaction():
                archive_current_issue(self.db,self.issue['id'])
                self.db.execute('UPDATE issues SET content=%s WHERE id=%s',(Jsonb(changed),self.issue['id']))
                raise RuntimeError('injected replacement failure')
        self.assertEqual(self.db.execute('SELECT count(*) FROM edition_revisions').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT content FROM issues').fetchone()[0],self.issue)

    def test_append_only_trigger_and_positive_revision_constraint(self):
        import psycopg
        with self.db.transaction():
            archive_current_issue(self.db,self.issue['id'])
        for query in ('UPDATE edition_revisions SET review=review','DELETE FROM edition_revisions'):
            with self.assertRaises(psycopg.errors.ObjectNotInPrerequisiteState):
                self.db.execute(query)
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.db.execute("INSERT INTO edition_revisions VALUES('bad','bad',0,'{}','{}',now())")

    def test_changed_expected_content_or_wrong_review_hash_cannot_archive(self):
        changed=copy.deepcopy(self.issue)
        changed['title']['en']='Different content'
        with self.db.transaction():
            with self.assertRaisesRegex(ValueError,'changed'):
                archive_current_issue(self.db,self.issue['id'],expected_content=changed)
            with self.assertRaisesRegex(ValueError,'does not match'):
                archive_current_issue(self.db,self.issue['id'],review={'issueHash':'wrong'})
        self.assertEqual(self.db.execute('SELECT count(*) FROM edition_revisions').fetchone()[0],0)

    def test_sequential_archives_retain_each_exact_previous_version(self):
        from psycopg.types.json import Jsonb
        changed=copy.deepcopy(self.issue)
        changed['title']['en']='Corrected edition'
        with self.db.transaction():
            self.assertEqual(archive_current_issue(self.db,self.issue['id']),1)
            self.db.execute('UPDATE issues SET content=%s WHERE id=%s',(Jsonb(changed),self.issue['id']))
        with self.db.transaction():
            self.assertEqual(archive_current_issue(self.db,self.issue['id']),2)
        self.assertEqual(self.db.execute('SELECT content FROM edition_revisions ORDER BY revision').fetchall(),
                         [(self.issue,),(changed,)])


if __name__=='__main__':
    unittest.main()
