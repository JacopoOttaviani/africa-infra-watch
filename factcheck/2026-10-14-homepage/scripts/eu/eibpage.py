import sys, re, html
for fn in sys.argv[1:]:
    s = open(fn, encoding="utf-8", errors="replace").read()
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    lines = [l.strip() for l in t.split("\n") if l.strip()]
    out = []
    keys = ("Signed", "Approved", "Status", "Release date", "Amount", "Total cost", "EUR", "USD", "Cancelled", "Location", "Sector", "Proposed EIB finance", "Project number", "Promoter", "Country")
    for i, l in enumerate(lines):
        if any(k.lower() in l.lower() for k in keys) and len(l) < 200:
            out.append(" | ".join(lines[i:i+3]))
    print("=====", fn)
    seen = set()
    for o in out:
        if o not in seen:
            seen.add(o); print("  ", o[:250])
