"""Appels d'offres de TRAVAUX de batiment ouverts (BOAMP, donnees publiques) : construction / rehabilitation /
restructuration / amenagement (presque toujours un lot peinture, souvent des plans d'etage avec surfaces).
Sert a trouver les dossiers NEUFS de validation finale. Sortie : donnees/ao_batiment.json"""
import json, os, re, sys, time, urllib.parse, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
API = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records"
LIMITE = sys.argv[1] if len(sys.argv) > 1 else "2026-11-30"
where = ('type_marche="TRAVAUX" and datelimitereponse>="%s" and (search(objet,"construction") or '
         'search(objet,"réhabilitation") or search(objet,"restructuration") or search(objet,"aménagement") or search(objet,"rénovation") or search(objet,"extension") or search(objet,"peinture") or search(objet,"école") or search(objet,"collège") or search(objet,"logements"))' % LIMITE)
LIEN = re.compile(r'https?://[^"\s<>\\]+')
PLACE = re.compile(r"consultation/\d+\?orgAcronyme=|[?&]id=\d+&orgAcronyme=")
out, off = [], 0
while True:
    q = urllib.parse.urlencode({"where": where, "limit": 100, "offset": off, "order_by": "datelimitereponse"})
    d = json.load(urllib.request.urlopen(urllib.request.Request(API + "?" + q, headers={"User-Agent": "etude-metre"}), timeout=60))
    rs = d.get("results", [])
    for r in rs:
        liens = sorted(set(LIEN.findall(r.get("donnees") or "")))
        out.append({"idweb": r.get("idweb"), "objet": r.get("objet"), "acheteur": r.get("nomacheteur"),
                    "dept": r.get("code_departement"), "limite": r.get("datelimitereponse"), "nature": r.get("nature"),
                    "url_avis": r.get("url_avis"), "place": [l for l in liens if "marches-publics.gouv.fr" in l], "liens": liens[:15]})
    off += 100
    if len(rs) < 100 or off >= 3000: break
    time.sleep(1)
json.dump(out, open(os.path.join(ici, "donnees", "ao_batiment.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out), "avis batiment |", sum(1 for x in out if any(PLACE.search(l) for l in x["place"])), "avec un lien PLACE exploitable")
