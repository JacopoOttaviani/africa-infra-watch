import json
_P = None
def load(bm):
    global _P
    cs = json.load(open(bm))["countries"]
    _P = []
    for c in cs:
        for poly in c["p"]:
            xs = [q[0] for q in poly[0]]; ys = [q[1] for q in poly[0]]
            _P.append((min(xs), min(ys), max(xs), max(ys), poly, c["iso"]))
def ring(x, y, r):
    inside = False
    j = len(r) - 1
    for i in range(len(r)):
        xi, yi = r[i][0], r[i][1]; xj, yj = r[j][0], r[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside
def country(lon, lat):
    for x0, y0, x1, y1, poly, iso in _P:
        if not (x0 <= lon <= x1 and y0 <= lat <= y1): continue
        if ring(lon, lat, poly[0]) and not any(ring(lon, lat, h) for h in poly[1:]):
            return iso
    return None
