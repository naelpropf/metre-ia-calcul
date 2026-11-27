"""MAQUETTE de l'ecran de validation (option C, D-07 pas encore tranchee).
Une page HTML autonome par plan : le plan, les pieces proposees par le moteur (coloriees), un clic = la fiche de la piece
avec Valider / Rejeter ; hauteur sous plafond modifiable ; totaux du lot peinture ; export CSV des pieces validees.
Usage : python ecran.py plan.pdf [dossier_sortie]"""
import base64, io, json, os, sys
import pypdfium2 as pdfium
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
from metre import mesurer, normaliser

def construire(chemin, sortie):
    res = mesurer(chemin)
    plat = normaliser(chemin)
    doc = pdfium.PdfDocument(plat); p = doc[0]; W, H = p.get_size()
    k = 2400 / max(W, H)
    img = p.render(scale=k).to_pil().convert("RGB")
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=80)
    fond = base64.b64encode(buf.getvalue()).decode()
    pieces = []
    for i, e in enumerate(res["pieces"]):
        if not e.get("contour_pt"): continue
        pieces.append({"id": i, "nom": e.get("nom") or "(sans nom)", "ecrite": e["surface_ecrite"],
                       "calc": e.get("surface_calc"), "ecart": e.get("ecart_pct"), "perim": e.get("perimetre"),
                       "statut": e["statut"], "pts": [[round(x * k, 1), round(y * k, 1)] for x, y in e["contour_pt"]]})
    donnees = {"plan": os.path.basename(chemin), "echelle": res["echelle_source"], "hauteur": res["hauteur"],
               "largeur": img.size[0], "hauteur_img": img.size[1], "pieces": pieces}
    html = PAGE.replace("__DONNEES__", json.dumps(donnees, ensure_ascii=False)).replace("__FOND__", fond)
    os.makedirs(sortie, exist_ok=True)
    f = os.path.join(sortie, os.path.splitext(os.path.basename(chemin))[0] + "_ecran.html")
    open(f, "w", encoding="utf-8").write(html)
    return f

