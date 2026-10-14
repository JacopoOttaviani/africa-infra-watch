"""Recompute the Piano Mattei headline figures from the parsed portal pages.
usage: python3 -I stats.py PARSED_JSON"""
import collections, json, re, sys

R = json.load(open(sys.argv[1]))
EUR_USD = 1.1206
print("records:", len(R))

# stage, IT vs EN
mism = [(r["it"]["slug"], r["it"]["stage"], r["en"]["stage"]) for r in R if r["en"] and
        {"In corso": "Ongoing", "Approvato": "Approved", "Concluso": "Completed", "Formulato": "Formulated",
         "Identificato": "Identified"}.get(r["it"]["stage"]) != r["en"]["stage"]]
print("IT/EN stage mismatches:", mism)

# countries
cnt_names = collections.Counter()
per = []
for r in R:
    c = r["en"]["fields"].get("Countries", "")
    names = [x.strip() for x in re.split(r",\s*", c) if x.strip()]
    per.append((r["it"]["slug"], names))
    cnt_names.update(names)
print("\ndistinct EN country names:", len(cnt_names))
for k, v in sorted(cnt_names.items(), key=lambda kv: -kv[1]):
    print(f"   {v:3d}  {k}")
n1 = sum(1 for s, n in per if len(n) == 1)
n0 = [(s, r["en"]["fields"].get("Countries")) for (s, n), r in zip(per, R) if len(n) == 0]
nm = sum(1 for s, n in per if len(n) > 1)
print("one country:", n1, " several:", nm, " none:", len(n0), n0)

# directives
dirs = collections.Counter()
for r in R:
    dirs.update(r["en"]["directives"])
print("\nEN directives:", dirs.most_common())
dirs_it = collections.Counter()
for r in R:
    dirs_it.update(r["it"]["directives"])
print("IT directives:", dirs_it.most_common())
print("all six:", sum(1 for r in R if len(r["en"]["directives"]) >= 6))

# amounts: print IT and EN texts side by side
print("\nAMOUNTS")
for r in R:
    print(f"  {r['it']['slug'][:70]:70s} | IT: {r['it']['fields'].get('Importo')!r} | EN: {r['en']['fields'].get('Amount')!r}")
