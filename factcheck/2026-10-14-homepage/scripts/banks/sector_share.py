"""How much of each bank's 'infrastructure' commitment is actually infrastructure by the activity's own DAC percentages,
and how much is budget support (development policy operations) counted at full value.
Usage: sector_share.py AFDB_PARSED.json WB_PARSED.json RECORDS.json"""
import sys, json, re
INFRA = ("210", "23", "140", "321", "322", "323", "331", "410", "220")
CORE = ("210", "23", "140", "220")
recs = {(r["ln"], r["id"]): r for r in json.load(open(sys.argv[3]))}
DPO = re.compile(r"development policy|\bDPO\b|\bDPF\b|\bDPL\b|\bDPC\b|budget support|policy financing|policy operation|policy-based|policy based|programme d'appui budg|appui budg|program[me]* for results|\bPforR\b", re.I)
for fn, ln in ((sys.argv[1], "AfDB"), (sys.argv[2], "WB")):
    acts = {a["id"]: a for a in json.load(open(fn))}
    tot = w_inf = w_core = dpo = low = 0.0; nlow = ndpo = 0; nopct = 0; lows = []
    for (l, i), r in recs.items():
        if l != ln: continue
        a = acts[i]
        sp = [(c, float(p)) for v, c, p in a["sectp"] if v in (None, "1", "2") and c and p not in (None, "")]
        if not sp:
            share = core = 1.0; nopct += 1
        else:
            T = sum(p for c, p in sp) or 1
            share = sum(p for c, p in sp if c.startswith(INFRA)) / T
            core = sum(p for c, p in sp if c.startswith(CORE)) / T
        c = r["com"]; tot += c; w_inf += c * share; w_core += c * core
        if share < 0.5: low += c; nlow += 1; lows.append((c, share, i, a["title"]))
        if DPO.search(a["title"] or ""): dpo += c; ndpo += 1
    print(f"{ln}: total USD {tot/1e9:.1f} bn; weighted by infra DAC share {w_inf/1e9:.1f} bn; weighted by core infra (210/220/23x/140) {w_core/1e9:.1f} bn;"
          f" activities with infra share <50%: {nlow} worth {low/1e9:.1f} bn; DPO/budget-support titles: {ndpo} worth {dpo/1e9:.1f} bn; no percentages: {nopct}")
    for c, s, i, t in sorted(lows, reverse=True)[:12]: print(f"    {c/1e6:8.1f}  infra {s:.0%}  {i}  {t[:70]}")
