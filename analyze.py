#!/usr/bin/env python3
"""Build graph.json from the Android repo, Windows repo and the public_html (web + PHP backend).

usage: python analyze.py --android A --windows W --web public_html [--infra infra.json] -o docs/graph.json
Never reads/exports secrets: config*.php, data/, *.bak and private/ are skipped.
"""
import argparse, hashlib, json, os, posixpath, re, time
from pathlib import Path

SKIP = re.compile(r'(config[^/]*\.php|/data/|\.bak$|\.example$|/private/|/node_modules/|/\.git/)')
ACTION_PHP = re.compile(r"""(?:case\s+)?['"]([a-z][a-z0-9_]*\.[a-z0-9_.]+)['"]\s*(?:=>|:)""")
ACTION_ANY = re.compile(r"""['"]([a-z][a-z0-9_]*\.[a-z0-9_.]+)['"]""")
PHP_FILE = re.compile(r"""['"/]([a-z][a-z0-9_]*\.php)\b""")
REQ = re.compile(r"""(?:require|include)(?:_once)?\s*\(?\s*(?:__DIR__\s*\.\s*)?['"]/?([A-Za-z0-9_/.\-]+\.php)['"]""")
TABLE = re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+`?([a-z][a-z0-9_]+)`?", re.I)
CREATE = re.compile(r"CREATE TABLE(?: IF NOT EXISTS)?\s+`?([a-z][a-z0-9_]+)`?", re.I)
DART_IMP = re.compile(r"""^\s*(?:import|export|part)\s+['"]([^'"]+)['"]""", re.M)


def read(p):
    return Path(p).read_text(encoding='utf-8', errors='ignore')


def files(root, exts):
    root = Path(root)
    for p in sorted(root.rglob('*')):
        rel = '/' + p.relative_to(root).as_posix()
        if p.is_file() and p.suffix in exts and not SKIP.search(rel):
            yield p, rel[1:]


def doc_of(txt):
    """توضیح داخل خود فایل: کامنت سرفایل، یا ///کامنت اولین کلاس (Dart)."""
    head = txt[:3000]
    m = re.search(r'/\*\*?(.*?)\*/', head, re.S)
    if m and m.start() < 600:
        t = m.group(1)
    else:
        lines = [l.strip() for l in head.split('\n')[:60]]
        c = []
        for l in lines:
            if l.startswith('//'): c.append(l.lstrip('/').strip())
            elif c: break
            elif l and not l.startswith(('<?php', 'declare', '#!', 'import', 'library', "'use ")): 
                if not l.startswith(('//', '/*')): continue
        t = ' '.join(c)
        if not t:
            m = re.search(r'((?:^[ \t]*///.*\n)+)[ \t]*(?:abstract |final )?(?:class|mixin|enum|extension)\b', txt, re.M)
            t = ' '.join(x.strip().lstrip('/').strip() for x in m.group(1).split('\n')) if m else ''
    t = re.sub(r'^\s*\*+ ?', '', t, flags=re.M)
    t = re.sub(r'\s+', ' ', t).strip(' *-')
    return t[:260] if len(t) > 12 else ''


