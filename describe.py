#!/usr/bin/env python3
"""توضیح فارسی کارکرد هر فایل را با Claude می‌سازد و در docs/descriptions.json نگه می‌دارد.
فقط فایل‌های جدید یا تغییرکرده (بر اساس hash) دوباره پردازش می‌شوند.
usage: ANTHROPIC_API_KEY=... python describe.py --android A --windows W --web public_html [--max 150] [--dry]
"""
import argparse, json, os, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

MODEL = 'claude-haiku-5-5'
PROMPT = """این فایل بخشی از برنامه‌ی «پسته‌بازار» (مدیریت خرید و فروش، انبار، کارگاه و حسابداری پسته) است.
در ۲ تا ۳ جمله‌ی کوتاه و به فارسی ساده توضیح بده این فایل دقیقاً چه کاری انجام می‌دهد و در برنامه چه نقشی دارد.
مخاطب مدیر پروژه است نه برنامه‌نویس: از اصطلاح فنی تا حد امکان پرهیز کن و نام تابع‌ها را تکرار نکن.
فقط خود توضیح را بنویس، بدون مقدمه.

مسیر: {path}   (بخش: {group})
کامنت سرفایل: {doc}
به این فایل‌ها وصل است: {out}
این فایل‌ها آن را صدا می‌زنند: {inn}

--- ابتدای کد ---
{code}"""


def ask(prompt, key):
    body = json.dumps({'model': MODEL, 'max_tokens': 350, 'messages': [{'role': 'user', 'content': prompt}]}).encode()
    for k in range(4):
        req = urllib.request.Request('https://api.anthropic.com/v1/messages', body, {
            'content-type': 'application/json', 'x-api-key': key, 'anthropic-version': '2023-06-01'})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return ''.join(b.get('text', '') for b in json.load(r)['content']).strip()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 529): time.sleep(5 * (k + 1)); continue
            print('API error', e.code, e.read()[:200]); return None
        except Exception as e:
            time.sleep(3)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--android'); ap.add_argument('--windows'); ap.add_argument('--web')
    ap.add_argument('--graph', default='docs/graph.json'); ap.add_argument('--out', default='docs/descriptions.json')
    ap.add_argument('--max', type=int, default=150); ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    g = json.load(open(a.graph, encoding='utf-8'))
    desc = json.load(open(a.out, encoding='utf-8')) if os.path.exists(a.out) else {}
    roots = {'android': a.android, 'windows': a.windows, 'web': a.web, 'backend': a.web, 'admin': a.web}
    N = {n['id']: n for n in g['nodes']}
    out, inn = {}, {}
    for l in g['links']:
        out.setdefault(l['source'], []).append(N[l['target']]['label']); inn.setdefault(l['target'], []).append(N[l['source']]['label'])
    todo, seen = [], set()
    for n in g['nodes']:
        h = n.get('hash')
        if not h or h in desc or h in seen or n['group'] not in roots or not roots[n['group']]: continue
        seen.add(h); todo.append(n)
    todo = todo[:a.max]
    print(f'{len(desc)} موجود، {len(todo)} فایل برای توضیح (حداکثر {a.max})')
    if a.dry or not todo: return
    key = os.environ['ANTHROPIC_API_KEY']

    def work(n):
        code = open(os.path.join(roots[n['group']], n['path']), encoding='utf-8', errors='ignore').read()[:6000]
        t = ask(PROMPT.format(path=n['path'], group=n['group'], doc=n.get('doc') or '-',
                              out='، '.join(sorted(set(out.get(n['id'], [])))[:12]) or '-',
                              inn='، '.join(sorted(set(inn.get(n['id'], [])))[:12]) or '-', code=code), key)
        return n['hash'], t
    with ThreadPoolExecutor(4) as ex:
        for h, t in ex.map(work, todo):
            if t: desc[h] = {'fa': t, 'm': MODEL}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(desc, open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print('ذخیره شد:', len(desc), 'توضیح')


if __name__ == '__main__':
    main()
