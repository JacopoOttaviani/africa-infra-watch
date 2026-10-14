import json, sys
repo = sys.argv[1]
m = json.load(open(repo + '/docs/data/map.json', encoding='utf-8'))
s = open(repo + '/docs/dashboard.html', encoding='utf-8').read()
j = s.find('const DATA = ') + len('const DATA = ')
d, _ = json.JSONDecoder().raw_decode(s, j)
gm = [dict(zip(m['ground']['cols'], r)) for r in m['ground']['rows']]
gd = d['ground'] if isinstance(d['ground'], list) else [dict(zip(d['ground']['cols'], r)) for r in d['ground']['rows']]
print('dash ground keys', list(gd[0].keys()) if isinstance(gd[0], dict) else None)
b = json.load(open(repo + '/data/africa_basemap.json'))
def in_ring(x, y, ring):
    inside = False; n = len(ring); j = n - 1
    for i in range(n):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi: inside = not inside
        j = i
    return inside
def loc(x, y):
    for c in b['countries']:
        for poly in c['p']:
            if in_ring(x, y, poly[0]) and not any(in_ring(x, y, h) for h in poly[1:]):
                return c['iso']
    return None
for a, bb in zip(gm, gd):
    ib = bb.get('iso') if isinstance(bb, dict) else None
    if a['iso'] != ib:
        g = bb['g'][0]; mid = g[len(g)//2]
        print('map', a['iso'], (a['lon'], a['lat']), loc(a['lon'], a['lat']), '| dash', ib, 'dash-geom-mid', mid, loc(mid[0], mid[1]), '| oid', a['oid'], 'sector', a['sector'], 'km', a['km'])
