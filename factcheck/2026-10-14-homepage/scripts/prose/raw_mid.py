import json, sys
repo = sys.argv[1]
want = {'411024293', '441934983', '1135660175', '859036875', '1414739907'}
g = json.load(open(repo + '/data/osm_construction.geojson', encoding='utf-8'))
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
for f in g['features']:
    oid = (f['properties'].get('osm_id') or '').replace('way/', '')
    if oid in want:
        c = f['geometry']['coordinates']; mid = c[len(c)//2]
        print(oid, f['properties'].get('name'), f['properties'].get('sector'), 'n_vertices', len(c), 'raw midpoint', mid, '->', loc(mid[0], mid[1]))
