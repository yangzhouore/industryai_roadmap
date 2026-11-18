"""Practical local-only human editorial review; never publishes or changes source data."""
import argparse
import getpass
import hmac
import json
from pathlib import Path
import sys
import warnings

from .core import Workbench
from .security import ROOT, ReviewError, load_private_json, new_file, plain_json
from .source import source_dsn, source_editions


class PrivateParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, 'Review command arguments refused; use --help. Private values withheld.\n')


def password(prompt):
    if not sys.stdin.isatty():
        raise ReviewError('Interactive terminal authentication is required; passwords cannot come from files or environment')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            return getpass.getpass(prompt)
        except (getpass.GetPassWarning, EOFError):
            raise ReviewError('Private interactive password entry unavailable') from None


def parser():
    value = PrivateParser(description=__doc__)
    value.add_argument('--state-dir', default=str(ROOT/'artifacts/editorial-review'))
    value.add_argument('--actor', help='Explicit enrolled human identifier; no default identity')
    commands = value.add_subparsers(dest='command', required=True, parser_class=PrivateParser)
    enroll = commands.add_parser('enroll', help='Explicit manually verified identity enrollment; no identities are seeded')
    enroll.add_argument('--human-id', required=True)
    enroll.add_argument('--name', required=True)
    enroll.add_argument('--role', action='append', choices=['administrator', 'author', 'reviewer'], required=True)
    enroll.add_argument('--identity-evidence', required=True, help='Private JSON evidence/attestation document')
    enroll.add_argument('--bootstrap', action='store_true', help='Explicit first administrator only; manual identity verification required')
    sources = commands.add_parser('source-list', help='List source editions using only read-only PostgreSQL')
    sources.add_argument('--database-env', default='DATABASE_URL')
    ingest = commands.add_parser('import', help='Import actual stored source edition into a separate private candidate')
    ingest.add_argument('--database-env', default='DATABASE_URL')
    ingest.add_argument('--issue-id', required=True)
    ingest.add_argument('--reason', required=True)
    commands.add_parser('list', help='List append-only candidate revision metadata')
    commands.add_parser('verify', help='Verify immutable journal and hash chain')
    commands.add_parser('audit', help='Authenticated private audit view with password verifiers omitted')
    status = commands.add_parser('status', help='Inspect current decisions, reasons, evidence and findings')
    status.add_argument('--revision', required=True)
    show = commands.add_parser('show', help='Write an editable full private candidate snapshot, never to stdout')
    show.add_argument('--revision', required=True)
    show.add_argument('--output', required=True, help='New filename under private state/drafts')
    revise = commands.add_parser('revise', help='Create an append-only editorial-only revision; sources remain unchanged')
    revise.add_argument('--revision', required=True)
    revise.add_argument('--input', required=True, help='Private full proposed Issue JSON snapshot')
    revise.add_argument('--reason', required=True)
    decide = commands.add_parser('decide', help='Document current exact story or source-link review')
    decide.add_argument('--revision', required=True)
    decide.add_argument('--scope', choices=['story', 'link'], required=True)
    decide.add_argument('--target', required=True)
    decide.add_argument('--status', choices=['pending', 'rejected', 'approved'], required=True)
    decide.add_argument('--review-file', required=True)
    for command in ('finalize', 'revoke'):
        item = commands.add_parser(command)
        item.add_argument('--revision', required=True)
        item.add_argument('--review-file', required=True)
    for command in ('export', 'report', 'preview'):
        item = commands.add_parser(command)
        item.add_argument('--revision', required=True)
        item.add_argument('--output', required=True, help='New single filename/directory in the matching private area')
    return value


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command != 'enroll' and not args.actor:
            raise ReviewError('Explicit actor required')
        if not sys.stdin.isatty():
            raise ReviewError('Interactive private authentication is required')
        with Workbench(args.state_dir) as workbench:
            if args.command == 'enroll':
                session = None
                if not args.bootstrap:
                    if not args.actor:
                        raise ReviewError('An explicit authenticated administrator is required')
                    session = workbench.authenticate(args.actor, password('Administrator password: '))
                chosen = password('New human password: ')
                confirmed = password('Confirm new human password: ')
                if not hmac.compare_digest(chosen.encode(), confirmed.encode()):
                    raise ReviewError('Password confirmation failed')
                result = workbench.enroll(args.human_id, args.name, args.role, chosen,
                    load_private_json(args.identity_evidence), session=session, bootstrap=args.bootstrap)
            else:
                if not args.actor:
                    raise ReviewError('An explicit enrolled human actor is required')
                session = workbench.authenticate(args.actor, password('Review password: '))
                if args.command == 'source-list':
                    # Title metadata remains private and is intentionally not printed by this list.
                    rows = source_editions(source_dsn(args.database_env))
                    result = {'sourceEditions': [{'id': row['id'], 'date': row['date']} for row in rows], 'readOnly': True}
                elif args.command == 'import':
                    item = workbench.import_issue(session, source_editions(source_dsn(args.database_env), args.issue_id), args.reason)
                    result = {'revisionId': item['id'], 'hash': item['hash']}
                elif args.command == 'list':
                    result = {'revisions': workbench.revisions(session)}
                elif args.command == 'audit':
                    result = {'events': workbench.audit(session)}
                elif args.command == 'status':
                    result = workbench.status(session, args.revision)
                elif args.command == 'verify':
                    workbench._actor(session)
                    result = {'integrity': 'verified', 'events': len(workbench.verify())}
                elif args.command == 'show':
                    item = workbench.candidate(session, args.revision)
                    path = workbench._output(Path(workbench.root/'drafts')/args.output, 'drafts')
                    new_file(path, plain_json(item['issue']).encode())
                    with workbench.transaction():
                        workbench._append('draft_exported', args.actor, {'revisionId': args.revision, 'file': path.name})
                    result = {'privateDraft': path.name}
                elif args.command == 'revise':
                    item = workbench.revise(session, args.revision, load_private_json(args.input), args.reason)
                    result = {'revisionId': item['id'], 'hash': item['hash']}
                elif args.command == 'decide':
                    item = workbench.decide(session, args.revision, args.scope, args.target, args.status, load_private_json(args.review_file))
                    result = {'decisionId': item['id'], 'status': item['status']}
                elif args.command == 'finalize':
                    item = workbench.finalize(session, args.revision, load_private_json(args.review_file), password('Confirm final reviewer password: '))
                    result = {'approvalId': item['id'], 'revisionId': item['revisionId'], 'publicPolicyInstalled': False}
                elif args.command == 'revoke':
                    item = workbench.revoke(session, args.revision, load_private_json(args.review_file))
                    result = {'revoked': True, 'event': item['seq'], 'deployedPolicyUnchanged': True}
                else:
                    area = {'export': 'exports', 'preview': 'previews', 'report': 'reports'}[args.command]
                    method = {'export': workbench.export, 'preview': workbench.preview, 'report': workbench.review}[args.command]
                    path = method(session, args.revision, workbench.root/area/args.output)
                    result = {'privateArtifact': path.name, 'deployedPolicyUnchanged': True}
            print(json.dumps(result, ensure_ascii=True, default=str))
            return 0
    except KeyboardInterrupt:
        print(json.dumps({'status': 'cancelled', 'message': 'Review cancelled; no approval is implied.'}))
        return 130
    except Exception:
        print(json.dumps({'status': 'refused', 'message': 'Review operation refused or failed; private content and credential details withheld.'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
