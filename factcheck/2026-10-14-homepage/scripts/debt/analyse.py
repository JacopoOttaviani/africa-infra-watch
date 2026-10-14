"""Independent re-aggregation of World Bank IDS DT.DOD.DPPG.CD by counterpart
for the 54 African debtors. Usage:
    python3 -I analyse.py <by_debtor_dir> <counterpart_list.json> [year]
Reads only downloaded JSON; never imports repo code."""
import json
import os
import sys

DIR, CPL = sys.argv[1], sys.argv[2]
YEAR = int(sys.argv[3]) if len(sys.argv) > 3 else 2024

DEBTORS = """DZA AGO BEN BWA BFA BDI CMR CPV CAF TCD COM COD COG CIV DJI EGY GNQ ERI SWZ ETH GAB GMB GHA GIN GNB
KEN LSO LBR LBY MDG MWI MLI MRT MUS MAR MOZ NAM NER NGA RWA STP SEN SYC SLE SOM ZAF SSD SDN TZA TGO TUN UGA ZMB ZWE""".split()

names = {v["id"]: " ".join(v["value"].split())
         for v in json.load(open(CPL))["source"][0]["concept"][0]["variable"]}

# The site's stated group definitions, re-typed from the box's labels and
# fetch_debt.py's documented code sets, applied to the fresh API data.
INSTITUTIONS = {"019", "237", "877", "878", "887", "888", "890", "892", "893", "895", "896", "897",
                "898", "899"} | {f"{n:03d}" for n in range(802, 820)}
MULTIPLE = {"994", "FCW"}
EUROPE = {"001", "002", "003", "004", "005", "006", "007", "008", "009", "010", "011", "012", "018",
          "020", "021", "022", "025", "026", "030", "035", "040", "044", "045", "050", "060", "061",
          "062", "063", "064", "065", "066", "068", "069", "071", "072", "073", "074", "075", "076",
          "077", "082", "083", "084"}
GULF = {"530", "552", "558", "561", "566", "576"}


def grp(code):
    if code == "BND":
        return "Bondholders"
    if code in MULTIPLE:
        return "Other lenders"
    if code in INSTITUTIONS or (code.isdigit() and int(code) >= 901):
        return "Multilateral lenders"
    if code == "730":
        return "China"
    if code in EUROPE:
        return "Europe"
    if code == "302":
        return "United States"
    if code in GULF:
        return "Gulf states"
    return "Other lenders"


world, by_code, missing, last_year, updated = {}, {}, [], {}, set()
per_debtor_code = {}
for iso in DEBTORS:
    p = os.path.join(DIR, iso + ".json")
    raw = open(p, encoding="utf-8").read()
    if not raw.lstrip().startswith("{"):
        missing.append(iso)
        continue
    d = json.loads(raw)
    updated.add(d.get("lastupdated"))
    yrs = set()
    for row in d["source"]["data"]:
        v = row["value"]
        if v is None:
            continue
        var = {x["concept"]: x for x in row["variable"]}
        y = int(var["Time"]["value"])
        yrs.add(y)
        code = var["Counterpart-Area"]["id"]
        if y != YEAR:
            continue
        if code == "WLD":
            world[iso] = float(v)
        else:
            by_code[code] = by_code.get(code, 0) + float(v)
            per_debtor_code.setdefault(code, {})[iso] = float(v)
    last_year[iso] = max(yrs) if yrs else None

tot_world = sum(world.values())
tot_parts = sum(by_code.values())
print("API lastupdated:", updated)
print("debtors with data:", len(world), "missing:", missing)
print("latest year per debtor (set):", sorted(set(last_year.values()) - {None}))
print(f"sum of WLD totals {YEAR}: {tot_world/1e9:.3f} bn; sum of counterparts {tot_parts/1e9:.3f} bn")

g = {}
for code, v in by_code.items():
    g[grp(code)] = g.get(grp(code), 0) + v
print("\nGroups (site definitions, fresh API data):")
for k, v in sorted(g.items(), key=lambda t: -t[1]):
    print(f"  {k:<22} {v/1e9:8.3f} bn  {v/tot_parts*100:6.2f}%")
print(f"  sum {sum(g.values())/1e9:.3f}")

print("\nTop 15 counterparts:")
for code, v in sorted(by_code.items(), key=lambda t: -t[1])[:15]:
    print(f"  {code:<4} {names.get(code, code):<55} {v/1e9:8.3f} bn  {v/tot_parts*100:5.2f}%  [{grp(code)}]")

print("\nMembers of each group (>= 0.05 bn):")
for G in ["Multilateral lenders", "Europe", "Gulf states", "Other lenders"]:
    print(" ", G)
    for code, v in sorted(by_code.items(), key=lambda t: -t[1]):
        if grp(code) == G and v >= 5e7:
            print(f"     {code:<4} {names.get(code, code):<55} {v/1e9:7.3f}")

for code in ("907", "911", "970", "971", "922", "897", "919", "975", "918", "917", "087", "078", "055",
             "701", "742", "646", "540", "543", "994", "FCW"):
    if code in by_code:
        top = sorted(per_debtor_code[code].items(), key=lambda t: -t[1])[:4]
        print(f"  check {code} {names.get(code)}: {by_code[code]/1e9:.3f} bn; top debtors {[(i, round(v/1e9, 2)) for i, v in top]}")
    else:
        print(f"  check {code} {names.get(code)}: absent in {YEAR}")

print("\nLargest debtors:")
for iso, v in sorted(world.items(), key=lambda t: -t[1])[:12]:
    print(f"  {iso} {v/1e9:7.2f}")
NA = ["DZA", "EGY", "MAR", "TUN", "LBY"]
na = sum(world.get(i, 0) for i in NA)
print(f"North Africa (DZA EGY MAR TUN) {na/1e9:.2f} bn = {na/tot_world*100:.1f}%; Egypt {world.get('EGY',0)/1e9:.2f}")
ssa = sum(v for i, v in world.items() if i not in NA)
print(f"Sub-Saharan subset {ssa/1e9:.2f} bn")
