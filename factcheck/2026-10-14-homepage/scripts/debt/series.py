"""Print IMF credit sum for the 50 African debtors and regional aggregates.
    python3 -I series.py <imf_all.json> <regions.json> <regions_cp.json>"""
import json
import sys

AF = set("""DZA AGO BEN BWA BFA BDI CMR CPV CAF TCD COM COD COG CIV DJI EGY GNQ ERI SWZ ETH GAB GMB GHA GIN GNB
KEN LSO LBR LBY MDG MWI MLI MRT MUS MAR MOZ NAM NER NGA RWA STP SEN SYC SLE SOM ZAF SSD SDN TZA TGO TUN UGA ZMB ZWE""".split())
NA = {"DZA", "EGY", "MAR", "TUN", "LBY"}


def rows(p):
    for r in json.load(open(p))["source"]["data"]:
        var = {x["concept"]: x for x in r["variable"]}
        yield var, r["value"]


imf, n, series_name = 0.0, 0, None
ssa_imf = 0.0
for var, v in rows(sys.argv[1]):
    series_name = var["Series"]["value"]
    if var["Country"]["id"] in AF and v is not None:
        imf += v
        n += 1
        if var["Country"]["id"] not in NA:
            ssa_imf += v
print(f"{series_name}: {n} African debtors, 2024 sum {imf/1e9:.3f} bn; of which SSA-50 subset {ssa_imf/1e9:.3f}")
for p in sys.argv[2:]:
    print("--", p.rsplit("/", 1)[-1])
    for var, v in rows(p):
        cp = var.get("Counterpart-Area", {}).get("id")
        print(f"  {var['Country']['id']:<4} {var['Series']['id']:<16} cp={cp:<4} {(v or 0)/1e9:10.3f} bn  ({var['Series']['value']})")
