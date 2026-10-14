"""Multi-country Commission decisions: sub-activities (-01..-NN) that each repeat the whole envelope."""
import json, sys, re, collections
A = json.load(open(sys.argv[1]))
ec = [a for a in A if a["pub"] != "EIB"]
parents = {p for a in ec if a["hier"] == "2" for p in a["parents"]}
kept = {a["id"] for a in A if a["pub"] == "EIB" or a["hier"] == "2" or a["id"] not in parents}
def root(i):
    m = re.match(r"(.*ACT-D-\d+)-\d\d$", i)
    return m.group(1) if m else i
fam = collections.defaultdict(list)
for a in ec:
    if a["hier"] != "2": fam[root(a["id"])].append(a)
contracts_by_root = collections.defaultdict(list)
for a in ec:
    if a["hier"] == "2":
        rs = {root(p) for p in a["parents"]}
        for r in rs: contracts_by_root[r].append(a)
over_rule = over_strict = 0.0; rows = []
nkept_dupe = 0
for r, mem in fam.items():
    sigs = collections.Counter(tuple(sorted(map(tuple, m["tx2"]))) for m in mem if m["commit"])
    km = [m for m in mem if m["id"] in kept and m["commit"]]
    if len(mem) < 2 or not km: continue
    # same-envelope copies among kept members
    for sig, n in sigs.items():
        ks = [m for m in km if tuple(sorted(map(tuple, m["tx2"]))) == sig]
        if not ks: continue
        E = ks[0]["commit"]
        C = sum(c["commit"] for c in contracts_by_root[r])
        # site's own rule: the decision has contracts published -> none of its copies should be a record
        o_rule = len(ks) * E if C > 0 else (len(ks) - 1) * E
        # generous: allow one copy of the uncontracted remainder
        o_strict = len(ks) * E - max(E - C, 0)
        if o_rule > 0 or o_strict > 0:
            over_rule += o_rule; over_strict += o_strict; nkept_dupe += len(ks)
            rows.append((o_rule, r, len(mem), len(ks), E, C, [k["iso"] for k in ks], ks[0]["title"][:50]))
rows.sort(reverse=True)
for x in rows[:30]:
    print(f"over {x[0]/1e6:8.1f}M  {x[1]:38} members={x[2]} kept_copies={x[3]} envelope={x[4]/1e6:.1f}M contracts_under_family={x[5]/1e6:.1f}M {x[6]} | {x[7]}")
print("families affected", len(rows), "kept records involved", nkept_dupe)
print(f"overcount under site's own rule: EUR {over_rule/1e9:.3f}bn ; allowing one copy of uncontracted remainder: EUR {over_strict/1e9:.3f}bn")
