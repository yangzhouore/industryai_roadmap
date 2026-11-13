# Database contract (minimum)

- `sources`: id, name, homepage, feed_url, source_type, active, fetch_policy, timestamps.
- `raw_articles`: id, source_id, canonical_url UNIQUE, title, body_excerpt, published_at, event_at, collected_at, content_hash, raw_metadata.
- `story_clusters`: id, label, event_date, category, maturity, status.
- `article_cluster_links`: cluster_id, article_id UNIQUE pair.
- `entities`: id, name, entity_type, canonical_name.
- `story_entity_links`: cluster_id, entity_id, relationship.
- `scores`: cluster_id, scoring_version, dimensions_json, final_score, scored_at.
- `issues` (Prisma DigestIssue): id, issue_date UNIQUE, slug UNIQUE, state (draft/validated/published), published_at.
- `digest_stories`: id, issue_id, cluster_id, position, kind (feature/quick_bite), structured_content, evidence_status.
- `story_citations`: story_id, raw_article_id, claim_key, source_url, excerpt_or_pointer.
- `translations`: story_id, locale, title, summary, structured_body, validation_state.
- `pipeline_runs`: id, started_at, ended_at, mode, status, stage, stats, error.
- `delivery_logs`: id, issue_id, channel, status, delivered_at, error.
- `edition_revisions`: id, issue_id, revision UNIQUE per issue, content, review, archived_at; append-only SQL trigger.

Add foreign keys, unique constraints, useful indexes and PostgreSQL full-text search + pg_trgm. The lead freezes the contract before parallel development. Use seed fixtures with realistic but clearly synthetic stories and no false source URLs.
