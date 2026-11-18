-- Additive tracker storage. Existing editorial rows and approvals are unchanged.
CREATE TABLE tracker_companies (
    id TEXT PRIMARY KEY CHECK (id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    name_en TEXT NOT NULL CHECK (btrim(name_en) <> ''),
    name_zh TEXT NOT NULL CHECK (btrim(name_zh) <> '')
);

CREATE TABLE tracker_company_aliases (
    key TEXT PRIMARY KEY CHECK (btrim(key) <> ''),
    company_id TEXT NOT NULL REFERENCES tracker_companies(id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE INDEX tracker_company_aliases_company ON tracker_company_aliases(company_id);

CREATE TABLE tracker_technologies (
    id TEXT PRIMARY KEY CHECK (id ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    name_en TEXT NOT NULL CHECK (btrim(name_en) <> ''),
    name_zh TEXT NOT NULL CHECK (btrim(name_zh) <> '')
);

CREATE TABLE tracker_technology_aliases (
    key TEXT PRIMARY KEY CHECK (btrim(key) <> ''),
    technology_id TEXT NOT NULL REFERENCES tracker_technologies(id) ON DELETE RESTRICT ON UPDATE RESTRICT
);
CREATE INDEX tracker_technology_aliases_technology ON tracker_technology_aliases(technology_id);

CREATE TABLE tracker_projects (
    id TEXT PRIMARY KEY CHECK (btrim(id) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tracker_milestones (
    id TEXT PRIMARY KEY CHECK (btrim(id) <> ''),
    project_id TEXT NOT NULL REFERENCES tracker_projects(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX tracker_milestones_project ON tracker_milestones(project_id);

CREATE TABLE tracker_milestone_revisions (
    id TEXT PRIMARY KEY CHECK (btrim(id) <> ''),
    milestone_id TEXT NOT NULL REFERENCES tracker_milestones(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    revision INTEGER NOT NULL CHECK (revision > 0),
    issue_id TEXT NOT NULL REFERENCES issues(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    issue_hash TEXT NOT NULL CHECK (issue_hash ~ '^[a-f0-9]{64}$'),
    story_id TEXT NOT NULL CHECK (btrim(story_id) <> ''),
    stage TEXT NOT NULL CHECK (stage IN ('research', 'prototype', 'pilot', 'deployed', 'scaling', 'commercial')),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    recorded_xid XID8 NOT NULL DEFAULT pg_current_xact_id(),
    withdrawn BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX tracker_revisions_milestone_version ON tracker_milestone_revisions(milestone_id, revision DESC);
CREATE INDEX tracker_revisions_issue_story ON tracker_milestone_revisions(issue_id, issue_hash, story_id);

CREATE TABLE tracker_evidence (
    revision_id TEXT NOT NULL REFERENCES tracker_milestone_revisions(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    source_key TEXT NOT NULL CHECK (btrim(source_key) <> ''),
    raw_article_id TEXT NOT NULL REFERENCES raw_articles(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    kind TEXT NOT NULL CHECK (kind IN ('vendor', 'independent', 'other')),
    published_at TIMESTAMPTZ NOT NULL,
    event_at TIMESTAMPTZ,
    publisher TEXT NOT NULL CHECK (btrim(publisher) <> ''),
    canonical_url TEXT NOT NULL CHECK (btrim(canonical_url) <> ''),
    source_timezone TEXT NOT NULL CHECK (btrim(source_timezone) <> ''),
    PRIMARY KEY (revision_id, source_key)
);
CREATE UNIQUE INDEX tracker_evidence_revision_article ON tracker_evidence(revision_id, raw_article_id);
CREATE INDEX tracker_evidence_article ON tracker_evidence(raw_article_id);

CREATE TABLE tracker_revision_companies (
    revision_id TEXT NOT NULL REFERENCES tracker_milestone_revisions(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    company_id TEXT NOT NULL REFERENCES tracker_companies(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    PRIMARY KEY (revision_id, company_id)
);
CREATE INDEX tracker_revision_companies_company ON tracker_revision_companies(company_id, revision_id);

CREATE TABLE tracker_revision_technologies (
    revision_id TEXT NOT NULL REFERENCES tracker_milestone_revisions(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    technology_id TEXT NOT NULL REFERENCES tracker_technologies(id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    PRIMARY KEY (revision_id, technology_id)
);
CREATE INDEX tracker_revision_technologies_technology ON tracker_revision_technologies(technology_id, revision_id);

CREATE FUNCTION protect_tracker_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'tracker revision records are append-only' USING ERRCODE = '55000';
END;
$$;

CREATE TRIGGER tracker_revisions_immutable BEFORE UPDATE OR DELETE ON tracker_milestone_revisions
    FOR EACH ROW EXECUTE FUNCTION protect_tracker_revision();
CREATE TRIGGER tracker_evidence_immutable BEFORE UPDATE OR DELETE ON tracker_evidence
    FOR EACH ROW EXECUTE FUNCTION protect_tracker_revision();
CREATE TRIGGER tracker_revision_companies_immutable BEFORE UPDATE OR DELETE ON tracker_revision_companies
    FOR EACH ROW EXECUTE FUNCTION protect_tracker_revision();
CREATE TRIGGER tracker_revision_technologies_immutable BEFORE UPDATE OR DELETE ON tracker_revision_technologies
    FOR EACH ROW EXECUTE FUNCTION protect_tracker_revision();

-- Parent identity and project membership are also immutable once recorded.
CREATE TRIGGER tracker_projects_immutable BEFORE UPDATE OR DELETE ON tracker_projects
    FOR EACH ROW EXECUTE FUNCTION protect_tracker_revision();
CREATE TRIGGER tracker_milestones_immutable BEFORE UPDATE OR DELETE ON tracker_milestones
    FOR EACH ROW EXECUTE FUNCTION protect_tracker_revision();

-- Evidence and entity membership are part of the immutable version. Comparing
-- the full, top-level transaction IDs also supports writers using savepoints.
-- The insertion timestamp prevents an old revision from reopening if a restored
-- database reuses a transaction ID from the source cluster.
CREATE FUNCTION require_tracker_revision_transaction() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parent_was_created_here BOOLEAN;
BEGIN
    EXECUTE format(
        'SELECT EXISTS (SELECT 1 FROM %I.tracker_milestone_revisions
                        WHERE id = $1 AND recorded_xid = pg_current_xact_id() AND recorded_at = transaction_timestamp())',
        TG_TABLE_SCHEMA
    ) INTO parent_was_created_here USING NEW.revision_id;
    IF NOT parent_was_created_here THEN
        RAISE EXCEPTION 'tracker revision children require their parent transaction' USING ERRCODE = '55000';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER tracker_evidence_sealed BEFORE INSERT ON tracker_evidence
    FOR EACH ROW EXECUTE FUNCTION require_tracker_revision_transaction();
CREATE TRIGGER tracker_revision_companies_sealed BEFORE INSERT ON tracker_revision_companies
    FOR EACH ROW EXECUTE FUNCTION require_tracker_revision_transaction();
CREATE TRIGGER tracker_revision_technologies_sealed BEFORE INSERT ON tracker_revision_technologies
    FOR EACH ROW EXECUTE FUNCTION require_tracker_revision_transaction();
