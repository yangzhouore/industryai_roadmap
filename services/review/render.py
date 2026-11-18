"""Private offline HTML reports and strict public-projection previews; no approvals."""
from datetime import datetime, timezone
from html import escape
import json
import math
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit
from xml.sax.saxutils import escape as xml_escape

from .analysis import _bounded

CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'; connect-src 'none'"
CSS = 'body{font:16px/1.6 system-ui,sans-serif;max-width:1100px;margin:auto;padding:2rem;color:#202020;background:#faf8f4}h1,h2,h3{line-height:1.3}a{color:#294b70}.pair{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.box{padding:1rem;border:1px solid #aaa;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}nav{display:flex;gap:1rem;flex-wrap:wrap}.notice{padding:1rem;border:2px solid #9c4e1f}@media(max-width:700px){.pair{grid-template-columns:1fr}}'


def _text(value):
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff]', lambda match:'\\u'+format(ord(match.group()),'04x'), str(value))
    return escape(text, quote=True)


def _html(title, content, locale='en'):
    return '<!doctype html><html lang="'+locale+'"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="'+_text(CSP)+'"><title>'+_text(title)+'</title><style>'+CSS+'</style></head><body>'+content+'</body></html>'


def _pair(value, heading):
    value = value if isinstance(value, dict) else {}
    return '<h3>'+_text(heading)+'</h3><div class="pair"><section class="box" lang="en"><strong>English</strong><pre>'+_text(value.get('en',''))+'</pre></section><section class="box" lang="zh"><strong>\u4e2d\u6587</strong><pre>'+_text(value.get('zh',''))+'</pre></section></div>'


def _private_root(output_dir):
    raw = Path(output_dir).absolute()
    if '..' in raw.parts or len(raw.parts) < 3:
        raise ValueError('A new private report subdirectory is required')
    denied = {'public', 'www', 'wwwroot', 'htdocs', '.next', '.git', 'node_modules'}
    parts = [part.casefold() for part in raw.parts]
    repo_trees = any(parts[i:i+2] in (['apps','web'], ['packages','shared']) for i in range(len(parts)-1))
    if repo_trees or any(part.casefold() in denied for part in raw.parts):
        raise ValueError('Public/build/repository output directories are forbidden')
    # Do not resolve first: that would erase evidence of symlink/reparse traversal.
    for parent in [raw, *raw.parents]:
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Report paths cannot traverse symlinks or reparse points')
    repository = Path(__file__).resolve().parents[2]
    try:
        relative = raw.relative_to(repository)
    except ValueError:
        relative = None
    if relative is not None and (len(relative.parts)<2 or relative.parts[0].casefold() != 'artifacts'):
        raise ValueError('In-repository private reports must stay under ignored artifacts')
    if raw.exists():
        raise ValueError('Report output already exists; never overwrite private reports')
    raw.mkdir(mode=0o700, parents=True, exist_ok=False)
    from packages.db.recovery import protect_windows_directory
    protect_windows_directory(raw)
    if os.name != 'nt' and stat.S_IMODE(raw.stat().st_mode) & 0o077:
        raise ValueError('Private report permissions are required')
    return raw


def _write(root, name, content):
    target = root/name
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    encoded = content.encode('utf-8')
    if len(encoded) > 8*1024*1024:
        raise ValueError('Rendered output exceeds its bound')
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'wb') as handle:
        handle.write(encoded)


