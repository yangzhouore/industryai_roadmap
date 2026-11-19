"""Read-only manifest checks and tracker revision tests on an explicitly isolated database."""

from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import quote, urlencode, urlunsplit
from uuid import uuid4

from smoke_database_web import PUBLIC_DATE, test_database_url as isolated_database_url
from services.tracker.manifest import Catalog, TrackerError, load_changes, parse_change
from services.tracker.store import apply_changes, list_stories


ROOT = Path(__file__).resolve().parents[1]
DATABASE = os.getenv('TEST_DATABASE_URL')


def candidate(**overrides):
    return {
        'projectKey': 'test-project', 'milestoneKey': 'test-milestone', 'expectedRevision': 0,
        'issueId': 'test-issue', 'issueHash': 'a' * 64, 'storyId': 'test-story',
        'companies': ['Siemens'], 'technologies': ['Digital Twin'], **overrides,
    }


class TrackerManifestTests(unittest.TestCase):
    def test_aliases_resolve_and_equivalent_replays_have_same_id(self):
        catalog = Catalog.load()
        original = parse_change(candidate(), catalog)
        aliases = parse_change(candidate(companies=[' ＳＩＥＭＥＮＳ ', '西门子'], technologies=['数字孪生']), catalog)
        self.assertEqual(original, aliases)
        self.assertEqual(original.companies, ('siemens',))
        self.assertEqual(original.technologies, ('digital-twins',))
        self.assertEqual(original.revision_id, aliases.revision_id)
        self.assertNotIn('test-project', original.project_id)

    def test_reject_unknown_alias_duplicate_keys_and_unbound_or_extra_fields(self):
        catalog = Catalog.load()
        for overrides in (
            {'companies': ['unknown-company']}, {'technology': ['Digital Twins']}, {'issueHash': 'short'},
            {'expectedRevision': True}, {'sourceRoles': {'some-source': 'verified'}},
            {'withdraw': True}, {'title': 'unapproved extra prose'},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(TrackerError):
                parse_change(candidate(**overrides), catalog)
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'duplicate.json'
            file.write_text('{"version":1,"version":1,"changes":[]}', encoding='utf-8')
            with self.assertRaisesRegex(TrackerError, 'duplicate keys'):
                load_changes(file, catalog)


@unittest.skipUnless(DATABASE, 'TEST_DATABASE_URL is required for the isolated tracker import test')
class TrackerImportTests(unittest.TestCase):
    def test_import_replay_deduplication_revision_withdrawal_and_existing_news_preservation(self):
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb
        from services.pipeline.editorial.live import generate_real_issue
        from services.pipeline.editorial.test_live import ARTICLE, ScriptedHTTP, provider
        from services.pipeline.store import Store

        parts = isolated_database_url(DATABASE, isolated=True)
        self.assertIn(parts.hostname, ('127.0.0.1', 'localhost', '::1'))
        schema = 'tracker_import_test_' + uuid4().hex
        scoped = urlunsplit(parts._replace(query=urlencode([('options', '-c search_path='+schema+',public')], quote_via=quote)))
        with psycopg.connect(DATABASE, autocommit=True) as admin:
            admin.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            try:
                store = Store(scoped)
                try:
                    for migration in sorted((ROOT/'packages/db/prisma/migrations').glob('*/migration.sql')):
                        store.db.execute(migration.read_text(encoding='utf-8'), prepare=False)
                    draft, review = generate_real_issue([deepcopy(ARTICLE)], PUBLIC_DATE, provider(ScriptedHTTP()))
                    store.publish(draft, review)
                finally:
                    store.close()
                with psycopg.connect(scoped, autocommit=True, row_factory=dict_row) as db:
                    repeated = db.execute('SELECT content FROM issues WHERE id=%s', (draft['id'],)).fetchone()['content']
                    repeated.update(id='second-test-edition', slug='2026-01-02', date='2026-01-02')
                    old_story_key = f"{draft['id']}:{repeated['stories'][0]['id']}"
                    new_story_key = f"{repeated['id']}:{repeated['stories'][0]['id']}"
                    db.execute("""INSERT INTO issues(id, slug, issue_date, state, validated, content, published_at)
                        SELECT %s, %s, %s, state, validated, %s, published_at FROM issues WHERE id=%s""",
                        (repeated['id'], repeated['slug'], repeated['date'], Jsonb(repeated), draft['id']))
                    db.execute("""INSERT INTO digest_stories(id, issue_id, position, kind, structured_content, evidence_status)
                        SELECT %s, %s, position, kind, structured_content, evidence_status FROM digest_stories WHERE id=%s""",
                        (new_story_key, repeated['id'], old_story_key))
                    db.execute("""INSERT INTO story_citations(story_id, raw_article_id, claim_key, source_url, excerpt_or_pointer)
                        SELECT %s, raw_article_id, claim_key, source_url, excerpt_or_pointer FROM story_citations WHERE story_id=%s""",
                        (new_story_key, old_story_key))
                    original = self.news_rows(db)
                    stories = list_stories(db, draft['id'])
                    story = stories['stories'][0]
                    catalog = Catalog.load()
                    raw = candidate(issueId=draft['id'], issueHash=stories['issueHash'], storyId=story['storyId'])
                    change = parse_change(raw, catalog)
                    repeated_stories = list_stories(db, repeated['id'])
                    cross_edition = parse_change(dict(raw, milestoneKey='cross-edition-duplicate',
                        issueId=repeated['id'], issueHash=repeated_stories['issueHash']), catalog)
                    self.assertEqual(apply_changes(db, catalog, [change])[0]['status'], 'appended')
                    self.assertEqual(apply_changes(db, catalog, [change])[0]['status'], 'unchanged')
                    with self.assertRaisesRegex(TrackerError, 'canonical evidence already anchors'):
                        apply_changes(db, catalog, [cross_edition])
                    for invalid, message in (
                        (dict(raw, milestoneKey='duplicate'), 'already anchors'),
                        (dict(raw, milestoneKey='wrong-edition', issueHash='0' * 64), 'changed'),
                        (dict(raw, milestoneKey='unrelated-source', sourceRoles={'missing-source': 'vendor'}), 'exact source'),
                    ):
                        with self.assertRaisesRegex(TrackerError, message):
                            apply_changes(db, catalog, [parse_change(invalid, catalog)])
                    correction = parse_change(dict(raw, expectedRevision=1,
                        sourceRoles={story['sourceIds'][0]: 'vendor'}), catalog)
                    self.assertEqual(apply_changes(db, catalog, [correction])[0]['currentRevision'], 2)
                    self.assertEqual(apply_changes(db, catalog, [change])[0]['currentRevision'], 2)
                    with self.assertRaisesRegex(TrackerError, 'head changed'):
                        apply_changes(db, catalog, [parse_change(dict(raw, companies=['ABB'], expectedRevision=1), catalog)])
                    withdrawal = parse_change(dict(projectKey='test-project', milestoneKey='test-milestone',
                                                   expectedRevision=2, withdraw=True), catalog)
                    self.assertEqual(apply_changes(db, catalog, [withdrawal])[0]['status'], 'withdrawn')
                    self.assertEqual(apply_changes(db, catalog, [withdrawal])[0]['status'], 'unchanged')
                    with self.assertRaisesRegex(TrackerError, 'canonical evidence already anchors'):
                        apply_changes(db, catalog, [cross_edition])

                    revisions = list(db.execute('SELECT revision, withdrawn FROM tracker_milestone_revisions ORDER BY revision'))
                    self.assertEqual(revisions, [dict(revision=1, withdrawn=False), dict(revision=2, withdrawn=False),
                                                 dict(revision=3, withdrawn=True)])
                    rows = list(db.execute('''SELECT e.kind,e.publisher,e.canonical_url,e.published_at,e.event_at,
                        a.canonical_url AS original_url,a.published_at AS original_published,a.event_at AS original_event
                        FROM tracker_evidence e JOIN raw_articles a ON a.id=e.raw_article_id ORDER BY e.kind'''))
                    self.assertEqual([row['kind'] for row in rows], ['other', 'vendor'])
                    for row in rows:
                        self.assertEqual(row['canonical_url'], row['original_url'])
                        self.assertEqual(row['published_at'], row['original_published'])
                        self.assertEqual(row['event_at'], row['original_event'])
                    self.assertEqual(self.news_rows(db), original)
            finally:
                admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))

    @staticmethod
    def news_rows(db):
        return [list(db.execute(f'SELECT * FROM {table} ORDER BY 1,2'))
                for table in ('issues', 'digest_stories', 'sources', 'raw_articles', 'story_citations', 'edition_revisions')]
