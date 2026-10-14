import json, sys
repo = sys.argv[1]
def in_ring(x, y, ring):
    inside = False; n = len(ring); j = n - 1
    for i in range(n):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi: inside = not inside
        j = i
    return inside
pts = {'Laayoune': (-13.20, 27.15), 'Dakhla': (-15.93, 23.70), 'Tifariti': (-10.60, 26.16), 'Bir Lehlou': (-9.60, 26.35), 'Smara': (-11.67, 26.74), 'ground-1': (-12.3587, 25.1654), 'ground-2': (-12.2831, 25.399), 'Tan-Tan(MA proper)': (-11.10, 28.44)}
for f in ('data/africa_basemap.json', 'data/africa_basemap_10m.json'):
    b = json.load(open(repo + '/' + f))
    C = {c['iso']: c for c in b['countries'] if c['iso'] in ('MA', 'EH')}
    print(f, 'order:', [c['iso'] for c in b['countries'] if c['iso'] in ('MA','EH')])
    for k, (x, y) in pts.items():
        r = {iso: any(in_ring(x, y, p[0]) for p in C[iso]['p']) for iso in C}
        print('  ', k, r)
