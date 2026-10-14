"""Parse the downloaded Piano Mattei portal pages (IT + EN) into one JSON list.
usage: python3 -I parse.py RAW_DIR OUT_JSON
Independent of the repo: reads only the downloaded HTML."""
import html, json, os, re, sys

raw, out = sys.argv[1], sys.argv[2]


def text(s):
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = re.sub(r"</p>|</li>", "\n", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    return re.sub(r"\n{2,}", "\n", s).strip()


def page(lang, slug):
    s = open(os.path.join(raw, lang, slug + ".html"), encoding="utf-8").read()
    d = {"slug": slug, "lang": lang}
    other = "en" if lang == "it" else "it"
    m = re.search(rf'hrefLang="{other}"[^>]*href="/{other}/piano-mattei/progetti/progetto/([^"/]+)/"', s)
    d["other"] = m.group(1) if m else None
    m = re.search(r'<h1 id="project-heading"[^>]*>(.*?)</h1>', s, re.S)
    d["title"] = text(m.group(1)) if m else None
    # every dt/dd pair, raw and as text (keep raw so we can see <br>/<li> splits)
    fields, raw_fields = {}, {}
    for k, v in re.findall(r'<dt class="text-muted[^"]*">(.*?)</dt><dd[^>]*>(.*?)</dd>', s, re.S):
        k = text(k)
        steps = re.findall(r'background:(#[0-9A-Fa-f]{6})"></span><span class="text-base text-center">(.*?)</span>', v)
        if steps:
            act = [text(n) for c, n in steps if c.upper() != "#C5C7C9"]
            d["stage_all_active"] = act
            d["stage"] = act[0] if act else None
            d["steps"] = [(c, text(n)) for c, n in steps]
        else:
            fields[k] = text(v)
            raw_fields[k] = v
    d["fields"] = fields
    d["raw_fields"] = raw_fields
    # directives (pillars): list region
    m = re.search(r'role="list" aria-label="([^"]*)">(.*?)</div></div></div><div class="col-12 col-lg-4', s, re.S)
    d["dir_label"] = m.group(1) if m else None
    d["directives"] = [text(x) for x in re.findall(
        r'<span class="fw-semibold text-base font-titillium text-truncate[^"]*"[^>]*>(.*?)</span>', m.group(2) if m else "", re.S)]
    m = re.search(r'<div class="[^"]*markdown-text"[^>]*>(.*?)</div><div class="mt-4 w-100" role="list"', s, re.S)
    d["desc"] = text(m.group(1)) if m else None
    return d


slugs_it = [l.strip() for l in open(os.path.join(raw, "slugs_it.txt")) if l.strip()]
slugs_en = [l.strip() for l in open(os.path.join(raw, "slugs_en.txt")) if l.strip()]
recs = []
for sl in slugs_it:
    it = page("it", sl)
    en = page("en", it["other"]) if it["other"] and it["other"] in slugs_en else None
    recs.append({"it": it, "en": en})
json.dump(recs, open(out, "w"), ensure_ascii=False, indent=1)
print(len(recs), "records;", sum(1 for r in recs if r["en"]), "with EN pair")
print("EN slugs not paired:", sorted(set(slugs_en) - {r["it"]["other"] for r in recs}))
