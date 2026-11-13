CREATE TABLE edition_revisions (
  id TEXT PRIMARY KEY,
  issue_id TEXT NOT NULL,
  revision INTEGER NOT NULL CHECK (revision > 0),
  content JSONB NOT NULL,
  review JSONB NOT NULL,
  archived_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(issue_id, revision)
);
CREATE INDEX edition_revisions_issue_archive ON edition_revisions(issue_id, archived_at);

CREATE FUNCTION protect_edition_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'edition revisions are append-only' USING ERRCODE = '55000';
END;
$$;
CREATE TRIGGER edition_revisions_immutable
  BEFORE UPDATE OR DELETE ON edition_revisions
  FOR EACH ROW EXECUTE FUNCTION protect_edition_revision();
