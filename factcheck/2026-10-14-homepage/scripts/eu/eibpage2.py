import sys, re, html
for fn in sys.argv[1:]:
    s = open(fn, encoding="utf-8", errors="replace").read()
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
    L = [l.strip() for l in t.split("\n") if l.strip()]
    def after(k, n=1):
        for i, l in enumerate(L):
            if l == k: return " / ".join(L[i+1:i+1+n])
    title = next((L[i+1] for i, l in enumerate(L) if l.startswith("Promoter")), None)
    amt = after("Amount", 1)
    st = after("Status", 6)
    prop = after("Proposed EIB finance (Approximate amount)", 3)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", s, re.S)
    print(fn.split("/")[-1], "|", re.sub(r"<[^>]+>|\s+", " ", h1.group(1)).strip() if h1 else None, "| Amount:", amt, "| Status:", st, "| Proposed/Total:", prop)
