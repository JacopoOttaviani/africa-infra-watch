import sys, re, html
s = open(sys.argv[1], encoding="utf-8", errors="replace").read()
t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", s, flags=re.S)
t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
L = [l.strip() for l in t.split("\n") if l.strip()]
a = next(i for i, l in enumerate(L) if l.startswith("Amount") or l.startswith("Release date"))
b = next((i for i, l in enumerate(L) if "Queries regarding" in l), a + 120)
print("\n".join(L[max(0, a - 15):b])[:int(sys.argv[2]) if len(sys.argv) > 2 else 4000])
