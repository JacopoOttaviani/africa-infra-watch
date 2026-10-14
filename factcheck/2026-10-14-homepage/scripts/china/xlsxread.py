import zipfile, xml.etree.ElementTree as ET
def read_xlsx_sheet(path, sheet):
    """Rows of one worksheet as lists (str, int, float or None), from the
    standard library alone: an .xlsx is a zip of XML. Dates arrive as Excel
    serial numbers, which is fine here because only years are used."""
    ns = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rns = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    z = zipfile.ZipFile(path)
    rels = {r.get("Id"): r.get("Target")
            for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    target = None
    for sh in ET.fromstring(z.read("xl/workbook.xml")).iter(ns + "sheet"):
        if sh.get("name") == sheet:
            target = rels[sh.get(rns + "id")].lstrip("/")
    if not target:
        raise KeyError(f"no sheet {sheet!r} in {path}")
    if not target.startswith("xl/"):
        target = "xl/" + target
    strings = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(ns + "si"):
            strings.append("".join(t.text or "" for t in si.iter(ns + "t")))

    def col(ref):
        n = 0
        for ch in ref:
            if not ch.isalpha():
                break
            n = n * 26 + ord(ch.upper()) - 64
        return n - 1

    with z.open(target) as f:
        row = []
        for ev, el in ET.iterparse(f, events=("start", "end")):
            if ev == "start" and el.tag == ns + "row":
                row = []
            elif ev == "end" and el.tag == ns + "c":
                i = col(el.get("r", ""))
                while len(row) < i:
                    row.append(None)
                t, v = el.get("t"), el.find(ns + "v")
                if t == "s":
                    val = strings[int(v.text)] if v is not None else None
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in el.iter(ns + "t"))
                elif v is None or v.text is None:
                    val = None
                elif t in ("str", "e"):
                    val = v.text
                else:
                    try:
                        val = float(v.text)
                        if val.is_integer() and "." not in v.text and "E" not in v.text.upper():
                            val = int(val)
                    except ValueError:
                        val = v.text
                row.append(val)
                el.clear()
            elif ev == "end" and el.tag == ns + "row":
                yield row
                el.clear()


_COUNTRY_POLYS = None


