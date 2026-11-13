CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE TABLE issues (
 id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, issue_date TEXT NOT NULL UNIQUE,
 state TEXT NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','validated','published')),
 validated BOOLEAN NOT NULL DEFAULT false, content JSONB NOT NULL,
 published_at TIMESTAMPTZ,
 CHECK (state='draft' OR validated),
 CHECK (state<>'published' OR published_at IS NOT NULL)
);
CREATE INDEX issues_public ON issues(state,validated,issue_date);
CREATE INDEX issues_search ON issues USING gin(to_tsvector('simple', content::text));
CREATE INDEX issues_trigram ON issues USING gin((content::text) gin_trgm_ops);
CREATE TABLE sources (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, homepage TEXT NOT NULL,
 feed_url TEXT, source_type TEXT NOT NULL, active BOOLEAN NOT NULL DEFAULT true,
 fetch_policy JSONB NOT NULL
);
CREATE TABLE raw_articles (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
 canonical_url TEXT NOT NULL UNIQUE, title TEXT NOT NULL, body_excerpt TEXT NOT NULL,
 published_at TIMESTAMPTZ NOT NULL, event_at TIMESTAMPTZ, source_timezone TEXT NOT NULL,
 collected_at TIMESTAMPTZ NOT NULL DEFAULT now(), content_hash TEXT NOT NULL,
 raw_metadata JSONB NOT NULL
);
CREATE INDEX articles_date ON raw_articles(published_at);
CREATE TABLE story_clusters (
 id TEXT PRIMARY KEY, label TEXT NOT NULL, event_date DATE, category TEXT NOT NULL,
 maturity TEXT NOT NULL, status TEXT NOT NULL
);
CREATE TABLE article_cluster_links (
 cluster_id TEXT REFERENCES story_clusters(id), article_id TEXT REFERENCES raw_articles(id),
 PRIMARY KEY(cluster_id,article_id)
);
CREATE TABLE entities (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, entity_type TEXT NOT NULL, canonical_name TEXT NOT NULL UNIQUE
);
CREATE TABLE story_entity_links (
 cluster_id TEXT REFERENCES story_clusters(id), entity_id TEXT REFERENCES entities(id),
 relationship TEXT NOT NULL, PRIMARY KEY(cluster_id,entity_id,relationship)
);
CREATE TABLE scores (
 cluster_id TEXT REFERENCES story_clusters(id), scoring_version TEXT NOT NULL,
 dimensions_json JSONB NOT NULL, final_score DOUBLE PRECISION NOT NULL CHECK(final_score BETWEEN 0 AND 100),
 scored_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(cluster_id,scoring_version)
);
CREATE TABLE digest_stories (
 id TEXT PRIMARY KEY, issue_id TEXT NOT NULL REFERENCES issues(id), cluster_id TEXT REFERENCES story_clusters(id),
 position INTEGER NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('feature','quick_bite')),
 structured_content JSONB NOT NULL, evidence_status TEXT NOT NULL, UNIQUE(issue_id,position)
);
CREATE TABLE story_citations (
 story_id TEXT REFERENCES digest_stories(id), raw_article_id TEXT REFERENCES raw_articles(id),
 claim_key TEXT NOT NULL, source_url TEXT NOT NULL, excerpt_or_pointer TEXT NOT NULL,
 PRIMARY KEY(story_id,raw_article_id,claim_key)
);
CREATE TABLE translations (
 story_id TEXT REFERENCES digest_stories(id), locale TEXT CHECK(locale IN ('en','zh')),
 title TEXT NOT NULL, summary TEXT NOT NULL, structured_body JSONB NOT NULL,
 validation_state TEXT NOT NULL, PRIMARY KEY(story_id,locale)
);
CREATE TABLE pipeline_runs (
 id TEXT PRIMARY KEY, started_at TIMESTAMPTZ NOT NULL DEFAULT now(), ended_at TIMESTAMPTZ,
 mode TEXT NOT NULL, status TEXT NOT NULL, stage TEXT NOT NULL, stats JSONB NOT NULL, error TEXT
);
CREATE TABLE delivery_logs (
 id TEXT PRIMARY KEY, issue_id TEXT REFERENCES issues(id), channel TEXT NOT NULL,
 status TEXT NOT NULL, delivered_at TIMESTAMPTZ, error TEXT
);
