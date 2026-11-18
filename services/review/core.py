"""Append-only authenticated editorial candidates; source PostgreSQL is never written."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from hashlib import pbkdf2_hmac, sha256
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from uuid import uuid4

from .security import (ReviewError, MAX_JSON, MAX_EVIDENCE, bilingual, bridge, https_reference,
                       new_file, no_links, plain_json, private_access, private_root, read_private)

ITERATIONS = 600000
ROLES = {'administrator', 'author', 'reviewer'}
STORY_CHECKS = {'originality_en', 'originality_zh', 'facts', 'citations', 'assets'}
EDITION_CHECKS = {'title_introduction_en', 'title_introduction_zh', 'facts', 'citations', 'assets'}
SCHEMA = 'CREATE TABLE events(seq INTEGER PRIMARY KEY,kind TEXT NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL,payload TEXT NOT NULL,previous_hash TEXT NOT NULL,event_hash TEXT NOT NULL)'
TRIGGERS = {
    'events_no_update': "CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'append-only journal'); END",
    'events_no_delete': "CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'append-only journal'); END",
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9._-]{2,63}', value):
        raise ReviewError('Use a stable human identifier of 3-64 simple characters')
    return value


def reason_text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 20000:
        raise ReviewError('A documented change reason is required')
    return value


@dataclass(frozen=True)
class Session:
    user_id: str
    token: str


class Workbench:
    def __init__(self, state_dir):
        self.root = private_root(state_dir)
        self.path = no_links(self.root/'journal.sqlite')
        if not self.path.exists():
            new_file(self.path, b'')
        private_access(self.path)
        self.db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA busy_timeout=10000')
        self.db.execute('PRAGMA foreign_keys=ON')
        self._sessions = {}
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if not self.db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
                self.db.execute(SCHEMA)
                for sql in TRIGGERS.values():
                    self.db.execute(sql)
            self.verify()
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK')
            self.db.close()
            raise

    def close(self):
        self._sessions.clear()
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def verify(self):
        schema = self.db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='events'").fetchone()
        tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        triggers = dict(self.db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"))
        if not schema or schema[0] != SCHEMA or tables != {'events'} or triggers != TRIGGERS:
            raise ReviewError('Journal schema integrity check failed')
        previous, sequence = '0'*64, 0
        result = []
        for row in self.db.execute('SELECT * FROM events ORDER BY seq'):
            try:
                payload = json.loads(row['payload'])
                material = {'seq': row['seq'], 'kind': row['kind'], 'actor': row['actor'],
                            'createdAt': row['created_at'], 'payload': payload, 'previousHash': previous}
                expected = sha256(plain_json(material).encode()).hexdigest()
                if row['seq'] != sequence+1 or row['previous_hash'] != previous or row['event_hash'] != expected:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ReviewError('Journal hash-chain integrity check failed') from None
            result.append(dict(material, eventHash=expected))
            previous, sequence = expected, row['seq']
        return result

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.verify()
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def _events(self, kind=None):
        return [event for event in self.verify() if kind is None or event['kind'] == kind]

    def _append(self, kind, actor, payload):
        body = plain_json(payload)
        if len(body.encode()) > MAX_JSON:
            raise ReviewError('Journal entry exceeds its bound')
        last = self.db.execute('SELECT seq,event_hash FROM events ORDER BY seq DESC LIMIT 1').fetchone()
        seq, previous = (last[0]+1, last[1]) if last else (1, '0'*64)
        at = now()
        material = {'seq': seq, 'kind': kind, 'actor': actor, 'createdAt': at, 'payload': payload, 'previousHash': previous}
        digest = sha256(plain_json(material).encode()).hexdigest()
        self.db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?)', (seq, kind, actor, at, body, previous, digest))
        return dict(material, eventHash=digest)

    def _users(self):
        return {event['payload']['userId']: event['payload'] for event in self._events('user_enrolled')}

    def _actor(self, session, role=None):
        if not isinstance(session, Session) or not isinstance(session.token, str) or not isinstance(session.user_id, str) or session.token not in self._sessions:
            raise ReviewError('Authentication required')
        user_id, expires = self._sessions[session.token]
        if session.user_id != user_id or time.monotonic() > expires:
            raise ReviewError('Authentication required')
        user = self._users().get(user_id)
        if not user or (role and role not in user['roles']):
            raise ReviewError('Required role is not assigned')
        return user

    def _evidence(self, evidence):
        if not isinstance(evidence, dict):
            raise ReviewError('Documented evidence required')
        reason = bilingual(evidence.get('reason'))
        refs = evidence.get('references')
        files = evidence.get('files')
        if not isinstance(refs, list) or not 1 <= len(refs) <= 20 or not isinstance(files, list) or not 1 <= len(files) <= 10:
            raise ReviewError('Actual private evidence files and HTTPS references are required')
        references = [https_reference(value) for value in refs]
        evidence_root = private_root(self.root/'evidence')
        recorded = []
        for filename in files:
            if not isinstance(filename, str):
                raise ReviewError('Evidence filenames must be explicit private paths')
            path = no_links(filename)
            filename = path.name.lower()
            if (filename.startswith('.env') or filename.endswith('.env') or '.env.' in filename
                or path.suffix.lower() in {'.key', '.pem', '.agekey', '.p12', '.pfx', '.sqlite', '.db', '.dump', '.backup', '.age'}
                or filename in {'pgpass', '.pgpass', '.pg_service.conf', 'rclone.conf', 'journal.sqlite'}
                or (filename.endswith('.json') and filename.startswith(('credentials', 'service-account')))):
                raise ReviewError('Credential and journal files cannot be submitted as review evidence')
            data = read_private(path, MAX_EVIDENCE)
            if (not data or re.search(rb'-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----|AGE-SECRET-KEY-|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|(?:AKIA|ASIA)[A-Z0-9]{16}|(?:postgresql|postgres)://[^\s/:]+:[^\s@]+@|(?:OPENAI_API_KEY|DATABASE_URL|PASSWORD|AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY)\s*=', data, re.IGNORECASE)):
                raise ReviewError('Evidence is empty or contains credential material')
            digest = sha256(data).hexdigest()
            destination = evidence_root/(digest+'.evidence')
            if not destination.exists():
                new_file(destination, data)
            elif sha256(read_private(destination, MAX_EVIDENCE)).hexdigest() != digest:
                raise ReviewError('Retained evidence integrity check failed')
            recorded.append({'sha256': digest, 'bytes': len(data), 'file': digest+'.evidence'})
        return {'reason': reason, 'files': recorded, 'references': references}

    def _check_evidence(self, evidence):
        for item in evidence['files']:
            if not re.fullmatch(r'[0-9a-f]{64}\.evidence', item['file']):
                raise ReviewError('Invalid retained evidence reference')
            data = read_private(self.root/'evidence'/item['file'], MAX_EVIDENCE)
            if len(data) != item['bytes'] or sha256(data).hexdigest() != item['sha256']:
                raise ReviewError('Retained evidence integrity check failed')

    def enroll(self, user_id, name, roles, password, identity_evidence, *, session=None, bootstrap=False):
        user_id = identifier(user_id)
        if not isinstance(name, str) or not name.strip() or len(name) > 200 or any(ord(c) < 32 for c in name):
            raise ReviewError('An actual verified human display name is required')
        if not isinstance(roles, (list, tuple)) or not roles or any(not isinstance(role, str) for role in roles) or len(set(roles)) != len(roles) or not set(roles) <= ROLES:
            raise ReviewError('Explicit author, reviewer or administrator roles required')
        if not isinstance(password, str) or not 15 <= len(password) <= 1024:
            raise ReviewError('Choose a private password of 15-1024 characters')
        salt = secrets.token_bytes(32)
        try:
            digest = pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS).hex()
        except UnicodeError:
            raise ReviewError('Password encoding refused') from None
        with self.transaction():
            users = self._users()
            if not users:
                if not bootstrap or session is not None or 'administrator' not in roles:
                    raise ReviewError('Explicit first administrator bootstrap and real identity attestation required')
                actor = user_id
            else:
                if bootstrap:
                    raise ReviewError('Enrollment bootstrap already completed')
                actor = self._actor(session, 'administrator')['userId']
            if user_id in users:
                raise ReviewError('Human identifier already enrolled')
            evidence = self._evidence(identity_evidence)
            payload = {'userId': user_id, 'name': name, 'roles': sorted(roles), 'salt': salt.hex(),
                       'passwordHash': digest, 'algorithm': 'pbkdf2-sha256', 'iterations': ITERATIONS,
                       'identityAttestation': evidence, 'createdAt': now()}
            self._append('user_enrolled', actor, payload)
        return {'userId': user_id, 'roles': sorted(roles)}

    def authenticate(self, user_id, password):
        identifier(user_id)
        allowed = False
        with self.transaction():
            user = self._users().get(user_id)
            cutoff = datetime.now(timezone.utc)-timedelta(minutes=15)
            failures = 0
            for event in reversed(self._events()):
                if event['actor'] == user_id and event['kind'] in {'login_success', 'login_failure'}:
                    if event['kind'] == 'login_success' or datetime.fromisoformat(event['createdAt']) < cutoff:
                        break
                    failures += 1
            valid = False
            if failures < 5 and isinstance(password, str) and len(password) <= 1024:
                try:
                    salt = bytes.fromhex(user['salt']) if user else b'\0'*32
                    if user and (user['iterations'] != ITERATIONS or user['algorithm'] != 'pbkdf2-sha256' or len(salt) != 32 or not re.fullmatch(r'[a-f0-9]{64}', user['passwordHash'])):
                        raise ValueError()
                    digest = pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS).hex()
                    valid = bool(user) and hmac.compare_digest(digest, user['passwordHash'])
                except (ValueError, TypeError, KeyError, UnicodeError):
                    valid = False
            allowed = failures < 5 and valid
            self._append('login_success' if allowed else 'login_failure', user_id, {'result': 'accepted' if allowed else 'refused'})
        if not allowed:
            raise ReviewError('Authentication refused')
        token = secrets.token_urlsafe(32)
        self._sessions[token] = (user_id, time.monotonic()+120)
        return Session(user_id, token)

    def _revision(self, revision_id):
        rows = [event['payload'] for event in self._events('revision') if event['payload']['id'] == revision_id]
        if len(rows) != 1:
            raise ReviewError('Candidate revision not found')
        return rows[0]

    def _head(self, revision):
        heads = [event['payload'] for event in self._events('revision') if event['payload']['candidateId'] == revision['candidateId']]
        if not heads or heads[-1]['id'] != revision['id']:
            raise ReviewError('Revision is stale; review the latest candidate')

    def _reviewer(self, session, revision):
        user = self._actor(session, 'reviewer')
        contributors = {event['payload']['author'] for event in self._events('revision') if event['payload']['candidateId'] == revision['candidateId']}
        if user['userId'] in contributors:
            raise ReviewError('A distinct reviewer who did not author this candidate is required')
        self._head(revision)
        return user

    def _valid_issue(self, issue):
        if not isinstance(issue, dict) or issue.get('synthetic') is not False or not bridge('validate', issue).get('valid'):
            raise ReviewError('A structurally valid real edition is required')
        return bridge('hash', issue)['hash']

    def import_issue(self, session, issue, reason):
        reason_text(reason)
        content_hash = self._valid_issue(issue)
        with self.transaction():
            user = self._actor(session, 'author')
            if any(event['payload']['issue']['id'] == issue['id'] for event in self._events('revision')):
                raise ReviewError('Source edition already imported; create an append-only revision')
            revision = {'id': uuid4().hex, 'candidateId': uuid4().hex, 'parentId': None, 'hash': content_hash,
                        'author': user['userId'], 'reason': reason, 'issue': deepcopy(issue), 'createdAt': now()}
            self._append('revision', user['userId'], revision)
        return deepcopy(revision)

    def revise(self, session, revision_id, proposed_issue, reason):
        reason_text(reason)
        content_hash = self._valid_issue(proposed_issue)
        with self.transaction():
            user = self._actor(session, 'author')
            parent = self._revision(revision_id)
            self._head(parent)
            permitted = deepcopy(parent['issue'])
            for field in ('title', 'introduction'):
                permitted[field] = deepcopy(proposed_issue.get(field))
            old_stories = permitted['stories']
            new_stories = proposed_issue.get('stories', [])
            if len(old_stories) != len(new_stories) or [s['id'] for s in old_stories] != [s['id'] for s in new_stories]:
                raise ReviewError('Candidate identities and story order cannot be replaced')
            asset_fields = {'assets', 'images', 'image', 'logo', 'logos', 'artwork', 'media', 'attachments'}
            for target, proposed in [(permitted, proposed_issue), *zip(old_stories, new_stories)]:
                for field in asset_fields:
                    if field in target and field not in proposed:
                        del target[field]
            for target, proposed in zip(old_stories, new_stories):
                for field in ('title', 'summary', 'why', 'limitation', 'company', 'category', 'maturity', 'score', 'sourceIds'):
                    target[field] = deepcopy(proposed.get(field))
            if plain_json(permitted) != plain_json(proposed_issue):
                raise ReviewError('Only editorial fields and removal of candidate assets may change; source evidence is immutable')
            if content_hash == parent['hash']:
                raise ReviewError('Revision must document an actual editorial change')
            revision = {'id': uuid4().hex, 'candidateId': parent['candidateId'], 'parentId': parent['id'],
                        'hash': content_hash, 'author': user['userId'], 'reason': reason,
                        'issue': deepcopy(proposed_issue), 'createdAt': now()}
            self._append('revision', user['userId'], revision)
        return deepcopy(revision)

    def _review_material(self, review, *, checks=None, approved=False, story=None, revision=None):
        evidence = self._evidence(review)
        if checks is not None:
            values = review.get('checks')
            if not isinstance(values, dict) or set(values) != checks or any(type(value) is not bool for value in values.values()) or (approved and not all(values.values())):
                raise ReviewError('Every required bilingual editorial check must be documented and approved')
            evidence['checks'] = dict(values)
        if story is not None:
            claims = review.get('claims')
            if not isinstance(claims, list) or (approved and not claims) or len(claims) > 100:
                raise ReviewError('Bilingual claim-to-citation mapping is required')
            evidence['claims'] = []
            for claim in claims:
                if not isinstance(claim, dict) or not isinstance(claim.get('sourceIds'), list) or not claim['sourceIds'] or any(not isinstance(item, str) for item in claim['sourceIds']) or len(set(claim['sourceIds'])) != len(claim['sourceIds']) or not set(claim['sourceIds']) <= set(story['sourceIds']):
                    raise ReviewError('Claims must map to exact cited sources for this story')
                evidence['claims'].append({'claim': bilingual(claim.get('claim')), 'support': bilingual(claim.get('support')), 'sourceIds': list(claim['sourceIds'])})
        resolutions = review.get('riskResolutions', [])
        if not isinstance(resolutions, list):
            raise ReviewError('Risk resolutions must be documented')
        from .analysis import analyze
        risk_ids = {risk['id'] for risk in analyze(revision['issue'])} if revision else set()
        seen = set()
        evidence['riskResolutions'] = []
        for resolution in resolutions:
            if not isinstance(resolution, dict) or not isinstance(resolution.get('findingId'), str) or resolution.get('findingId') not in risk_ids or resolution['findingId'] in seen:
                raise ReviewError('Risk resolutions must match distinct current finding IDs')
            seen.add(resolution['findingId'])
            evidence['riskResolutions'].append({'findingId': resolution['findingId'], 'reason': bilingual(resolution.get('reason'))})
        return evidence

    def decide(self, session, revision_id, scope, target_id, status, review):
        if not isinstance(scope, str) or not isinstance(status, str) or scope not in {'story', 'link'} or status not in {'pending', 'rejected', 'approved'}:
            raise ReviewError('Explicit story/link decision and review state required')
        with self.transaction():
            revision = self._revision(revision_id)
            user = self._reviewer(session, revision)
            items = revision['issue']['stories' if scope == 'story' else 'sources']
            target = next((item for item in items if item['id'] == target_id), None)
            if target is None:
                raise ReviewError('Decision target is not in this exact candidate')
            material = self._review_material(review, checks=STORY_CHECKS if scope == 'story' else None,
                                             approved=status == 'approved', story=target if scope == 'story' else None, revision=revision)
            if scope == 'link':
                if review.get('url') != target['url'] or review.get('publisher') != target['name'] or review.get('basis') not in {'permission', 'legal-review'} or review.get('intendedUse') != 'public-web':
                    raise ReviewError('Exact publisher/URL, intended public use and documented legal basis required')
                material.update(url=target['url'], publisher=target['name'], basis=review['basis'], intendedUse='public-web')
            decision = {'id': uuid4().hex, 'revisionId': revision_id, 'revisionHash': revision['hash'], 'scope': scope,
                        'targetId': target_id, 'status': status, 'review': material, 'reviewer': user['userId'], 'createdAt': now()}
            self._append('decision', user['userId'], decision)
        return deepcopy(decision)

    def _decisions(self, revision):
        current = {}
        for event in self._events('decision'):
            decision = event['payload']
            if decision['revisionId'] == revision['id'] and decision['revisionHash'] == revision['hash']:
                current[(decision['scope'], decision['targetId'])] = decision
        return current

    def finalize(self, session, revision_id, review, confirmation_password):
        # A fresh password check is mandatory even when an in-memory session exists.
        actor = self._actor(session, 'reviewer')
        confirmation = self.authenticate(actor['userId'], confirmation_password)
        with self.transaction():
            revision = self._revision(revision_id)
            user = self._reviewer(confirmation, revision)
            if any(event['payload'].get('revisionId') == revision_id for event in self._events('revoked')):
                raise ReviewError('Revoked revisions require a new candidate revision and complete review')
            if any(event['payload'].get('revisionId') == revision_id for event in self._events('approval')):
                raise ReviewError('Revision already approved; export the existing immutable approval')
            decisions = self._decisions(revision)
            required = [('story', item['id']) for item in revision['issue']['stories']] + [('link', item['id']) for item in revision['issue']['sources']]
            if any(key not in decisions or decisions[key]['status'] != 'approved' for key in required):
                raise ReviewError('Every exact story and source link must have current approval')
            material = self._review_material(review, checks=EDITION_CHECKS, approved=True, revision=revision)
            all_material = [material, *(decisions[key]['review'] for key in required)]
            for evidence in all_material:
                self._check_evidence(evidence)
            from .analysis import analyze
            risks = {risk['id'] for risk in analyze(revision['issue'])}
            resolved = {entry['findingId'] for item in all_material for entry in item['riskResolutions']}
            if risks - resolved:
                raise ReviewError('Current heuristic risks require documented human resolution')
            approval = {'id': uuid4().hex, 'revisionId': revision_id, 'revisionHash': revision['hash'],
                        'reviewer': user['userId'], 'review': material,
                        'decisionIds': [decisions[key]['id'] for key in required], 'createdAt': now()}
            self._append('approval', user['userId'], approval)
            if bridge('project', revision['issue'], self._policy(revision, approval, decisions)).get('issue') is None:
                raise ReviewError('Exact shared public gate refused the completed review')
        return deepcopy(approval)

    def _policy(self, revision, approval, decisions):
        links = []
        users = self._users()
        for source in revision['issue']['sources']:
            decision = decisions[('link', source['id'])]
            links.append({'sourceId': source['id'], 'url': source['url'], 'publisher': source['name'], 'approved': True,
                          'basis': decision['review']['basis'], 'evidenceUrl': decision['review']['references'][0],
                          'reviewedBy': users[decision['reviewer']]['name'], 'reviewedAt': decision['createdAt'].replace('+00:00', 'Z')})
        return {'version': 1, 'intendedUse': 'public-web', 'editions': [{
            'issueId': revision['issue']['id'], 'contentSha256': revision['hash'], 'editorialApproved': True,
            'reviewedBy': users[approval['reviewer']]['name'], 'reviewedAt': approval['createdAt'].replace('+00:00', 'Z'),
            'reviewEvidence': approval['review']['references'][0], 'sourceLinks': links}]}

    def revoke(self, session, revision_id, reason):
        evidence = None
        if isinstance(reason, dict):
            evidence = reason
        else:
            raise ReviewError('Revocation requires bilingual reason and retained evidence')
        with self.transaction():
            revision = self._revision(revision_id)
            user = self._actor(session, 'reviewer')
            material = self._evidence(evidence)
            event = self._append('revoked', user['userId'], {'revisionId': revision_id, 'revisionHash': revision['hash'], 'review': material})
        return event

    def _bundle(self, revision):
        self._head(revision)
        events = self._events()
        if any(event['kind'] == 'revoked' and event['payload'].get('revisionId') == revision['id'] for event in events):
            raise ReviewError('Revision approval is revoked')
        approvals = [event['payload'] for event in events if event['kind'] == 'approval' and event['payload']['revisionId'] == revision['id'] and event['payload']['revisionHash'] == revision['hash']]
        if len(approvals) != 1:
            raise ReviewError('Revision has no complete authenticated approval')
        approval = approvals[0]
        decisions = self._decisions(revision)
        if any(item['status'] != 'approved' or item['id'] not in approval['decisionIds'] for item in decisions.values()):
            raise ReviewError('Review changed after final approval; create a new candidate revision')
        for item in [approval['review'], *(decision['review'] for decision in decisions.values())]:
            self._check_evidence(item)
        if bridge('hash', revision['issue']).get('hash') != revision['hash']:
            raise ReviewError('Candidate hash integrity check failed')
        policy = self._policy(revision, approval, decisions)
        public = bridge('project', revision['issue'], policy).get('issue')
        if public is None:
            raise ReviewError('Exact shared public gate withheld this candidate')
        return {'format': 'industrial-ai-reviewed-bundle-v1', 'issue': deepcopy(revision['issue']), 'policy': policy,
                'revision': {key: deepcopy(value) for key, value in revision.items() if key != 'issue'},
                'approvalId': approval['id'], 'auditHead': events[-1]['eventHash'], 'publicIssue': public}

    def bundle(self, session, revision_id):
        with self.transaction():
            self._actor(session)
            return self._bundle(self._revision(revision_id))

    def _output(self, output, area, directory=False):
        base = private_root(self.root/area)
        path = no_links(output)
        try:
            relative = path.relative_to(base)
        except ValueError:
            raise ReviewError('Review output must stay in its private workbench area') from None
        if len(relative.parts) != 1 or not relative.name or path.exists():
            raise ReviewError('Use a new single output name inside the private workbench area')
        if not directory and path.suffix != '.json':
            raise ReviewError('Review bundles must use a new JSON filename')
        return path

    def export(self, session, revision_id, output):
        with self.transaction():
            user = self._actor(session)
            bundle = self._bundle(self._revision(revision_id))
            path = self._output(output, 'exports')
            new_file(path, plain_json(bundle).encode())
            self._append('exported', user['userId'], {'revisionId': revision_id, 'file': path.name, 'sha256': sha256(read_private(path)).hexdigest()})
        return path

    def preview(self, session, revision_id, output_dir):
        with self.transaction():
            user = self._actor(session)
            revision = self._revision(revision_id)
            try:
                public = self._bundle(revision)['publicIssue']
            except ReviewError:
                public = None
            from .render import render_preview
            path = self._output(output_dir, 'previews', directory=True)
            render_preview(public, path)
            self._append('previewed', user['userId'], {'revisionId': revision_id, 'output': path.name, 'approved': public is not None})
        return path

    def review(self, session, revision_id, output_dir):
        with self.transaction():
            user = self._actor(session)
            revision = self._revision(revision_id)
            from .analysis import analyze, suggest
            from .render import render_review
            path = self._output(output_dir, 'reports', directory=True)
            render_review(revision['issue'], analyze(revision['issue']), suggest(revision['issue']), path)
            self._append('reviewed_private', user['userId'], {'revisionId': revision_id, 'output': path.name})
        return path

    def revisions(self, session):
        with self.transaction():
            self._actor(session)
            return [{key: deepcopy(value) for key, value in event['payload'].items() if key != 'issue'} for event in self._events('revision')]

    def candidate(self, session, revision_id):
        with self.transaction():
            self._actor(session)
            return deepcopy(self._revision(revision_id))

    def status(self, session, revision_id):
        with self.transaction():
            self._actor(session)
            revision = self._revision(revision_id)
            decisions = list(self._decisions(revision).values())
            from .analysis import analyze
            events = self._events()
            return {'revision': {key: deepcopy(value) for key, value in revision.items() if key != 'issue'},
                    'decisions': deepcopy(decisions), 'findings': analyze(revision['issue']),
                    'approvals': [deepcopy(event['payload']) for event in events if event['kind'] == 'approval' and event['payload']['revisionId'] == revision_id],
                    'revocations': [deepcopy(event['payload']) for event in events if event['kind'] == 'revoked' and event['payload']['revisionId'] == revision_id]}

    def audit(self, session):
        with self.transaction():
            self._actor(session)
            events = deepcopy(self._events())
            for event in events:
                if event['kind'] == 'user_enrolled':
                    for field in ('passwordHash', 'salt'):
                        event['payload'].pop(field, None)
            return events
