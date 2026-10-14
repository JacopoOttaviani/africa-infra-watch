"""Corrected totals. Usage: python3 -I corrected.py <power.csv> <ggit> <goit>"""
import csv, json, sys, runpy, io, contextlib
# power with The Gambia added
ns = {}
src = open("power.py").read().split("rows = list(")[0]
exec(src, ns)
AF = ns["AFRICA_NAMES"] | {"The Gambia"}; ST = ns["GEM_STATUS"]
rows = [r for r in csv.DictReader(open(sys.argv[1], encoding="utf-8")) if r["country-area1"].strip() in AF]
mw = lambda r: round(float(r["capacity"]), 1) if r["capacity"] else 0.0
pipe = [r for r in rows if ST.get(r["status"]) in ("announced", "approved", "under_construction")]
print("POWER incl. The Gambia: units", len(rows), "countries", len({r["country-area1"] for r in rows}),
      "projects", len({r["project-id"] for r in rows}), "GW %.1f" % (sum(map(mw, rows)) / 1000),
      "pipeline GW %.1f in %d units" % (sum(map(mw, pipe)) / 1000, len(pipe)))
from collections import Counter
print("  status", Counter(ST.get(r["status"]) for r in rows))
print("  exact share %.1f%%" % (100 * sum(r["location-accuracy"] == "exact" for r in rows) / len(rows)))
# pipelines with GEM-wiki corrections
fix = {("Wafa-Mellitah Gas Pipeline", "Pipeline 1"): 524.6,
       ("Trans Nigeria Gas Pipeline", "Phase 1: Ajaokuta–Kaduna–Kano Pipeline (AKK Pipeline)"): 614.0,
       ("Egbin Node-Alagbado Gas Pipeline", ""): 40.0,
       ("Medgaz Gas Pipeline", "Onshore Segment (Hassi R'Mel-Mocta Douz)"): 547.0 - 120.0}
with contextlib.redirect_stdout(io.StringIO()):
    g = runpy.run_path("pipes.py", run_name="x") if False else None
sys.argv = [sys.argv[0], sys.argv[2], sys.argv[3]]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    g = runpy.run_path("pipes.py")
kept = g["kept"]
def L(s, corr):
    if corr and (s["name"], s["seg"]) in fix:
        return fix[(s["name"], s["seg"])]
    return s["L"] or s["geo"]
for corr, lab in ((False, "as published"), (True, "corrected (Wafa, AKK, Egbin, Medgaz onshore)")):
    tot = sum(L(s, corr) for s in kept)
    by = {st: sum(L(s, corr) for s in kept if s["dash"] == st) for st in ("operating", "under_construction", "announced", "stalled")}
    print(f"PIPES {lab}: total {tot:,.1f} km | " + " | ".join(f"{k} {v:,.1f}" for k, v in by.items()))
wafa_only = sum((524.6 if (s["name"], s["seg"]) == ("Wafa-Mellitah Gas Pipeline", "Pipeline 1") else (s["L"] or s["geo"])) for s in kept)
print(f"PIPES Wafa-only correction: {wafa_only:,.1f} km")
hit = [(s["name"], s["seg"]) for s in kept if (s["name"], s["seg"]) in fix]
print("fixed keys matched:", len(hit), hit)
