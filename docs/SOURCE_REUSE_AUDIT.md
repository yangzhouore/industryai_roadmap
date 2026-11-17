# Source reuse and attribution audit - rechecked 2026-11-17

## Scope and release decision
This review records publisher evidence, not a blanket legal clearance or a jurisdiction-specific exception.
All six active registry sources currently allow only local research in project policy; redistribution_permitted remains false.
No feed's availability, robots response, policy_reviewed flag or AI verification establishes a public-content license.
Public deployment is blocked until the intended display, translations and business model satisfy applicable permissions.

## Publisher evidence and decisions
| Source | Verified evidence | Current public-display decision |
| --- | --- | --- |
| MIT News | [Republication policy](https://news.mit.edu/terms-of-use) expressly permits third-party story republication with specified attribution. Images have a separate noncommercial/no-derivatives license. | Conditional story permission exists; do not assume it covers translated/adapted excerpts. Implement required notices or obtain clarification before public use. |
| NVIDIA | [RSS terms](https://www.nvidia.com/en-us/about-nvidia/rss/) restrict RSS use to noncommercial purposes and reserve cessation rights. | No commercial clearance. Confirm the proposed public noncommercial display and translation rights; otherwise obtain permission. |
| AWS Industries | [Site terms](https://aws.amazon.com/terms/) reserve content rights and limit downloading, derivative/commercial reuse; a separate documentation license applies to docs.aws.amazon.com, not these blog articles. | No general blog-republication grant verified. Written permission or an applicable article-specific license is needed before relying on copied excerpts/translations. |
| Microsoft Cloud | [Terms](https://www.microsoft.com/en-us/legal/terms-of-use) reserve rights and limit copying, distribution, display and derivative works unless separately authorized. | Identify any blog/article-specific grant or request permission; no blanket clearance from the RSS endpoint. |
| Schneider Electric | [Terms](https://www.se.com/ww/en/about-us/legal/terms-of-use/) restrict reproduction beyond personal noncommercial use without written permission and contain a hyperlink restriction. | Further publisher clarification/approval required, including applicability to the blog and proposed links. |
| Siemens Simcenter | [Publisher blog](https://blogs.sw.siemens.com/simcenter/) identifies authors but supplies no verified republication grant in this audit. [Global terms](https://www.siemens.com/global/en/general/terms-of-use.html) timed out; the software-specific terms URL was inaccessible. | Unresolved. Record the fetch limitation; obtain applicable terms and permission rather than infer a license. |

MIT's story conditions include original headline/subheadline, author byline and linked MIT News citation at the top,
plus the prescribed permission notice and MIT News homepage link at the bottom. These conditions are not image permissions.
The image restriction must not be misrepresented as the license for all MIT story text.

## Existing website attribution gaps
- Source notebooks show publisher name, original URL, publication time, excerpts in EN/ZH and citation references.
- Collected metadata retains authors/original titles, but the public Source contract does not expose author/subheadline fields.
- Current pages do not implement MIT's complete republication notice layout.
- Bilingual source excerpts reproduce/translate publisher prose; 400-character retention alone is not a legal safe harbor.
- Private evidence retention, public excerpt display, images/logos and original editorial writing need separate decisions.
- No existing article or edition was deleted or rewritten during this review.

## Preferred publication policy before launch
1. Write independently phrased summaries and analysis of verifiable facts; retain uncertainty and source attribution.
2. Link to original publisher pages and keep a factual citation record; check source-specific link restrictions.
3. Keep retained evidence/private quote pointers out of public display unless a license or approved legal basis covers them.
4. Use no publisher images, logos, full articles or translated source passages without appropriate permission.
5. Where MIT's story policy is used, satisfy every notice/byline requirement and clarify adaptations/translations.
6. Record per-source/article license URL, checked date, allowed uses, conditions and approval evidence before changing registry flags.
7. Seek publisher approval when terms are unclear; do not mark licensing complete on the basis of a feed response.

## Disabled sources
arXiv, The Robot Report, Rockwell and the Siemens root-feed candidate remain disabled for the recorded availability/policy reasons.
arXiv article licenses vary; metadata access does not establish one license for every article or image.
No restricted endpoint was bypassed and no permission-request email was sent.

## Evidence limits
MIT, NVIDIA, AWS, Microsoft and Schneider terms were re-read November 17; Siemens global terms timed out again.
Publisher terms and item-specific notices can change; section references are recorded in the machine-readable review.
This audit does not claim paid/public hosting approval from any publisher or resolve statutory quotation exceptions.
Machine-readable decisions are in config/source_reuse_review.json; public_display_approved is false for every current source.

## MVP-4.2 independent-summary and link questions
[Public content audit](PUBLIC_CONTENT_AUDIT.md) maps every public field and private evidence boundary.
Each publisher now has a separate pending original-summary/link question in the evidence registry.
All public_display_approved flags and review_complete remain false; no copied-text rights are inferred.
The collection registry describes local research policy, not a verified blanket private-copying license.
Schneider blog/link applicability and Siemens applicable terms remain unresolved even for a links-only design.
A separate exact-content editorial/public-source policy must govern public output; this registry grants no approval.