def area(name):
    return re.sub(r'\.(dart|php|js)$', '', os.path.basename(name)).split('_')[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--android'); ap.add_argument('--windows'); ap.add_argument('--web')
    ap.add_argument('--infra'); ap.add_argument('-o', default='graph.json')
    a = ap.parse_args()

    nodes, edges = {}, {}

    def node(i, **kw):
        nodes.setdefault(i, {'id': i, **kw})

    def edge(s, t, kind):
        if s != t and s in nodes and t in nodes:
            e = edges.setdefault((s, t, kind), {'source': s, 'target': t, 'kind': kind, 'w': 0})
            e['w'] += 1

    texts = {}
    # ---- Flutter repos
    dart = {}
    for grp, root in (('android', a.android), ('windows', a.windows)):
        if not root: continue
        for p, rel in files(root, {'.dart'}):
            if rel.startswith('test/'): continue
            i = f'{grp}:{rel}'
            node(i, label=os.path.basename(rel), group=grp, area=area(rel), path=rel,
                 hash=hashlib.md5(p.read_bytes()).hexdigest()[:8], lines=read(p).count('\n'))
            texts[i] = read(p); dart[i] = (grp, rel)
    for i, (grp, rel) in dart.items():
        for imp in DART_IMP.findall(texts[i]):
            if imp.startswith('dart:') or (imp.startswith('package:') and not imp.startswith('package:pesteh_bazar/')):
                continue
            imp = imp.replace('package:pesteh_bazar/', 'lib/')
            cand = posixpath.normpath(posixpath.join(posixpath.dirname(rel), imp)) if not imp.startswith('lib/') else imp
            t = f'{grp}:{cand}'
            if t not in nodes: t = f'{grp}:lib/{os.path.basename(imp)}'
            edge(i, t, 'import')
    # same file in both repos -> "shared" link
    for i, n in list(nodes.items()):
        if n['group'] == 'android':
            j = 'windows:' + n['path']
            if j in nodes:
                same = n['hash'] == nodes[j]['hash']
                n['shared'] = nodes[j]['shared'] = 'same' if same else 'diff'
                edge(i, j, 'shared-same' if same else 'shared-diff')

    # ---- Web + backend
    actions, tables = {}, set()
    php = {}
    if a.web:
        for p, rel in files(a.web, {'.php', '.js', '.sql'}):
            if p.suffix == '.sql':
                tables |= set(m.lower() for m in CREATE.findall(read(p))); continue
            if p.suffix == '.php' and rel.startswith(('backend/', 'admin/', 'api/')):
                g = 'admin' if 'admin/' in rel else 'backend'
                i = f'{g}:{rel}'
                node(i, label=os.path.basename(rel), group=g, area=area(rel), path=rel, lines=read(p).count('\n'))
                texts[i] = read(p); php[i] = rel
                for act in ACTION_PHP.findall(texts[i]): actions.setdefault(act, i)
                tables |= set(m.lower() for m in CREATE.findall(texts[i]))
            elif p.suffix == '.js' and rel.startswith('app/'):
                i = f'web:{rel}'
                node(i, label=os.path.basename(rel), group='web', area=area(rel), path=rel, lines=read(p).count('\n'))
                texts[i] = read(p)
        # php -> php requires, php -> tables
        by_base = {os.path.basename(r): i for i, r in php.items()}
        for i in php:
            for r in REQ.findall(texts[i]):
                edge(i, by_base.get(os.path.basename(r), ''), 'require')
            for t in set(m.lower() for m in TABLE.findall(texts[i])):
                if t in tables:
                    node(f'db:{t}', label=t, group='db', area='db'); edge(i, f'db:{t}', 'sql')
        # clients -> backend (by action name or direct php file name)
        for i, (g, rel) in list(dart.items()) + [(k, ('web', v['path'])) for k, v in nodes.items() if v['group'] == 'web']:
            for act in set(ACTION_ANY.findall(texts[i])):
                if act in actions: edge(i, actions[act], 'api')
            for f in set(PHP_FILE.findall(texts[i])):
                if f in by_base: edge(i, by_base[f], 'api')

    # ---- infrastructure (hand written: servers, hosting, db)
    if a.infra and os.path.exists(a.infra):
        inf = json.load(open(a.infra, encoding='utf-8'))
        for n in inf['nodes']: node(f"infra:{n['id']}", label=n.get('label', n['id']), group='infra', area='infra', host=n.get('host'))
        for l in inf['links']:
            s, t = (x if ':' in x else f'infra:{x}' for x in (l['from'], l['to'])); edge(s, t, 'infra')

    for i, n in nodes.items():
        if i in texts: n['doc'] = doc_of(texts[i])
        if i in texts: n.setdefault('hash', hashlib.md5(texts[i].encode('utf-8', 'ignore')).hexdigest()[:8])

    # ---- mark new nodes/edges compared with the previous graph.json
    now = int(time.time()); old_n, old_e = {}, {}
    if os.path.exists(a.o):
        try:
            old = json.load(open(a.o, encoding='utf-8'))
            old_n = {n['id']: n.get('added', 0) for n in old['nodes']}
            old_e = {(e['source'], e['target'], e['kind']): e.get('added', 0) for e in old['links']}
        except Exception: pass
    first = not old_n
    for i, n in nodes.items(): n['added'] = 0 if first else old_n.get(i, now)
    for k, e in edges.items(): e['added'] = 0 if first else old_e.get(k, now)

    out = {'generated': now, 'nodes': list(nodes.values()), 'links': list(edges.values())}
    os.makedirs(os.path.dirname(os.path.abspath(a.o)), exist_ok=True)
    json.dump(out, open(a.o, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    # ---- history (for growth charts): one point per run when counts change
    hp = os.path.join(os.path.dirname(os.path.abspath(a.o)), 'history.json')
    hist = json.load(open(hp, encoding='utf-8')) if os.path.exists(hp) else []
    pt = {'t': now, 'nodes': {}, 'lines': {}, 'edges': len(edges)}
    for n in nodes.values():
        pt['nodes'][n['group']] = pt['nodes'].get(n['group'], 0) + 1
        pt['lines'][n['group']] = pt['lines'].get(n['group'], 0) + n.get('lines', 0)
    if not hist or {k: v for k, v in hist[-1].items() if k != 't'} != {k: v for k, v in pt.items() if k != 't'}:
        hist.append(pt)
    json.dump(hist[-500:], open(hp, 'w'), separators=(',', ':'))
    print(f'{len(nodes)} nodes, {len(edges)} edges -> {a.o}')


if __name__ == '__main__':
    main()
