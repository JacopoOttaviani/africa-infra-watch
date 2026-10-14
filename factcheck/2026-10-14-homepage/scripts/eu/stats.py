import json, sys, collections
A = json.load(open(sys.argv[1]))
sub = {"XI-IATI-EC_INTPA_C_1027.xml","XI-IATI-EC_INTPA_C_1028.xml","XI-IATI-EC_INTPA_C_1029.xml","XI-IATI-EC_INTPA_C_1030.xml","XI-IATI-EC_INTPA_C_1031.xml"}
subacts = [a for a in A if a["file"] in sub]
A57 = [a for a in A if a["file"] not in sub]
print("activities from 1027-1031 files passing filter:", len(subacts), "commit EUR bn", sum(a['commit'] for a in subacts)/1e9)
# duplicates across files
ids = collections.Counter(a["id"] for a in A57)
print("dup ids across 57 files:", sum(1 for v in ids.values() if v > 1))
def run(acts, label):
    ec = [a for a in acts if a["pub"] != "EIB"]
    parents = {p for a in ec if a["hier"] == "2" for p in a["parents"]}
    kept = [a for a in acts if a["pub"] == "EIB" or a["hier"] == "2" or a["id"] not in parents]
    nc = sum(1 for a in kept if a["pub"] != "EIB" and a["hier"] == "2")
    nd = sum(1 for a in kept if a["pub"] != "EIB" and a["hier"] != "2")
    eib = [a for a in kept if a["pub"] == "EIB"]
    print(f"== {label}: records {len(kept)} EC {nc+nd} (contracts {nc}, decisions {nd}, folded {len(ec)-nc-nd}) EIB {len(eib)}")
    ce = sum(a['commit'] for a in kept if a['pub']!='EIB'); cb = sum(a['commit'] for a in eib)
    print(f"   commit EC {ce/1e9:.2f}bn EIB {cb/1e9:.2f}bn total {(ce+cb)/1e9:.2f}bn = ${(ce+cb)*1.1206/1e9:.2f}bn; disb {sum(a['disb'] for a in kept)*1.1206/1e9:.2f} $bn")
    st = collections.Counter(a['status'] for a in kept)
    print("   status", dict(sorted(st.items())), "announced", st['1'], "UC", st['2'], "oper", st['3']+st['4'], "stalled", st['5']+st['6'])
    print("   EIB instr", collections.Counter(a['instr'] for a in eib))
    yrs = [ (a['dates'].get('2') or a['dates'].get('1') or '')[:4] for a in kept]
    yrs = [y for y in yrs if y]
    print("   start years", min(yrs), max(yrs))
    countries = {a['iso'] for a in kept if a['iso']}
    print("   countries with iso", len(countries))
    impl = collections.Counter(i for a in kept if a['pub']!='EIB' for i in a['impl'])
    print("   implementers", impl.most_common(6))
    # sector buckets (EC by first infra DAC code)
    DAC = [("210","transport"),("220","ict"),("23","energy"),("140","water"),("321","industry"),("322","industry"),("323","industry"),("331","trade"),("410","environment")]
    def b(codes):
        for c in codes:
            for p, s in DAC:
                if c.startswith(p): return s
    sec = collections.Counter((a['sector'] if a['pub']=='EIB' else b(a['slabel'])) for a in kept)
    print("   sectors (first-code rule, approx)", sec.most_common())
    return kept
run(A57, "57 datasets, today")
run(A, "57 + 1027-1031 subregional files")
