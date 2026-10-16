import json, os, tempfile, time, urllib.request, urllib.parse, urllib.error, sys

UA = {'User-Agent': 'jarvis-research', 'Accept': 'application/vnd.github+json'}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_MD = os.path.join(ROOT, 'jarvis-research-roster.md')
OUT_JSON = os.path.join(tempfile.gettempdir(), 'jarvis-research-roster.json')
TOP_MARK = '## Top picks — what to borrow for JARVIS'

def search(q, page=1):
    url = ('https://api.github.com/search/repositories?q=' + urllib.parse.quote(q) +
           '&sort=stars&order=desc&per_page=100&page=%d' % page)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                print('  rate-limited (%d), sleeping 40s [%d]' % (e.code, attempt + 1), flush=True)
                time.sleep(40)
            else:
                print('  HTTP %d %s' % (e.code, e.reason), flush=True)
                return None
        except Exception as e:
            print('  net error: %s' % e, flush=True)
            time.sleep(12)
    return None

QUERIES = [
 ('Agent frameworks & orchestration', 'topic:agent-framework stars:>100'),
 ('AI agents (general)', 'topic:ai-agents stars:>100'),
 ('Autonomous agents', 'topic:autonomous-agents stars:>100'),
 ('Agent pattern (broad)', 'topic:agent stars:>800'),
 ('Code / coding agents', 'topic:coding-agent stars:>50'),
 ('MCP / Model Context Protocol', 'topic:mcp stars:>50'),
 ('MCP servers', 'topic:mcp-server stars:>20'),
 ('LLM tooling (broad)', 'topic:llm stars:>1000'),
 ('Browser automation', 'topic:browser-automation stars:>30'),
 ('Headless browsers', 'topic:headless-browser stars:>50'),
 ('Chromium tooling', 'chromium in:name,description stars:>300'),
 ('Electron apps & tooling', 'topic:electron stars:>300'),
 ('Browser extensions', 'topic:browser-extension stars:>300'),
 ('Web scraping & crawling', 'topic:web-scraping stars:>100'),
 ('RAG & retrieval', 'topic:rag stars:>100'),
 ('Vector databases', 'topic:vector-database stars:>100'),
 ('Agent memory (topic)', 'topic:llm-memory stars:>10'),
 ('Long-term memory', '"long-term memory" in:name,description stars:>20'),
 ('Knowledge graphs', 'topic:knowledge-graph stars:>300'),
 ('Embeddings', 'topic:embeddings stars:>100'),
 ('TUIs', 'topic:tui stars:>150'),
 ('Terminal emulators', '"terminal emulator" in:name,description stars:>200'),
 ('Terminal UI frameworks', 'topic:terminal stars:>500'),
 ('CLI tools (high quality)', 'topic:cli stars:>3000'),
 ('LLM evaluation', 'topic:llm-eval stars:>20'),
 ('Prompt engineering', 'topic:prompt-engineering stars:>200'),
 ('Local LLM runners', 'topic:local-llm stars:>100'),
 ('Ollama ecosystem', 'topic:ollama stars:>100'),
 ('LLM UIs', 'topic:llm-ui stars:>30'),
 ('Chat UIs & chatbots', 'topic:chatbot stars:>1000'),
 ('Sandboxes & code exec', 'topic:sandbox stars:>300'),
 ('Static analysis', 'topic:static-analysis stars:>300'),
 ('Secret scanning', 'topic:secret-detection stars:>20'),
 ('LLMOps & observability', 'topic:llmops stars:>20'),
 ('Workflow automation', 'topic:workflow-automation stars:>1000'),
 ('Voice assistants', 'topic:voice-assistant stars:>100'),
 ('Speech recognition', 'topic:speech-recognition stars:>1000'),
 ('Personal AI assistants', '"personal assistant" in:name,description stars:>100'),
 ('JARVIS-like projects', 'jarvis in:name stars:>50'),
 ('Password managers', 'topic:password-manager stars:>200'),
 ('Privacy tooling', 'topic:privacy stars:>500'),
 ('Desktop app frameworks', 'topic:desktop-app stars:>2000'),
 ('Monitoring & dashboards', 'topic:monitoring stars:>2000'),
 ('PKM / note-taking', 'topic:pkm stars:>500'),
 ('RPA / automation', 'topic:rpa stars:>100'),
 ('Developer tools', 'topic:developer-tools stars:>2000'),
 ('Chromium-based browsers', 'topic:chromium stars:>500'),
 ('Web browsers (topic)', 'topic:web-browser stars:>200'),
 ('Userscript managers', '"userscript" in:name,description stars:>100'),
 ('Web archiving', '"web archive" in:name,description stars:>100'),
 ('RSS & feed readers', 'topic:rss-reader stars:>100'),
 ('Chat UI components', 'topic:chat-ui stars:>50'),
 ('AI SDK / streaming UI', 'topic:ai-sdk stars:>50'),
 ('AI browser agents', 'topic:browser-agent stars:>20'),
 ('Code intelligence (tree-sitter)', 'topic:tree-sitter stars:>100'),
 ('Code search & indexing', 'topic:code-search stars:>100'),
 ('Local-first & sync', 'topic:local-first stars:>200'),
 ('Self-hosted search', 'topic:search-engine stars:>500'),
 ('Text-to-speech', 'topic:text-to-speech stars:>200'),
 ('OCR', 'topic:ocr stars:>200'),
 ('PDF tooling', 'topic:pdf stars:>500'),
 ('Maps & geo', 'topic:maps stars:>500'),
 ('Data visualization', 'topic:visualization stars:>1500'),
 ('Market data & trading', 'topic:market-data stars:>100'),
 ('Awesome lists (meta)', 'awesome in:name stars:>5000'),
 ('Agentic AI (2026 wave)', 'topic:agentic-ai stars:>100'),
 ('Claude Code ecosystem', '"claude code" in:name,description stars:>300'),
 ('opencode ecosystem', 'opencode in:name,description stars:>50'),
 ('MCP registries', 'mcp registry in:name,description stars:>50'),
 ('Self-hosted apps', 'topic:self-hosted stars:>1000'),
 ('Structured output & extraction', 'topic:structured-output stars:>20'),
]

