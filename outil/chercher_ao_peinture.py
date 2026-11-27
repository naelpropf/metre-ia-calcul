"""Appels d'offres de TRAVAUX ouverts (BOAMP, donnees publiques) qui ont un lot peinture.
Sortie : donnees/ao_peinture.json (idweb, objet, acheteur, dept, date limite, lien vers le dossier si trouve)."""
import json, os, re, sys, time, urllib.parse, urllib.request
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(ici, "donnees"), exist_ok=True)
API = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records"
LIMITE = sys.argv[1] if len(sys.argv) > 1 else "2026-12-01"
where = (f'type_marche="TRAVAUX" and datelimitereponse>="{LIMITE}" and '
         f'(search(objet,"peinture") or search(donnees,"peinture"))')
out, offset = [], 0
while True:
    q = urllib.parse.urlencode({"where": where, "limit": 100, "offset": offset, "order_by": "datelimitereponse"})
    d = json.load(urllib.request.urlopen(urllib.request.Request(API + "?" + q, headers={"User-Agent": "etude-metre"}), timeout=60))
    rs = d.get("results", [])
    for r in rs:
        brut = r.get("donnees") or ""
        liens = sorted(set(re.findall(r'https?://[^"\s<>\\]+', brut)))
        place = [l for l in liens if "marches-publics.gouv.fr" in l]
        out.append({"idweb": r.get("idweb"), "objet": r.get("objet"), "acheteur": r.get("nomacheteur"),
                    "dept": r.get("code_departement"), "limite": r.get("datelimitereponse"), "nature": r.get("nature"),
                    "url_avis": r.get("url_avis"), "place": place, "liens": liens[:15]})
    offset += 100
    if len(rs) < 100 or offset >= 1000: break
    time.sleep(1)
json.dump(out, open(os.path.join(ici, "donnees", "ao_peinture.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("AO travaux ouverts avec 'peinture' :", len(out), "| dont lien PLACE :", sum(bool(o["place"]) for o in out))
dom = {}
for o in out:
    for l in o["liens"]:
        h = urllib.parse.urlparse(l).netloc
        dom[h] = dom.get(h, 0) + 1
print("plateformes les plus citees :", sorted(dom.items(), key=lambda x: -x[1])[:12])
for o in out[:8]: print("-", o["limite"][:10], o["dept"], (o["objet"] or "")[:80], "| PLACE" if o["place"] else "")
