import json, sys
g = json.load(open(sys.argv[1], encoding='utf-8'))
def in_ring(x, y, ring):
    inside = False; n = len(ring); j = n - 1
    for i in range(n):
        xi, yi = ring[i][:2]; xj, yj = ring[j][:2]
        if (yi > y) != (yj > y):
            if x < (xj - xi) * (y - yi) / (yj - yi) + xi: inside = not inside
        j = i
    return inside
def polys(geom):
    return [geom['coordinates']] if geom['type'] == 'Polygon' else geom['coordinates']
pts = {'Laayoune': (-13.20, 27.15), 'Smara': (-11.67, 26.74), 'Tifariti': (-10.60, 26.16), 'Bir Lehlou': (-9.60, 26.35)}
for f in g['features']:
    p = f['properties']
    if p.get('ADMIN') in ('Morocco', 'Western Sahara', 'Somaliland') or p.get('NAME') in ('W. Sahara',):
        res = {k: any(in_ring(x, y, pl[0]) for pl in polys(f['geometry'])) for k, (x, y) in pts.items()}
        print(p.get('ADMIN'), p.get('ISO_A2'), p.get('SOVEREIGNT'), p.get('TYPE'), '| NOTE:', (p.get('NOTE_ADM0') or ''), (p.get('NOTE_BRK') or ''), res)
print('NE version field:', g['features'][0]['properties'].get('NE_VERSION') or g['features'][0]['properties'].get('ne_version'))