def _safe_link(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return None


def render_review(issue, findings, suggestions, output_dir):
    """Full private evidence report; explicit creation only, never publish or edit input."""
    _bounded(issue)
    bounded = json.dumps({'findings':findings,'suggestions':suggestions}, ensure_ascii=True, allow_nan=False)
    if len(bounded) > 4*1024*1024 or not isinstance(findings, list) or not isinstance(suggestions, dict):
        raise ValueError('Bounded findings and guidance are required')
    content = '<h1>Private bilingual editorial review</h1><p class="notice">PRIVATE EVIDENCE. Heuristic prompts are not factual/legal certification. Guidance is editable, unapplied and may contain unresolved placeholders. This report creates no approval.</p>'
    content += '<p>Issue: '+_text(issue.get('id',''))+' | '+_text(issue.get('date',''))+'</p>'
    content += _pair(issue.get('title'), 'Edition title') + _pair(issue.get('introduction'), 'Edition introduction')
    for story in issue['stories']:
        if not isinstance(story, dict):
            continue
        sid = story.get('id','')
        content += '<section><h2>Story '+_text(sid)+'</h2>'
        content += '<p>Category/maturity/company: '+_text(story.get('category',''))+' / '+_text(story.get('maturity',''))+' / '+_text(story.get('company',''))+'</p>'
        for field in ('title','summary','why','limitation'):
            content += _pair(story.get(field), field)
        content += '<h3>Citation mapping</h3><pre>'+_text(json.dumps(story.get('sourceIds',[]),ensure_ascii=False,indent=2))+'</pre>'
        content += '<h3>Heuristic findings</h3><ul>'
        for finding in findings:
            if isinstance(finding,dict) and finding.get('storyId') == sid:
                content += '<li>'+_text(finding.get('id',''))+' | '+_text(finding.get('severity',''))+' | '+_text(finding.get('kind',''))+': '+_text(finding.get('reason',''))+'</li>'
        content += '</ul>'+_pair(suggestions.get(sid), 'Editable guidance / no automatic changes')+'</section>'
    content += '<h2>Retained source metadata and bilingual evidence (PRIVATE)</h2>'
    for source in issue['sources']:
        if not isinstance(source,dict):
            continue
        content += '<section><h3>'+_text(source.get('id',''))+' | '+_text(source.get('name',''))+'</h3>'
        link = _safe_link(source.get('url'))
        content += '<p>Original URL: '+('<a rel="noreferrer noopener" href="'+_text(link)+'">'+_text(link)+'</a>' if link else _text(source.get('url','')))+'</p>'
        content += '<pre>'+_text(json.dumps({k:v for k,v in source.items() if k!='excerpt'},ensure_ascii=False,sort_keys=True,indent=2))+'</pre>'
        content += _pair(source.get('excerpt'), 'Source excerpt / retained translation')+'</section>'
    content += '<h2>All scope findings and risk reasons</h2><pre>'+_text(json.dumps(findings,ensure_ascii=False,indent=2))+'</pre>'
    content += '<details><summary>Complete stored snapshot (PRIVATE)</summary><pre>'+_text(json.dumps(issue,ensure_ascii=False,sort_keys=True,indent=2))+'</pre></details>'
    root = _private_root(output_dir)
    _write(root, 'index.html', _html('Private editorial review',content))
    return {'outputDir':str(root),'files':['index.html']}


def _public_issue(issue):
    # Additional fail-closed boundary: caller must use the real shared gate first.
    # This validator cannot and does not establish human approval or originality.
    if issue is None:
        return None
    _bounded(issue)
    def safe_characters(value):
        if isinstance(value,str) and re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff]',value):
            raise ValueError('Public preview contains invalid text characters')
        if isinstance(value,dict):
            for child in value.values(): safe_characters(child)
        elif isinstance(value,list):
            for child in value: safe_characters(child)
    safe_characters(issue)
    issue_keys = {'id','slug','date','state','validated','synthetic','title','introduction','sources','stories'}
    source_keys = {'id','name','url','publishedAt','eventAt','timezone','synthetic'}
    story_keys = {'id','category','maturity','company','kind','title','summary','why','limitation','sourceIds','evidenceStatus','score'}
    if set(issue)!=issue_keys or issue['state']!='published' or issue['validated'] is not True or not isinstance(issue['synthetic'],bool):
        raise ValueError('Only a strict shared-gate PublicIssue projection may be previewed')
    def textpair(value):
        return isinstance(value,dict) and set(value)=={'en','zh'} and all(isinstance(value[x],str) and value[x].strip() for x in ('en','zh'))
    if not textpair(issue['title']) or not textpair(issue['introduction']) or not isinstance(issue['slug'],str) or re.fullmatch(r'[a-z0-9][a-z0-9-]*',issue['slug']) is None:
        raise ValueError('Invalid public projection text/slug')
    if not isinstance(issue['id'],str) or not issue['id'].strip() or not isinstance(issue['date'],str):
        raise ValueError('Invalid public identity/date')
    try:
        if datetime.strptime(issue['date'],'%Y-%m-%d').strftime('%Y-%m-%d') != issue['date']:
            raise ValueError('date')
    except ValueError:
        raise ValueError('Invalid public edition date') from None
    if not issue['stories']:
        raise ValueError('Public edition requires stories')
    source_ids=set()
    for source in issue['sources']:
        if not isinstance(source,dict) or set(source)!=source_keys or not _safe_link(source.get('url')) or not isinstance(source.get('id'),str) or not source['id'].strip() or source['id'] in source_ids or source['synthetic'] is not issue['synthetic']:
            raise ValueError('Invalid public source projection')
        if not all(isinstance(source[k],str) for k in ('name','publishedAt','timezone')) or not (source['eventAt'] is None or isinstance(source['eventAt'],str)):
            raise ValueError('Invalid source metadata')
        source_ids.add(source['id'])
    story_ids=set()
    for story in issue['stories']:
        if not isinstance(story,dict) or set(story)!=story_keys or not all(textpair(story[k]) for k in ('title','summary','why','limitation')):
            raise ValueError('Invalid public story projection')
        if not isinstance(story['sourceIds'],list) or not story['sourceIds'] or not all(isinstance(sid,str) and sid in source_ids for sid in story['sourceIds']):
            raise ValueError('Invalid public citations')
        if not all(isinstance(story[k],str) and story[k].strip() for k in ('id','category','maturity','company','kind','evidenceStatus')):
            raise ValueError('Invalid public story metadata')
        if story['id'] in story_ids or story['kind'] not in ('feature','quick_bite') or story['maturity'] not in ('research','prototype','pilot','deployed','scaling','commercial'):
            raise ValueError('Invalid public story identity/stage')
        story_ids.add(story['id'])
        if story['evidenceStatus'] != ('synthetic' if issue['synthetic'] else 'verified') or len(set(story['sourceIds'])) != len(story['sourceIds']):
            raise ValueError('Invalid public evidence status/citation')
        if isinstance(story['score'],bool) or not isinstance(story['score'],(int,float)) or not 0 <= story['score'] <= 100 or not math.isfinite(story['score']):
            raise ValueError('Invalid public score')
    return issue


