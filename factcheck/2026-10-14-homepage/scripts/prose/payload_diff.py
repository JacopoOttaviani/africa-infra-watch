import json, sys, re, collections
repo = sys.argv[1]
m = json.load(open(repo + '/docs/data/map.json', encoding='utf-8'))
s = open(repo + '/docs/dashboard.html', encoding='utf-8').read()
i = s.find('const DATA = ')
j = i + len('const DATA = ')
dec = json.JSONDecoder()
d, end = dec.raw_decode(s, j)
L = ('assets','finance','ground','pipelines','cables','china','eu','mattei')
def recs(P):
    out = {}
    for k in L:
        v = P[k]
        if isinstance(v, list):
            out[k] = v
        else:
            out[k] = [dict(zip(v['cols'], r)) for r in v['rows']]
    return out
M = recs(m); D = recs(d)
def cnt(R):
    c = collections.Counter()
    for k in L:
        for r in R[k]:
            isos = r.get('isos') or ([r['iso']] if r.get('iso') else [])
            for x in isos:
                if x: c[x] += 1
    return c
cm, cd = cnt(M), cnt(D)
print('countries map', len(cm), 'dash', len(cd))
for x in sorted(set(cm)|set(cd)):
    if cm[x] != cd[x]: print('DIFF', x, m['names'].get(x), cm[x], cd[x])
# per-layer diffs
for k in L:
    a, b = M[k], D[k]
    if len(a) != len(b): print(k, 'len differs', len(a), len(b)); continue
    nd = 0
    for ra, rb in zip(a, b):
        ia = ra.get('isos') or [ra.get('iso')]
        ib = rb.get('isos') or [rb.get('iso')]
        if ia != ib:
            nd += 1
            if nd <= 12: print(' ', k, repr(ra.get('name'))[:60], ia, '->', ib, ra.get('lon'), ra.get('lat'))
    print(k, 'records with different country:', nd)
print('names in map payload:', len([x for x in cm]), sorted(m['names'].get(x, x) for x in cm))
