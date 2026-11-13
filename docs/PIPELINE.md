# Collection and editorial pipeline

## Collection
Use official RSS/Atom/open APIs first. `config/sources.yaml` is the source registry. Use explicit allowed hosts, sensible User-Agent, robots/terms awareness, throttling, backoff, timeouts and SSRF prevention. No paywall bypass. Only retain excerpts or content permitted by source terms.

## Normalization
Canonical URL, publish/event timestamp, source label, language, article excerpt, normalized title and content hash; normalize redirects and tracker parameters safely.

## Deduplication
First exact canonical URL; then title/content similarity; then related-event grouping. Syndicated copies do not count as independent corroboration.

## Scoring
Weights default: industrial relevance 25, real deployment 20, authority 15, corroboration 15, recency 10, significance 10, attention 5. Normalize dimension scores 0–1. Expose score trace and version; allow configuration overrides.

## Editorial
Select up to three distinct leads, then quick bites. Never force filler. Generate structured JSON with source IDs. Verify figures, names, dates, attribution and claims; keep source-backed uncertainty explicit. Produce English and Chinese translations consistently. A bad validation result blocks publication.

## Runtime
`fixture`, `dry-run`, `live` modes; separate stage commands; idempotent keys; pipeline run logs and failed-stage retry. Missing API keys must not break local fixtures.