def render_preview(public_issue_or_none, output_dir):
    """Offline rendering of ONLY a gate-supplied PublicIssue or a withheld state."""
    issue = _public_issue(public_issue_or_none)
    files = {}
    files['index.html'] = _html('Local public projection preview','<h1>Local public projection preview</h1><p class="notice">'+('WITHHELD - no approved public edition.' if issue is None else 'Shared-gate projection preview only; no publication or policy change.')+'</p><nav><a href="en/index.html">English</a><a href="zh/index.html">\u4e2d\u6587</a></nav>')
    for locale in ('en','zh'):
        en = locale=='en'
        labels = ('Home','Digest','Sources','Archive','Why','Limitations','Original editorial context','Original source') if en else ('\u9996\u9875','\u671f\u520a','\u6765\u6e90','\u5f52\u6863','\u610f\u4e49','\u5c40\u9650','\u539f\u521b\u7f16\u8f91\u80cc\u666f','\u539f\u59cb\u6765\u6e90')
        nav = '<nav>'+''.join('<a href="'+name+'">'+labels[n]+'</a>' for n,name in enumerate(('index.html','digest.html','sources.html','archive.html')))+'<a href="rss.xml">RSS</a></nav>'
        withheld = '<p class="notice">'+('WITHHELD - no approved public edition.' if en else '\u672a\u901a\u8fc7\u516c\u5f00\u5c55\u793a\u5ba1\u6838\uff0c\u6682\u65e0\u53ef\u5c55\u793a\u671f\u520a\u3002')+'</p>'
        demo = '<p class="notice">DEMONSTRATION - synthetic stories and sources.</p>' if issue is not None and issue['synthetic'] else ''
        pages = {name:nav+demo for name in ('index.html','digest.html','sources.html','archive.html')}
        rss_items = ''
        if issue is None:
            pages = {name:body+withheld for name,body in pages.items()}
        else:
            title = _text(issue['title'][locale])
            intro = _text(issue['introduction'][locale])
            edition = '<h1>'+title+'</h1><p>'+_text(issue['date'])+'</p><p>'+intro+'</p>'
            pages['index.html'] += edition+'<ul>'+''.join('<li>'+_text(story['title'][locale])+'</li>' for story in issue['stories'])+'</ul>'
            pages['archive.html'] += '<h1>'+labels[3]+'</h1><p>'+_text(issue['date'])+' <a href="digest.html">'+title+'</a></p>'
            pages['digest.html'] += edition
            for story in issue['stories']:
                pages['digest.html'] += '<section><h2>'+_text(story['title'][locale])+'</h2><p>'+_text(story['category'])+' / '+_text(story['maturity'])+'</p><p>'+_text(story['summary'][locale])+'</p><h3>'+labels[4]+'</h3><p>'+_text(story['why'][locale])+'</p><h3>'+labels[5]+'</h3><p>'+_text(story['limitation'][locale])+'</p><p>Citations: '+_text(', '.join(story['sourceIds']))+'</p></section>'
            pages['sources.html'] += '<h1>'+labels[2]+'</h1>'
            for source in issue['sources']:
                summaries = [s['summary'][locale] for s in issue['stories'] if source['id'] in s['sourceIds']]
                pages['sources.html'] += '<section><h2>'+_text(source['name'])+'</h2><p>'+_text(source['publishedAt'])+' / '+_text(source['eventAt'] or 'Event date not specified')+' / '+_text(source['timezone'])+'</p><p>'+labels[6]+': '+_text('\n'.join(summaries))+'</p><a rel="noreferrer noopener" href="'+_text(source['url'])+'">'+labels[7]+'</a></section>'
            # Relative links remain local and never suggest a production domain.
            rss_items = '<item><title>'+xml_escape(('[DEMO] ' if issue['synthetic'] else '')+issue['title'][locale])+'</title><link>digest.html</link><guid isPermaLink="false">'+xml_escape(issue['id'])+'</guid><description>'+xml_escape(issue['introduction'][locale])+'</description></item>'
        for name,body in pages.items():
            files[locale+'/'+name] = _html('Public projection preview',body,locale)
        files[locale+'/rss.xml'] = '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Local public projection preview</title><link>index.html</link><description>Offline gate projection preview</description><language>'+locale+'</language>'+rss_items+'</channel></rss>'
    root = _private_root(output_dir)
    for name,content in files.items():
        _write(root,name,content)
    return {'outputDir':str(root),'files':sorted(files)}
