"""Recompute stated amounts from the portal's English 'Amount' field, reading every
figure in the text (not just the first), plus the IT field as a cross-check.
usage: python3 -I money.py PARSED_JSON"""
import json, re, sys

R = json.load(open(sys.argv[1]))
EUR_USD = 1.1206
MULT = {"billion": 1e9, "million": 1e6, "thousand": 1e3, None: 1}


def figures(t):
    t = (t or "").replace("\xa0", " ")
    out = []
    for m in re.finditer(r"(EUR|USD|€|\$)?\s*(\d[\d,]*(?:\.\d+)?)\s*(billion|million|thousand)?", t):
        v = float(m.group(2).replace(",", "")) * MULT[m.group(3)]
        out.append((v, "USD" if m.group(1) in ("USD", "$") else "EUR", m.group(0).strip()))
    return out


def it_figures(t):
    t = (t or "").replace("\xa0", " ")
    out = []
    for m in re.finditer(r"(€|\$)?\s*(\d[\d.]*(?:,\d+)?)\s*(miliardi|milioni|milione|mila)?", t):
        v = float(m.group(2).replace(".", "").replace(",", ".")) * {"miliardi": 1e9, "milioni": 1e6, "milione": 1e6, "mila": 1e3, None: 1}[m.group(3)]
        out.append((v, "USD" if m.group(1) == "$" else "EUR"))
    return out


first_total = 0.0
alt_total = 0.0
n_first = 0
rows = []
for r in R:
    en = r["en"]["fields"].get("Amount", "")
    it = r["it"]["fields"].get("Importo", "")
    f = figures(en)
    fi = it_figures(it)
    slug = r["it"]["slug"]
    shared = "(Algeria, Egypt, Tunisia, Ethiopia)" in en
    # site rule: first figure; shared memoranda -> only the promotion figure
    if f:
        v, cur, _ = f[0]
        eur = v / EUR_USD if cur == "USD" else v
        if shared:
            m = re.search(r"(?:EUR|and)\s*(\d[\d,]*)\s*for the promotion", en)
            eur = float(m.group(1).replace(",", "")) if m else None
        if eur:
            n_first += 1
            first_total += eur
    # alternative: whole stated figure. TANIT: sum both parts; Laboratorio: the total only
    if f and not shared:
        if "TANIT" in en:
            alt = sum(x[0] for x in f)
        else:
            alt = f[0][0] / (EUR_USD if f[0][1] == "USD" else 1)
        alt_total += alt
        rows.append((alt, slug, en, it))
    elif shared:
        m = re.search(r"(\d[\d,]*)\s*for the promotion", en)
        alt_total += float(m.group(1).replace(",", "")) if m else 0
    # cross-check IT vs EN first figure
    if f and fi and abs(f[0][0] - fi[0][0]) > 1:
        print("IT/EN first-figure mismatch:", slug, f[0], fi[0])
alt_total += 5e6  # the shared ITS envelope, once
print(f"site rule: {n_first} with a figure, EUR {first_total/1e9:.4f} bn = USD {first_total*EUR_USD/1e9:.4f} bn")
print(f"all stated figures (TANIT both parts, shared EUR 5m once): EUR {alt_total/1e9:.4f} bn = USD {alt_total*EUR_USD/1e9:.4f} bn")
print("\nTop 8 stated amounts (EUR):")
for alt, slug, en, it in sorted(rows, reverse=True)[:8]:
    print(f"  {alt/1e6:9.2f} m  USD {alt*EUR_USD/1e6:9.2f} m  {slug[:80]}  | {en}")
