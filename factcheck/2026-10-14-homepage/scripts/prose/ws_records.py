import json, sys, collections
m = json.load(open(sys.argv[1] + '/docs/data/map.json', encoding='utf-8'))
L = ('assets','finance','ground','pipelines','cables','china','eu','mattei')
ma_in_ws = collections.Counter(); eh = collections.Counter()
for k in L:
    v = m[k]; rows = [dict(zip(v['cols'], r)) for r in v['rows']]
    for r in rows:
        isos = r.get('isos') or [r.get('iso')]
        if 'EH' in isos: eh[k] += 1
        if r.get('iso') == 'MA' and r.get('lat') is not None and r['lat'] < 27.66 and r['lon'] < -8.6:
            ma_in_ws[k] += 1
print('records counted under Western Sahara by layer:', dict(eh), sum(eh.values()))
print('records filed under Morocco with a point south of 27.66N (inside Western Sahara territory):', dict(ma_in_ws), sum(ma_in_ws.values()))
