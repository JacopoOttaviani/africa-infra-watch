"""Print part endpoints for named pipelines. Usage: python3 -I geom.py <ggit> <goit> name1 name2 ..."""
import json, sys
names = sys.argv[3:]
for path in sys.argv[1:3]:
    for f in json.load(open(path))["features"]:
        p = f.get("properties") or {}
        nm = (p.get("PipelineName") or "") + " · " + (p.get("SegmentName") or "")
        if not any(n.lower() in nm.lower() for n in names):
            continue
        g = f.get("geometry") or {}
        t = g.get("type")
        parts = [g["coordinates"]] if t == "LineString" else (g.get("coordinates") or []) if t == "MultiLineString" else []
        print(nm, "|", p.get("Status"), "|", p.get("CountriesOrAreas"), "|", p.get("StartLocation"), "->", p.get("EndLocation"), "| RouteAccuracy", p.get("RouteAccuracy"), "|", t, len(parts), "parts")
        for i, pt in enumerate(parts):
            print(f"   part {i}: {len(pt)} pts  start {pt[0][0]:.3f},{pt[0][1]:.3f}  end {pt[-1][0]:.3f},{pt[-1][1]:.3f}")
