"""Tally funding sources and implementing bodies from the portal's English pages:
(a) with the site's own split rules (map.template.html:2371-2372, impl truncated
to 160 chars as build_dashboard.py does), and (b) per body, one count per project,
with hand normalisation of the portal's wording.
usage: python3 -I tally.py PARSED_JSON"""
import collections, json, re, sys

R = json.load(open(sys.argv[1]))


def nz(v):
    return None if v in (None, "", "—", "-") else v


# (a) site rules
sf, si = collections.Counter(), collections.Counter()
for r in R:
    f = nz(r["en"]["fields"].get("Resources")) or ""
    for o in [s.strip() for s in re.split(r" / | and ", f) if s.strip()]:
        sf[o] += 1
    im = (nz(r["en"]["fields"].get("Implementing body")) or "")[:160]
    for o in [s.strip() for s in re.split(r"[;\n]", im) if s.strip()]:
        si[o] += 1
print("SITE RULE funding top 7:", sf.most_common(7))
print("SITE RULE implementers top 7:", si.most_common(7))

# (b) body-level: one count per project that names the body
FUND = {
    "MAECI (Ministry of Foreign Affairs and International Cooperation)": r"Ministry of Foreign Affairs and International Cooperation",
    "Italian Climate Fund": r"Italian Climate Fund",
    "Other resources (as printed)": r"^Other resources$",
    "Ministry of Culture": r"Ministry of Culture",
    "Ministry of the Environment and Energy Security (MASE)": r"\(MASE\)",
    "Rome Process Financing Facility": r"Rome Process",
    "National Recovery and Resilience Plan (NRRP)": r"NRRP",
    "Plafond Africa": r"Plafond Africa",
}
fc = collections.Counter()
for r in R:
    f = nz(r["en"]["fields"].get("Resources")) or ""
    for k, pat in FUND.items():
        if re.search(pat, f):
            fc[k] += 1
print("\nBODY-LEVEL funding:", fc.most_common())
print("  projects naming MAECI alone (exact):",
      sum(1 for r in R if r["en"]["fields"].get("Resources") == "Ministry of Foreign Affairs and International Cooperation (MAECI)"))

IMPL = {
    "United Nations Development Programme (UNDP)": r"United Nations Development Programme",
    "Ministry of the Environment and Energy Security (MASE)": r"\(MASE\)",
    "Italian ITS Academies": r"Italian ITS Academies",
    "Italian Agency for Development Cooperation (AICS)": r"\(AICS\)",
    "CIHEAM (Bari)": r"CIHEAM",
    "Ministry of Culture": r"Ministry of Culture",
    "Italian and foreign universities": r"Italian and foreign universities",
    "National School of Cultural Heritage and Activities": r"National School of Cultural Heritage",
    "Terna S.p.A.": r"Terna S\.p\.A\.",
    "ICCROM": r"ICCROM",
    "World Bank": r"World Bank",
    "University of Padua": r"University of Padua",
    "University for Foreigners of Siena": r"University for Foreigners of Siena",
    "BF group (BF International / BF SpA)": r"\bBF\b",
}
ic = collections.Counter()
for r in R:
    im = nz(r["en"]["fields"].get("Implementing body")) or ""
    for k, pat in IMPL.items():
        if re.search(pat, im):
            ic[k] += 1
print("\nBODY-LEVEL implementers:", ic.most_common())
print("  projects with no implementing body ('—'):",
      sum(1 for r in R if not nz(r["en"]["fields"].get("Implementing body"))))
