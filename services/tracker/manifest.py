"""Validate tracker input and resolve reviewed catalog aliases deterministically."""

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import unicodedata


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / 'packages/shared/tracker/catalog.json'
KEY = re.compile(r'[a-z0-9][a-z0-9-]{0,127}')
ISSUE_HASH = re.compile(r'[0-9a-f]{64}')
ROLES = {'vendor', 'independent', 'other'}
STAGES = {'research', 'prototype', 'pilot', 'deployed', 'scaling', 'commercial'}
MAX_MANIFEST_BYTES = 512 * 1024


class TrackerError(ValueError):
    """An operator-facing error with no stored source content or credentials."""


def alias_key(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def opaque_id(prefix, *values):
    encoded = json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    digest = sha256(encoded).hexdigest()
    return f'{prefix}-{digest if prefix == "revision" else digest[:24]}'


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TrackerError('JSON objects must not contain duplicate keys.')
        result[key] = value
    return result


def read_json(path, label):
    try:
        with path.open('rb') as stream:
            data = stream.read(MAX_MANIFEST_BYTES + 1)
        if len(data) > MAX_MANIFEST_BYTES:
            raise TrackerError(f'{label} exceeds the size limit.')
        return json.loads(data.decode('utf-8-sig'), object_pairs_hook=unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TrackerError(f'{label} must be a readable UTF-8 JSON file.') from exc


def identifier(value):
    return isinstance(value, str) and 0 < len(value) <= 240 and not any(character.isspace() or ord(character) < 32 for character in value)


@dataclass(frozen=True)
class CatalogEntry:
    id: str
    name_en: str
    name_zh: str
    aliases: tuple[str, ...]


def catalog_entries(data, kind):
    entries = []
    owners = {}
    ids = set()
    for raw in data[kind]:
        ident = raw['id']
        if not KEY.fullmatch(ident) or ident in ids:
            raise TrackerError('Tracker catalog contains an invalid or duplicate ID.')
        ids.add(ident)
        en, zh = raw['name']['en'], raw['name']['zh']
        keys = tuple(sorted({alias_key(alias) for alias in [ident, en, zh, *raw['aliases']]}))
        if '' in keys or not en.strip() or not zh.strip():
            raise TrackerError('Tracker catalog requires bilingual names and nonempty aliases.')
        for key in keys:
            if key in owners:
                raise TrackerError('Tracker catalog contains an ambiguous alias.')
            owners[key] = ident
        entries.append(CatalogEntry(ident, en, zh, keys))
    return tuple(sorted(entries, key=lambda item: item.id)), owners


@dataclass(frozen=True)
class Catalog:
    companies: tuple[CatalogEntry, ...]
    technologies: tuple[CatalogEntry, ...]
    company_aliases: dict[str, str]
    technology_aliases: dict[str, str]

    @classmethod
    def load(cls):
        data = read_json(CATALOG, 'Tracker catalog')
        try:
            companies, company_aliases = catalog_entries(data, 'companies')
            technologies, technology_aliases = catalog_entries(data, 'technologies')
        except (KeyError, TypeError, AttributeError) as exc:
            raise TrackerError('Tracker catalog is structurally invalid.') from exc
        return cls(companies, technologies, company_aliases, technology_aliases)


def resolve_aliases(values, aliases):
    if not isinstance(values, list) or not 1 <= len(values) <= 30:
        raise TrackerError('Changes must include company and technology aliases.')
    resolved = set()
    for value in values:
        if not isinstance(value, str) or len(value) > 200:
            raise TrackerError('Tracker aliases must be text.')
        owner = aliases.get(alias_key(value))
        if owner is None:
            raise TrackerError('Tracker aliases must match the reviewed catalog.')
        resolved.add(owner)
    return tuple(sorted(resolved))


@dataclass(frozen=True)
class Change:
    project_id: str
    milestone_id: str
    expected_revision: int
    withdraw: bool
    issue_id: str = ''
    issue_hash: str = ''
    story_id: str = ''
    companies: tuple[str, ...] = ()
    technologies: tuple[str, ...] = ()
    source_roles: tuple[tuple[str, str], ...] = ()

    @property
    def revision_id(self):
        return opaque_id('revision', self.milestone_id, self.expected_revision, self.withdraw,
                         self.issue_id, self.issue_hash, self.story_id, self.companies,
                         self.technologies, self.source_roles)


def parse_change(value, catalog):
    keys = {'projectKey', 'milestoneKey', 'expectedRevision'}
    if not isinstance(value, dict) or not keys <= value.keys():
        raise TrackerError('Each change requires projectKey, milestoneKey, and expectedRevision.')
    if any(not isinstance(value[key], str) or not KEY.fullmatch(value[key]) for key in ('projectKey', 'milestoneKey')):
        raise TrackerError('Tracker keys must be lowercase ASCII slugs of up to 128 characters.')
    expected = value['expectedRevision']
    if type(expected) is not int or not 0 <= expected < 2147483647:
        raise TrackerError('expectedRevision must be zero or a positive integer.')
    project_id = opaque_id('project', value['projectKey'])
    milestone_id = opaque_id('milestone', project_id, value['milestoneKey'])
    if 'withdraw' in value:
        if value.keys() != keys | {'withdraw'} or value['withdraw'] is not True or expected == 0:
            raise TrackerError('A withdrawal requires withdraw=true and an existing expectedRevision, with no replacement fields.')
        return Change(project_id, milestone_id, expected, True)

    required = keys | {'issueId', 'issueHash', 'storyId', 'companies', 'technologies'}
    if not required <= value.keys() <= required | {'sourceRoles'}:
        raise TrackerError('Provide the exact issueId, issueHash, storyId, companies and technologies for each import.')
    if any(not identifier(value[key]) for key in ('issueId', 'storyId')):
        raise TrackerError('Issue and story identifiers are invalid.')
    issue_hash = value['issueHash']
    if not isinstance(issue_hash, str) or not ISSUE_HASH.fullmatch(issue_hash):
        raise TrackerError('issueHash must be the exact canonical 64-character edition hash.')
    roles = value.get('sourceRoles', {})
    if not isinstance(roles, dict) or len(roles) > 100 or any(
        not identifier(key) or not isinstance(role, str) or role not in ROLES for key, role in roles.items()
    ):
        raise TrackerError('sourceRoles must map exact source IDs to vendor, independent, or other.')
    return Change(project_id, milestone_id, expected, False, value['issueId'], issue_hash, value['storyId'],
                  resolve_aliases(value['companies'], catalog.company_aliases),
                  resolve_aliases(value['technologies'], catalog.technology_aliases),
                  tuple(sorted(roles.items())))


def load_changes(path, catalog):
    value = read_json(path, 'Tracker input')
    if (not isinstance(value, dict) or value.keys() != {'version', 'changes'}
            or type(value['version']) is not int or value['version'] != 1
            or not isinstance(value['changes'], list) or not 1 <= len(value['changes']) <= 100):
        raise TrackerError('Tracker input requires version 1 and between 1 and 100 changes.')
    return [parse_change(change, catalog) for change in value['changes']]