PAGE = r"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Validation du metre</title>
<style>
:root{--fond:#f6f5f2;--texte:#1d1d1b;--doux:#6b6b66;--ok:#2e9e5b;--verif:#e08a1e;--rejet:#9a9a95;--valide:#2b6fd6;--carte:#fff}
*{box-sizing:border-box}body{margin:0;font:15px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;background:var(--fond);color:var(--texte)}
header{padding:12px 16px;border-bottom:1px solid #ddd;background:var(--carte);display:flex;gap:16px;flex-wrap:wrap;align-items:center}
header h1{font-size:17px;margin:0}header .doux{color:var(--doux);font-size:13px}
main{display:flex;gap:0;height:calc(100vh - 60px)}#plan{flex:1;overflow:auto;position:relative;background:#e9e8e4}
#cadre{position:relative;transform-origin:0 0}#cadre img{display:block}svg{position:absolute;left:0;top:0}
polygon{stroke-width:2;cursor:pointer;fill-opacity:.35}polygon.ok{fill:var(--ok);stroke:var(--ok)}
polygon.verif{fill:var(--verif);stroke:var(--verif)}polygon.valide{fill:var(--valide);stroke:var(--valide);fill-opacity:.25}
polygon.rejet{fill:var(--rejet);stroke:var(--rejet);fill-opacity:.15}polygon.choisi{stroke:#000;stroke-width:4}
aside{width:340px;background:var(--carte);border-left:1px solid #ddd;padding:16px;overflow:auto}
aside h2{font-size:16px;margin:0 0 8px}.ligne{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px dashed #eee}
button{font:inherit;padding:8px 12px;border-radius:8px;border:1px solid #ccc;background:#fff;cursor:pointer;margin:4px 4px 0 0}
button.v{background:var(--valide);color:#fff;border-color:var(--valide)}button.r{background:#fff;color:#a33;border-color:#d9a}
.leg span{display:inline-block;width:12px;height:12px;border-radius:3px;margin:0 4px -1px 10px}
input{font:inherit;width:70px;padding:4px}.aide{color:var(--doux);font-size:13px}
@media (max-width:800px){main{flex-direction:column;height:auto}aside{width:100%}#plan{height:60vh}}
</style></head><body>
<header><h1>Validation du metre</h1><span class="doux" id="info"></span>
<span class="leg"><span style="background:var(--ok)"></span>propose, sur<span style="background:var(--verif)"></span>a verifier<span style="background:var(--valide)"></span>valide<span style="background:var(--rejet)"></span>rejete</span>
<label>Zoom <input type="range" id="zoom" min="0.2" max="2" step="0.1" value="0.6" style="width:110px"></label></header>
<main><div id="plan"><div id="cadre"><img id="fond" src="data:image/jpeg;base64,__FOND__"><svg id="svg"></svg></div></div>
<aside><h2>Lot peinture</h2>
<div class="ligne"><span>Hauteur sous plafond (m)</span><input id="h" type="number" step="0.05"></div>
<div class="ligne"><span>Pieces validees</span><b id="nv">0</b></div>
<div class="ligne"><span>Plafonds valides</span><b id="tp">0 m2</b></div>
<div class="ligne"><span>Murs bruts valides</span><b id="tm">0 m2</b></div>
<p class="aide">Murs bruts = perimetre x hauteur. Portes et fenetres pas encore deduites (maquette).</p>
<button onclick="toutValiderSurs()">Valider toutes les pieces « sures »</button><button onclick="exporter()">Exporter (CSV)</button>
<hr><div id="fiche" class="aide">Cliquez sur une piece du plan.</div></aside></main>
<script>
const D=__DONNEES__;const etat={};let choisi=null;
document.getElementById('info').textContent=D.plan+' - echelle : '+D.echelle;
const h=document.getElementById('h');h.value=D.hauteur;h.oninput=totaux;
const svg=document.getElementById('svg');svg.setAttribute('viewBox','0 0 '+D.largeur+' '+D.hauteur_img);
const sure=p=>p.statut==='ok';
D.pieces.forEach(p=>{const g=document.createElementNS('http://www.w3.org/2000/svg','polygon');
 g.setAttribute('points',p.pts.map(q=>q.join(',')).join(' '));g.id='p'+p.id;g.onclick=()=>choisir(p.id);svg.appendChild(g);etat[p.id]='propose';});
function classe(p){const e=etat[p.id];return e==='valide'?'valide':e==='rejet'?'rejet':(sure(p)?'ok':'verif')}
function dessiner(){D.pieces.forEach(p=>{const g=document.getElementById('p'+p.id);g.setAttribute('class',classe(p)+(choisi===p.id?' choisi':''))});totaux()}
function choisir(id){choisi=id;const p=D.pieces.find(x=>x.id===id);const H=parseFloat(h.value)||0;
 document.getElementById('fiche').innerHTML='<h2>'+p.nom+'</h2>'+
 ['Surface ecrite sur le plan',p.ecrite+' m2','Surface mesuree',(p.calc??'-')+' m2','Ecart',(p.ecart??'-')+' %','Perimetre',(p.perim??'-')+' m','Murs bruts',p.perim?(p.perim*H).toFixed(2)+' m2':'-','Statut moteur',p.statut,'Etat',etat[id]]
 .reduce((a,v,i,t)=>i%2?a:a+'<div class="ligne"><span>'+v+'</span><b>'+t[i+1]+'</b></div>','')+
 '<button class="v" onclick="marquer('+id+',\'valide\')">Valider</button><button class="r" onclick="marquer('+id+',\'rejet\')">Rejeter</button><button onclick="marquer('+id+',\'propose\')">Annuler</button>';dessiner()}
function marquer(id,e){etat[id]=e;choisir(id)}
function toutValiderSurs(){D.pieces.forEach(p=>{if(sure(p)&&etat[p.id]==='propose')etat[p.id]='valide'});dessiner()}
function totaux(){const H=parseFloat(h.value)||0;let n=0,tp=0,tm=0;D.pieces.forEach(p=>{if(etat[p.id]==='valide'&&p.calc){n++;tp+=p.calc;tm+=(p.perim||0)*H}});
 document.getElementById('nv').textContent=n+' / '+D.pieces.length;document.getElementById('tp').textContent=tp.toFixed(2)+' m2';document.getElementById('tm').textContent=tm.toFixed(2)+' m2'}
function exporter(){const H=parseFloat(h.value)||0;let s='Piece;Surface ecrite;Plafond (m2);Perimetre (m);Murs bruts (m2);Etat\n';
 D.pieces.forEach(p=>{s+=[p.nom,p.ecrite,p.calc??'',p.perim??'',p.perim?(p.perim*H).toFixed(2):'',etat[p.id]].join(';')+'\n'});
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['﻿'+s],{type:'text/csv'}));a.download=D.plan.replace('.pdf','')+'_metre.csv';a.click()}
const z=document.getElementById('zoom');function zoomer(v){const w=D.largeur*v,hh=D.hauteur_img*v;const im=document.getElementById('fond');im.style.width=w+'px';im.style.height=hh+'px';svg.setAttribute('width',w);svg.setAttribute('height',hh)}z.oninput=()=>zoomer(parseFloat(z.value));const ajuste=Math.max(0.2,Math.min(2,(document.getElementById('plan').clientWidth-10)/D.largeur));z.value=ajuste.toFixed(2);zoomer(ajuste);dessiner();
</script></body></html>"""

if __name__ == "__main__":
    f = construire(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else os.path.join(ici, "sorties", "ecran"))
    print("ecran :", f)
