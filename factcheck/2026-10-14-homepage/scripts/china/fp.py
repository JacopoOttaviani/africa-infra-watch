import sys, json, os, collections
D = json.load(open(sys.argv[1])); site = json.load(open(sys.argv[2])); cache = sys.argv[3]
sid = set(f["properties"]["aiddata_id"] for f in site["features"])
R = [r for r in D["rows"] if r["AidData Record ID"] in sid]
prec = [r for r in R if r["Geographic Level of Precision Available"]=="Precise"]
n_file = n_nonpoint = n_line = 0; types = collections.Counter()
for r in prec:
    p = os.path.join(cache, f'{r["AidData Record ID"]}.geojson')
    if not os.path.exists(p) or os.path.getsize(p)==0: continue
    n_file += 1
    fc = json.load(open(p)); f0 = fc["features"][0]; g = f0["geometry"]
    polys = g["coordinates"] if g["type"]=="MultiPolygon" else [g["coordinates"]]
    big = False
    for poly in polys:
        xs=[q[0] for q in poly[0]]; ys=[q[1] for q in poly[0]]
        if max(xs)-min(xs) >= 0.0002 or max(ys)-min(ys) >= 0.0002: big=True
    if big: n_nonpoint += 1
print("precise", len(prec), "with GeoGCDF file", n_file, "with a non-point polygon (>=0.0002 deg)", n_nonpoint)
print("files in cache", len(os.listdir(cache)))
