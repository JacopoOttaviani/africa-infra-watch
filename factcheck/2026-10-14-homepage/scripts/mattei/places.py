"""For each gazetteer slug, show the sentences of the portal's IT+EN title/description
that mention candidate place words. usage: python3 -I places.py PARSED_JSON"""
import json, re, sys
R = {r["it"]["slug"]: r for r in json.load(open(sys.argv[1]))}
CHECK = {  # slug prefix -> words to look for (label as the site prints it, split into tokens)
 "progetto-recupero-terreni": ["Timimoun"],
 "progetto-supporto-al-progetto-di-sviluppo-rurale": ["Zanzan", "Bondoukou", "Bouna", "nord-est", "north-east", "northeast"],
 "progetto-supporto-alla-realizzazione-di-un-impianto-fotovoltaico": ["Benban", "Kom Ombo", "Aswan", "Assuan", "Abydos"],
 "progetto-tandem-italia-tunisia": ["El Attar", "Enfidha", "Sfax", "Tunis"],
 "progetto-finanziamento-sovrano-a-supporto": ["Brazzaville", "Pointe-Noire", "Pointe Noire"],
 "progetto-creazione-del-centro-algero": ["Sidi Bel Abb", "Sidi-Bel-Abb"],
 "progetto-rafforzamento-del-settore-sanitario": ["Abobo", "Abengourou", "Abidjan"],
 "progetto-programma-di-sostegno-alla-repubblica": ["Jimma", "Boye"],
 "progetto-sostegno-settore-sanitario-nella": ["Shire", "Adwa", "Gondar", "Tigray"],
 "progetto-supporto-al-rafforzamento-dei-servizi": ["Addis"],
 "progetto-laboratorio-dei-talenti": ["Meru", "Chaaria"],
 "progetto-istituzione-di-un-polo-agroalimentare": ["Manica"],
 "progetto-progetti-di-ampliamento": ["Maputo"],
 "progetto-programma-integrato-di-sviluppo": ["Matam", "Louga", "Kolda", "Sédhiou", "Sedhiou"],
 "progetto-formazione-professionale-di-qualita": ["Zanzibar"],
 "progetto-polo-patrimonio-tunisia": ["Kerkouane", "Kerkuane", "Neapolis", "Nabeul", "Pupput", "Hammamet"],
 "progetto-bleue-tunisie": ["Sidi Daoud", "Kraten", "Mahres", "Skhira"],
 "progetto-gemellaggio-tra-il-parco-archeologico-di-pompei": ["Timgad"],
 "progetto-gemellaggio-tra-il-parco-archeologico-del-colosseo": ["El Jem"],
 "progetto-ethiopia-borana": ["Borana"],
 "progetto-eastern-region": ["Moxico", "Luena", "Lunda", "Cuando", "Cubango", "eastern"],
 "progetto-lobito-economic": ["Lobito"],
 "progetto-terna-innovation-zone": ["Tunis"],
 "progetto-elmed": ["Mlaabi", "Cap Bon", "Menzel"],
 "progetto-centro-di-eccellenza-panafricano": ["Ben Guerir", "Benguerir", "UM6P", "Nairobi", "Pretoria"],
 "progetto-finanziamento-alla-banque-ouest": ["Lomé", "Lome"],
}
for pre, words in CHECK.items():
    hits = [s for s in R if s.startswith(pre)]
    if len(hits) != 1:
        print("!! prefix", pre, hits); continue
    r = R[hits[0]]
    txt = " ".join(filter(None, [r["it"]["title"], r["it"]["desc"], r["en"]["title"], r["en"]["desc"]]))
    found = {w: len(re.findall(re.escape(w), txt, re.I)) for w in words}
    print(f"{pre[:55]:55s} {found}")
    for w in words[:1]:
        for m in re.finditer(re.escape(w), r["en"]["desc"] or "", re.I):
            print("     EN…", (r["en"]["desc"] or "")[max(0, m.start()-120):m.end()+80].replace("\n", " "))
            break