seen = {}
def take(items, cat):
    new = 0
    for it in items:
        key = (it.get('full_name') or '').lower()
        if not key or key in seen:
            continue
        seen[key] = {
            'cat': cat,
            'name': it['full_name'],
            'url': it.get('html_url') or ('https://github.com/' + it['full_name']),
            'stars': it.get('stargazers_count') or 0,
            'desc': (it.get('description') or '').replace('\n', ' ').replace('\r', ' ').strip()[:140],
            'lang': it.get('language') or '',
            'lic': ((it.get('license') or {}).get('spdx_id') or 'NOASSERTION'),
            'pushed': (it.get('pushed_at') or '')[:7],
        }
        new += 1
    return new

for cat, q in QUERIES:
    d = search(q)
    items = (d or {}).get('items') or []
    new = take(items, cat)
    print('%-44s fetched %3d  new %3d  total %4d' % (cat[:44], len(items), new, len(seen)), flush=True)
    time.sleep(6.6)

if len(seen) < 1050:
    for cat, q in QUERIES:
        if len(seen) >= 1050:
            break
        d = search(q, 2)
        items = (d or {}).get('items') or []
        if items:
            take(items, cat)
        time.sleep(6.6)

print('TOTAL UNIQUE:', len(seen), flush=True)

cats = {}
for r in seen.values():
    cats.setdefault(r['cat'], []).append(r)

def fmt_stars(n):
    return ('%.1fk' % (n / 1000.0)) if n >= 1000 else str(n)

shown = {}
for cap in (30, 40, 50, 60):
    shown = {c: sorted(v, key=lambda r: -r['stars'])[:cap] for c, v in cats.items()}
    if sum(len(v) for v in shown.values()) >= 1000:
        break
total_shown = sum(len(v) for v in shown.values())

lines = []
lines.append('# JARVIS MK-X — GitHub Research Roster')
lines.append('')
lines.append('**Generated**: 2026-10-16 · GitHub Search API, stars-sorted, deduped · %d targeted queries across agent / browser / memory / security / UX / platform domains.' % len(QUERIES))
lines.append('**Purpose**: research corpus feeding JARVIS MK-X + Orbit. Companion: `jarvis-research-tags.md` (curated adoption analysis).')
lines.append('**Principle**: extract patterns, do not blindly install. Nothing here destabilizes an active sprint (AGENTS.md research rule).')
lines.append('')
lines.append('---')
lines.append('')
lines.append('## Top picks — what to borrow for JARVIS')
lines.append('')
lines.append('<!-- TOP-PICKS -->')
lines.append('')
lines.append('---')
lines.append('')
lines.append('## Roster — %d repos shown (from %d collected, %d categories)' % (total_shown, len(seen), len(cats)))
lines.append('')
for cat, _q in QUERIES:
    items = shown.get(cat) or []
    if not items:
        continue
    lines.append('### %s (%d)' % (cat, len(items)))
    lines.append('')
    for r in items:
        meta = ' · '.join([x for x in (r['lang'], r['lic'], r['pushed']) if x])
        if r['desc']:
            lines.append('- [%s](%s) ★%s — %s · %s' % (r['name'], r['url'], fmt_stars(r['stars']), r['desc'], meta))
        else:
            lines.append('- [%s](%s) ★%s · %s' % (r['name'], r['url'], fmt_stars(r['stars']), meta))
    lines.append('')

out = '\n'.join(lines) + '\n'
if os.path.exists(OUT_MD):
    try:
        old = open(OUT_MD).read()
    except Exception:
        old = ''
    h = old.find(TOP_MARK)
    if h >= 0:
        h2 = old.find('\n---\n', h)
        if h2 > h:
            body = old[h + len(TOP_MARK):h2].strip('\n')
            if body:
                out = out.replace('<!-- TOP-PICKS -->', body)
open(OUT_MD, 'w').write(out)
json.dump(list(seen.values()), open(OUT_JSON, 'w'), indent=1)

print('WROTE %s (%d lines)' % (OUT_MD, len(lines)), flush=True)
print('=== TOP 110 BY STARS ===', flush=True)
for r in sorted(seen.values(), key=lambda x: -x['stars'])[:110]:
    print('%s ★%s — %s' % (r['name'], fmt_stars(r['stars']), r['desc'][:88]), flush=True)
