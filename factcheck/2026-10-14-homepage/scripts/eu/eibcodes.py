import sys, json, re, collections
import xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
kept = {a["id"]: a for a in json.load(open(sys.argv[2])) if a["pub"] == "EIB"}
allcodes = collections.Counter()
rows = []
for act in root.iter("iati-activity"):
    i = act.find("iati-identifier").text
    if i not in kept: continue
    a = kept[i]
    sec = [(s.get("code"), (s.find("narrative").text if s.find("narrative") is not None else "")) for s in act.iter("sector") if s.get("vocabulary") == "99"]
    title = act.find("title/narrative").text
    flags = []
    if any(c.startswith("ZZ") for c, _ in sec): flags.append("ZZ-globalloan")
    if any(c[:2] in ("64", "65", "66") for c, _ in sec): flags.append("finance-code")
    if re.search(r"\bFUND\b|FUND I|FUND II|FUND III|\bLCFP\b|PARTNERS|EVOLUTION|PLATFORM", title.upper()): flags.append("fund-title")
    if any(c[:2] in ("01", "02", "03", "85", "86", "87", "88") for c, _ in sec): flags.append("agri/health/edu-code")
    if a["instr"] == "equity" and not flags: flags.append("equity-other")
    if flags: rows.append((a["commit"], i, title[:55], a["instr"], a["iso"], a["regions"], flags, [c for c, _ in sec][:4]))
    for c, n in sec: allcodes[(c[:2], n if c.startswith('ZZ') else '')] += 1
rows.sort(reverse=True)
tot = collections.defaultdict(float); cnt = collections.Counter()
for r in rows:
    print(f"{r[0]/1e6:7.1f}M {r[1][13:]:20} {r[3]:7} {str(r[4]):5} {r[6]} {r[2]} {r[7]}")
    for f in r[6]: tot[f] += r[0]; cnt[f] += 1
print({k: (cnt[k], round(v/1e6, 1)) for k, v in tot.items()})
fund_eq = [r for r in rows if r[3] == "equity" and "fund-title" in r[6]]
print("equity records with fund-like titles:", len(fund_eq), round(sum(r[0] for r in fund_eq)/1e6, 1), "M EUR")
