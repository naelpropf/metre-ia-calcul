"""Ecran de validation v2 (26/11 nuit) -- methode rule-of-8 (grille de 8 px + 8 regles d'or de Shneiderman).
Pour un operateur NON metreur ou le client peintre : une LISTE DE TRAVAIL centree sur les alertes.
  files comptees : A verifier / Non trouvees / Sures / Traitees ; chaque ligne dit en MOTS ce qui cloche + 1 bouton ;
  fiche laterale avec les quantites peinture (sol, plafond, murs a peindre, plinthes, ouvertures) et les hypotheses ;
  Annuler partout ; clavier (J/K, Entree, V, R, Echap, ?) ; statut jamais par la seule couleur ; clair / sombre.
Donnees : methode matiere (surfaces exactes) + quantites.py. L'ancien ecran (ecran.py) reste pour comparer.
Usage : python ecran2.py plan.pdf [hauteur] -> sorties/ecran/<plan>_v2.html"""
import base64, io, json, os, sys
import pypdfium2 as pdfium
sys.stdout.reconfigure(encoding="utf-8")
ici = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ici)
from metre import normaliser, echelle_par_cotes, origine
import matiere, quantites


def construire(chemin, hauteur=None, sortie=None):
    capt = {}
    _p = matiere.portes
    def espion(pl, m_pt, conv):
        r = _p(pl, m_pt, conv); capt["cordes"] = r; return r
    matiere.portes = espion
    try:
        import metre_v3
        R = metre_v3.pieces_v3(chemin)   # regime A : la surface ecrite designe le bon contour (pieces sures)
        # CASSURE 1 (27/11) : ce que le DOSSIER apprend sur ce plan (hauteur des coupes, tableau des surfaces)
        import dossier
        ctx = dossier.contexte(chemin)
        hauteur_note = None
        if hauteur is None and ctx.get("hauteur"):
            hauteur = ctx["hauteur"]; pl_ = ctx.get("hauteur_plage") or (hauteur, hauteur)
            hauteur_note = ("hauteur %.2f m lue dans les coupes du dossier (plage %.2f à %.2f m) : à confirmer" % (hauteur, pl_[0], pl_[1])).replace(".", ",") + " — méthode : " + str(ctx.get("hauteur_methode"))
        ctrl = dossier.controle_tableau(ctx.get("tableau") or [], [r["e"] for r in R])
    finally:
        matiere.portes = _p
    plat = normaliser(chemin)
    m_pt = echelle_par_cotes(plat, 0)[0]
    doc = pdfium.PdfDocument(plat); p = doc[0]; W, H = p.get_size(); OX, OY = origine(p)
    k = 2400 / max(W, H)
    img = p.render(scale=k).to_pil().convert("RGB")
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=78)
    fond = base64.b64encode(buf.getvalue()).decode()
    murs = matiere.DERNIERS_MURS_REELS[0] if matiere.DERNIERS_MURS_REELS else None
    pieces = []
    for i, r in enumerate(R):
        e, a, h = r["e"], r["a"], r["h"]
        base = {"id": i, "nom": (e.get("nom") or "(sans nom)").strip(), "ecrite": e.get("surface_ecrite"),
                "x": round(e["x"] * k, 1), "y": round(e["y"] * k, 1)}
        if not a:
            pieces.append({**base, "file": "absente", "doutes": ["pièce non fermée : à tracer à la main"], "pts": []})
            continue
        q = quantites.quantites_piece(e, a, h, capt.get("cordes", []), matiere.DERNIERES_VITRES, m_pt, hauteur, murs=murs, hauteur_note=hauteur_note, menuiseries=ctx.get("menuiseries"))
        pts = [[round(x * k, 1), round(y * k, 1)] for x, y in h.exterior.coords]
        doutes = ([] if r["sure"] else (e.get("doutes") or ["surface non confirmee par l'ecrit"])) + ([ctrl[id(e)]] if id(e) in ctrl else [])
        pieces.append({**base, "file": "sure" if r["sure"] else "verifier", "doutes": doutes, "source": r["source"],
                       "ecart": e.get("ecart_ecrit_pct"), "q": q, "pts": pts})
    donnees = {"plan": os.path.basename(chemin), "largeur": img.size[0], "haut": img.size[1],
               "hauteur": hauteur or 2.5, "hauteur_supposee": hauteur is None, "hauteur_note": hauteur_note, "pieces": pieces,
               "cctp": [{"article": a, "loc": l} for a, l, _ in ctx.get("cctp") or []],   # cassure 1 : perimetre lu dans le CCTP
               "k": k, "m_pt": m_pt, "chemin": os.path.abspath(chemin)}   # k, m_pt : passer de l'image aux metres (traces, exemples IA)
    html = PAGE.replace("__DONNEES__", json.dumps(donnees, ensure_ascii=False)).replace("__FOND__", fond)
    sortie = sortie or os.path.join(ici, "sorties", "ecran")
    os.makedirs(sortie, exist_ok=True)
    f = os.path.join(sortie, os.path.splitext(os.path.basename(chemin))[0][:60] + "_v2.html")
    open(f, "w", encoding="utf-8").write(html)
    return f


PAGE = r"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Validation du métré</title>
<style>
:root{--fond:#f4f3f0;--carte:#fff;--texte:#1c1c1a;--doux:#5c5c57;--trait:#d9d8d3;--accent:#1f5fbf;--accent-t:#fff;
--alerte:#b4231c;--alerte-f:#fbe9e7;--sure:#1d7a46;--sure-f:#e6f4ec;--neutre:#6b6b66;--valide:#1f5fbf;--focus:#ffbf47}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--fond:#161615;--carte:#1f1f1d;--texte:#ecebe7;--doux:#b3b2ac;
--trait:#3a3a37;--accent:#7fb0ff;--accent-t:#0d1b33;--alerte:#ff8a80;--alerte-f:#3a1e1c;--sure:#6fd39b;--sure-f:#16301f;--neutre:#a3a29c;--valide:#7fb0ff}}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{font:14px/24px system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--fond);color:var(--texte);display:flex;flex-direction:column}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
.saut{position:absolute;left:-999px}.saut:focus{left:16px;top:8px;z-index:9;background:var(--carte);padding:8px 16px}
header{height:64px;padding:16px 24px;display:flex;align-items:center;gap:24px;background:var(--carte);box-shadow:inset 0 -1px var(--trait)}
header h1{font-size:20px;line-height:32px;margin:0;white-space:nowrap}
.doux{color:var(--doux)}.petit{font-size:12px;line-height:16px}
.prog{display:flex;align-items:center;gap:8px;margin-left:auto;white-space:nowrap}
.barre{width:160px;height:8px;border-radius:4px;background:var(--trait);overflow:hidden}.barre i{display:block;height:8px;background:var(--valide)}
main{flex:1;display:flex;min-height:0}
#vue{flex:1;overflow:auto;position:relative;background:var(--fond)}
#vue svg{display:block}
.pc{fill-opacity:.28;stroke-width:6;cursor:pointer}
.pc.sure{fill:var(--sure);stroke:var(--sure)}.pc.verifier{fill:var(--alerte);stroke:var(--alerte)}
.pc.valide{fill:var(--valide);stroke:var(--valide)}.pc.rejete{fill:none;stroke:var(--neutre);stroke-dasharray:16 12}
.pc.actif{stroke-width:14;fill-opacity:.45}
.pc.corrigee{fill:var(--valide);stroke:var(--valide);stroke-dasharray:24 12}
#trace{fill:var(--alerte);fill-opacity:.18;stroke:var(--alerte);stroke-width:6;pointer-events:none}
#trace-pts circle{fill:var(--alerte)}
#vue.trace svg{cursor:crosshair}
#mode{position:fixed;top:72px;left:16px;min-height:48px;padding:12px 16px;border-radius:8px;background:var(--carte);color:var(--texte);box-shadow:0 4px 16px rgba(0,0,0,.25);display:none;align-items:center;gap:16px;max-width:calc(100% - 472px)}
#mode.on{display:flex}
.num{font:bold 40px system-ui;paint-order:stroke;stroke:#fff;stroke-width:8px;fill:#1c1c1a;pointer-events:none}
aside{width:424px;display:flex;flex-direction:column;background:var(--carte);box-shadow:inset 1px 0 var(--trait);min-height:0}
.reglage{flex-shrink:0;padding:16px 24px;display:flex;align-items:center;gap:16px;box-shadow:inset 0 -1px var(--trait)}
.reglage label{flex:1}.reglage input{width:96px;height:48px;font:inherit;padding:8px;border-radius:8px;border:0;box-shadow:inset 0 0 0 1px var(--trait);background:var(--fond);color:var(--texte)}
[role=tablist]{flex-shrink:0;display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:16px 24px 8px}
[role=tab]{height:40px;padding:0 16px;border:0;border-radius:8px;font:inherit;background:var(--fond);color:var(--texte);cursor:pointer;white-space:nowrap;display:flex;align-items:center;justify-content:space-between}
[role=tab][aria-selected=true]{background:var(--texte);color:var(--carte)}
.cpt{display:inline-block;min-width:24px;height:24px;line-height:24px;border-radius:12px;padding:0 8px;margin-left:8px;font-size:12px;background:var(--carte);color:var(--texte)}
.cpt.rouge{background:var(--alerte);color:var(--carte)}
#liste{flex:1;overflow:auto;margin:0;padding:0 0 8px;list-style:none}
#liste li{height:64px;padding:8px 24px;display:flex;align-items:center;gap:16px;box-shadow:inset 0 -1px var(--trait);cursor:pointer}
#liste li.alerte{box-shadow:inset 4px 0 0 var(--alerte),inset 0 -1px var(--trait)}
#liste li.sel{background:var(--fond)}
.txt{flex:1;min-width:0}.txt b,.txt span{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.txt span{font-size:12px;line-height:16px;color:var(--doux)}
.etat{font-size:12px;line-height:16px;padding:4px 8px;border-radius:4px;white-space:nowrap}
.etat.verifier,.etat.absente{background:var(--alerte-f);color:var(--alerte)}.etat.sure{background:var(--sure-f);color:var(--sure)}
.etat.valide{background:var(--fond);color:var(--valide)}.etat.rejete{background:var(--fond);color:var(--neutre)}
button.act{height:40px;padding:0 16px;border:0;border-radius:8px;font:inherit;cursor:pointer;background:var(--fond);color:var(--texte);box-shadow:inset 0 0 0 1px var(--trait)}
button.prim{background:var(--accent);color:var(--accent-t);box-shadow:none}
.vide{padding:24px;color:var(--doux)}
.totaux{flex-shrink:0;padding:16px 24px;box-shadow:inset 0 1px var(--trait);display:grid;grid-template-columns:1fr 1fr;gap:8px 16px}
.totaux div{display:flex;justify-content:space-between}.totaux p{grid-column:1/3;margin:0}
#fiche{position:fixed;top:64px;right:0;bottom:0;width:424px;background:var(--carte);box-shadow:-8px 0 24px rgba(0,0,0,.18);padding:24px;overflow:auto;display:none}
#fiche.ouverte{display:block}
#fiche h2{font-size:20px;line-height:32px;margin:0 0 8px}
.doute{margin:0 0 16px;padding:8px 16px;border-radius:8px;background:var(--alerte-f);color:var(--alerte)}
.hyp{margin:0 0 16px;padding:8px 16px;border-radius:8px;background:var(--fond)}
table{width:100%;border-collapse:collapse;margin-bottom:16px}td{height:40px;box-shadow:inset 0 -1px var(--trait)}td+td{text-align:right;font-variant-numeric:tabular-nums}
.boutons{display:flex;gap:8px;flex-wrap:wrap}
#toast{position:fixed;left:16px;bottom:16px;min-height:48px;padding:12px 16px;border-radius:8px;background:var(--texte);color:var(--carte);display:none;align-items:center;gap:16px;max-width:calc(100% - 32px)}
#toast button{background:none;border:0;color:inherit;font:inherit;text-decoration:underline;cursor:pointer;height:40px}
#aide{position:fixed;inset:0;margin:auto;width:min(480px,calc(100% - 32px));height:fit-content;border:0;border-radius:16px;padding:24px;background:var(--carte);color:var(--texte)}
kbd{font:12px/16px ui-monospace,monospace;padding:4px 8px;border-radius:4px;background:var(--fond)}
@media (max-width:900px){main{flex-direction:column}#vue{height:40vh;flex:none}aside{flex:none;overflow:visible}#liste{flex:none;overflow:visible}#info{display:none}.barre{width:64px}aside,#fiche{width:100%}button.act,[role=tab]{height:48px}header{padding:16px}}
</style></head><body>
<a class="saut" href="#liste">Aller à la liste des pièces</a>
<header><h1>Validation du métré</h1><span class="doux petit" id="info"></span>
<div class="prog" aria-label="Avancement"><span id="progt"></span><span class="barre"><i id="progb"></i></span></div></header>
<main><div id="vue" aria-label="Plan avec les pièces"></div>
<aside aria-label="Pièces à traiter">
<div class="reglage"><label for="h">Hauteur sous plafond (m)<span class="petit doux" id="hinfo" style="display:block"></span></label>
<input id="h" type="number" step="0.05" min="1.8" max="6" inputmode="decimal"></div>
<div role="tablist" aria-label="Files de travail" id="files"></div>
<ul id="liste" aria-label="Pièces de la file"></ul>
<div class="totaux" aria-live="polite" id="totaux"></div>
<details id="cctp" style="padding:0 24px 16px"><summary style="min-height:48px;display:flex;align-items:center;cursor:pointer">Ce que le CCTP fait peindre</summary><ul id="cctpl" class="petit" style="margin:0;padding-left:16px;line-height:24px"></ul></details>
<div style="padding:0 24px 16px;display:flex;gap:8px"><button class="act" onclick="exporter()">Exporter (CSV)</button><button class="act" onclick="exporterIA()" title="Contours validés, corrigés et rejetés : exemples pour entraîner l’IA">Exemples IA</button><button class="act" onclick="aide.showModal()" aria-keyshortcuts="?">Raccourcis</button></div>
</aside></main>
<section id="fiche" role="dialog" aria-modal="false" aria-labelledby="ftitre"></section>
<div id="mode" role="status" aria-live="polite"><span id="mtxt"></span><button class="act prim" onclick="finirTrace()">Terminer</button><button class="act" onclick="quitterTrace()">Abandonner</button></div>
<div id="toast" role="status" aria-live="polite"><span id="tmsg"></span><button id="tundo">Annuler</button></div>
<dialog id="aide"><h2 style="margin-top:0">Raccourcis clavier</h2>
<p><kbd>J</kbd> / <kbd>K</kbd> pièce suivante / précédente · <kbd>Entrée</kbd> ouvrir · <kbd>V</kbd> valider · <kbd>R</kbd> rejeter ·
<kbd>U</kbd> annuler la dernière action · <kbd>Échap</kbd> fermer · <kbd>1</kbd>–<kbd>4</kbd> changer de file</p>
<p><kbd>T</kbd> tracer le contour de la pièce ouverte : un clic par coin · <kbd>Entrée</kbd> terminer · <kbd>Retour arrière</kbd> effacer le dernier point · <kbd>Échap</kbd> abandonner</p>
<button class="act prim" onclick="aide.close()">Fermer</button></dialog>
<script>
const D=__DONNEES__;
const FILES=[["verifier","À vérifier"],["absente","Non trouvées"],["sure","Sûres"],["traitee","Traitées"]];
const ETAT={verifier:"À vérifier",absente:"Non trouvée",sure:"Sûre",valide:"Validée",rejete:"Rejetée",corrigee:"Corrigée"};
const FINI=p=>p.etat=="valide"||p.etat=="rejete"||p.etat=="corrigee",COMPTE=p=>p.etat=="valide"||p.etat=="corrigee";
let file=D.pieces.some(p=>p.file=="verifier")?"verifier":"sure",sel=null,hist=[],H=D.hauteur;
// CHRONO de relecture (D-10 : la vitesse de relecture est le chiffre cle) : debut, et temps de decision par piece
const T0=Date.now(),ouvertA={},tempsPiece={};
D.pieces.forEach(p=>p.etat=p.file);  // etat courant ; p.file = file d'origine (ne bouge pas tout seul)
const $=s=>document.querySelector(s),fmt=v=>v==null?"–":v.toLocaleString("fr-FR",{minimumFractionDigits:2,maximumFractionDigits:2});
$("#info").textContent=D.plan;$("#h").value=H;
if(D.cctp&&D.cctp.length){$("#cctpl").innerHTML=D.cctp.map(c=>'<li><b>'+esc(c.article)+'</b> : '+esc(c.loc)+'</li>').join("")}else{$("#cctp").style.display="none"}
// --- plan
const NS="http://www.w3.org/2000/svg",svg=document.createElementNS(NS,"svg");
svg.setAttribute("viewBox","0 0 "+D.largeur+" "+D.haut);svg.setAttribute("width",D.largeur/2);svg.setAttribute("role","img");
svg.innerHTML='<image href="data:image/jpeg;base64,__FOND__" width="'+D.largeur+'" height="'+D.haut+'"/>';
const calque=document.createElementNS(NS,"g");svg.appendChild(calque);
function poly(p){let g=$("#p"+p.id);const pts=p.corrige||p.pts;if(!pts.length){g&&g.remove();return}
 if(!g){g=document.createElementNS(NS,"polygon");g.id="p"+p.id;g.onclick=()=>{if(!trace)ouvrir(p.id)};calque.appendChild(g)}
 g.setAttribute("points",pts.map(q=>q.join(",")).join(" "))}
D.pieces.forEach((p,i)=>{poly(p);
 const t=document.createElementNS(NS,"text");t.setAttribute("x",p.x);t.setAttribute("y",p.y);t.setAttribute("class","num");t.textContent=i+1;svg.appendChild(t);});
$("#vue").appendChild(svg);
function murs(p){if(!p.q)return null;const q=p.q;return Math.max(0,q.perimetre_ml*H-q.ouvertures_deduites_m2)}
function dans(p,f){return f=="traitee"?FINI(p):(p.file==f)}
function dessiner(){
 D.pieces.forEach(p=>{const g=$("#p"+p.id);if(g)g.setAttribute("class","pc "+p.etat+(sel===p.id?" actif":""))});
 $("#files").innerHTML=FILES.map(([k,n],i)=>{const c=D.pieces.filter(p=>dans(p,k)&&(k=="traitee"||p.etat==k)).length;
  return '<button role="tab" aria-selected="'+(file==k)+'" aria-keyshortcuts="'+(i+1)+'" onclick="choisirFile(\''+k+'\')">'+n+
  '<span class="cpt'+((k=="verifier"||k=="absente")&&c?" rouge":"")+'">'+c+'</span></button>'}).join("");
 const L=D.pieces.filter(p=>dans(p,file));
 $("#liste").innerHTML=L.length?L.map(p=>{const al=p.etat=="verifier"||p.etat=="absente";
  const raison=p.doutes.length?p.doutes.join(" · "):(p.q?"Sol "+fmt(p.q.sol_m2)+" m² · murs "+fmt(murs(p))+" m²":"");
  const bt=p.etat=="verifier"?"Vérifier":p.etat=="absente"?"Voir":p.etat=="sure"?"Valider":"Ouvrir";
  return '<li class="'+(al?"alerte ":"")+(sel===p.id?"sel":"")+'" data-id="'+p.id+'" onclick="ouvrir('+p.id+')">'+
  '<div class="txt"><b>'+(D.pieces.indexOf(p)+1)+'. '+esc(p.nom)+'</b><span title="'+esc(raison)+'">'+esc(raison)+'</span></div>'+
  '<span class="etat '+p.etat+'">'+ETAT[p.etat]+'</span>'+
  '<button class="act'+(p.etat=="sure"?" prim":"")+'" onclick="event.stopPropagation();'+(p.etat=="sure"?"marquer("+p.id+",\'valide\')":"ouvrir("+p.id+")")+'">'+bt+'</button></li>'}).join("")
  :'<li class="vide" style="height:auto;box-shadow:none">'+({verifier:"Aucune pièce à vérifier.",absente:"Toutes les pièces ont été trouvées.",sure:"Aucune pièce sûre en attente.",traitee:"Aucune pièce traitée pour l’instant."}[file])+'</li>';
 const V=D.pieces.filter(COMPTE),T=D.pieces.length,F=D.pieces.filter(FINI).length;
 const s=(f)=>V.reduce((a,p)=>a+(f(p)||0),0);
 $("#totaux").innerHTML='<div><span>Sols</span><b>'+fmt(s(p=>p.q.sol_m2))+' m²</b></div><div><span>Plafonds</span><b>'+fmt(s(p=>p.q.plafond_m2))+' m²</b></div>'+
  '<div><span>Murs à peindre</span><b>'+fmt(s(murs))+' m²</b></div><div><span>Plinthes</span><b>'+fmt(s(p=>p.q.plinthes_ml))+' ml</b></div>'+
  '<p class="petit doux">Sur '+V.length+' pièce'+(V.length>1?"s":"")+' validée'+(V.length>1?"s":"")+' sur '+T+'. Hauteur '+fmt(H)+' m'+(D.hauteur_supposee&&H==D.hauteur?" (supposée, à confirmer)":"")+'.</p>';
 $("#hinfo").textContent=D.hauteur_supposee&&H==D.hauteur?"Supposée : à confirmer (coupes, CCTP ou client)":(D.hauteur_note&&H==D.hauteur?"Lue dans les coupes du dossier : à confirmer":"Appliquée à toutes les pièces");
 $("#progt").textContent=F+" / "+T+" traitées";$("#progb").style.width=(100*F/T)+"%";
}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function choisirFile(k){file=k;fermer();dessiner()}
function ouvrir(id){sel=id;ouvertA[id]=ouvertA[id]||Date.now();const p=D.pieces.find(x=>x.id==id),q=p.q;
 let h='<h2 id="ftitre">'+(D.pieces.indexOf(p)+1)+'. '+esc(p.nom)+'</h2><p class="petit doux" style="margin:0 0 16px">'+ETAT[p.etat]+(p.ecrite?" · surface écrite "+fmt(p.ecrite)+" m²":"")+(p.source?" · contour : "+esc(p.source)+(p.etat=="sure"||p.file=="sure"?" (conforme à l’écrit à 1 % près)":""):"")+'</p>';
 p.doutes.forEach(d=>h+='<p class="doute">⚠ '+esc(d)+'</p>');
 if(q){h+='<table><tr><td>Sol / plafond</td><td>'+fmt(q.sol_m2)+' m²</td></tr><tr><td>Périmètre</td><td>'+fmt(q.perimetre_ml)+' ml</td></tr>'+
  '<tr><td>Portes</td><td>'+q.portes_U+(q.portes_larg_m.length?" ("+q.portes_larg_m.map(fmt).join(" ; ")+" m)":"")+'</td></tr>'+
  '<tr><td>Fenêtres (à vérifier)</td><td>'+q.fenetres_U+(q.fenetres_larg_m.length?" ("+q.fenetres_larg_m.map(fmt).join(" ; ")+" m)":"")+'</td></tr>'+
  '<tr><td>Plinthes</td><td>'+fmt(q.plinthes_ml)+' ml</td></tr><tr><td>Murs bruts (h '+fmt(H)+' m)</td><td>'+fmt(q.perimetre_ml*H)+' m²</td></tr>'+
  '<tr><td>Ouvertures déduites</td><td>− '+fmt(q.ouvertures_deduites_m2)+' m²</td></tr><tr><td><b>Murs à peindre</b></td><td><b>'+fmt(murs(p))+' m²</b></td></tr></table>';
  q.hypotheses.filter(x=>!x.startsWith("hauteur 2,50")).forEach(x=>h+='<p class="hyp petit">Hypothèse : '+esc(x)+'</p>');}
 else h+='<p class="hyp">Le logiciel n’a pas pu fermer cette pièce (ouverture non reconnue, ou mur dessiné autrement). Elle est repérée par son numéro sur le plan : tracez son contour (un clic par coin).</p>';
 h+='<div class="boutons">'+(q&&p.etat!="corrigee"?'<button class="act prim" onclick="marquer('+id+',\'valide\')" aria-keyshortcuts="V">Valider</button>':"")+
  '<button class="act'+(q?"":" prim")+'" onclick="tracer('+id+')" aria-keyshortcuts="T">'+(p.corrige?"Retracer":"Tracer le contour")+'</button>'+
  '<button class="act" onclick="marquer('+id+',\'rejete\')" aria-keyshortcuts="R">Rejeter</button>'+
  '<button class="act" onclick="suivante()">Pièce suivante à vérifier</button><button class="act" onclick="fermer()">Fermer</button></div>';
 $("#fiche").innerHTML=h;$("#fiche").classList.add("ouverte");
 const g=$("#p"+id);if(g)g.scrollIntoView({block:"center",inline:"center",behavior:"smooth"});dessiner();
 const b=$("#fiche .prim")||$("#fiche button");b&&b.focus();}
function fermer(){$("#fiche").classList.remove("ouverte");sel=null;dessiner()}
function marquer(id,e){const p=D.pieces.find(x=>x.id==id);hist.push([id,p.etat]);p.etat=e;
 tempsPiece[id]=Math.round((Date.now()-(ouvertA[id]||T0))/1000);
 toast((e=="valide"?"Validée : ":"Rejetée : ")+p.nom+". "+D.pieces.filter(x=>x.etat=="verifier"||x.etat=="absente").length+" pièce(s) restent à voir.");
 if(sel===id)ouvrir(id);else dessiner();}
function annuler(){const h=hist.pop();if(!h)return;const p=D.pieces.find(x=>x.id==h[0]);p.etat=h[1];toast("Annulé : "+p.nom+" revient à « "+ETAT[p.etat]+" ».",true);sel===p.id?ouvrir(p.id):dessiner()}
let tt;function toast(m,sans){$("#tmsg").textContent=m;$("#tundo").style.display=sans?"none":"";$("#toast").style.display="flex";clearTimeout(tt);tt=setTimeout(()=>$("#toast").style.display="none",8000)}
$("#tundo").onclick=()=>annuler();   // toujours la DERNIERE version d'annuler (hauteur, trace)
function suivante(){const L=D.pieces.filter(p=>p.etat=="verifier"||p.etat=="absente");if(!L.length){toast("Plus rien à vérifier. Vous pouvez exporter.",true);fermer();return}
 const n=L.find(p=>p.id>(sel??-1))||L[0];file=n.file;ouvrir(n.id)}
$("#h").onchange=e=>{const v=parseFloat(e.target.value);if(!(v>=1.8&&v<=6)){toast("Hauteur refusée : entre 1,80 et 6,00 m.",true);e.target.value=H;return}
 const av=H;H=v;hist.push(["h",av]);toast("Hauteur "+fmt(v)+" m appliquée à toutes les pièces.");dessiner();if(sel!=null)ouvrir(sel)};
const _ann=annuler;annuler=function(){const h=hist[hist.length-1];if(h&&h[0]=="h"){hist.pop();H=h[1];$("#h").value=H;toast("Hauteur remise à "+fmt(H)+" m.",true);dessiner();return}_ann()};
// --- TRACE A LA MAIN (boucle de correction, facon Togal : chaque piece corrigee = un exemple parfait pour l'IA)
let trace=null;
const ptSvg=e=>{const m=svg.getScreenCTM().inverse(),q=svg.createSVGPoint();q.x=e.clientX;q.y=e.clientY;const r=q.matrixTransform(m);return [Math.round(r.x*10)/10,Math.round(r.y*10)/10]};
const enM=px=>px/D.k*D.m_pt;
function aire(P){let a=0;for(let i=0;i<P.length;i++){const [x1,y1]=P[i],[x2,y2]=P[(i+1)%P.length];a+=x1*y2-x2*y1}return Math.abs(a)/2}
function perim(P){let l=0;for(let i=0;i<P.length;i++){const [x1,y1]=P[i],[x2,y2]=P[(i+1)%P.length];l+=Math.hypot(x2-x1,y2-y1)}return l}
function majTrace(){let g=$("#trace");if(!g){g=document.createElementNS(NS,"polygon");g.id="trace";svg.appendChild(g)}
 g.setAttribute("points",trace.pts.map(q=>q.join(",")).join(" "));
 const p=D.pieces.find(x=>x.id==trace.id),n=trace.pts.length,a=n>2?aire(trace.pts)/(D.k*D.k)*D.m_pt*D.m_pt:0;
 $("#mtxt").textContent="Tracé de « "+p.nom+" » : "+n+" point"+(n>1?"s":"")+(n>2?" · "+fmt(a)+" m²"+(p.ecrite?" (écrit "+fmt(p.ecrite)+" m², écart "+(a/p.ecrite*100-100).toFixed(1).replace(".",",")+" %)":""):" · cliquez les coins de la pièce")}
function tracer(id){trace={id,pts:[]};$("#vue").classList.add("trace");$("#mode").classList.add("on");majTrace();
 toast("Cliquez chaque coin de la pièce, puis Entrée. Retour arrière efface le dernier point.",true)}
svg.addEventListener("click",e=>{if(!trace)return;e.stopPropagation();trace.pts.push(ptSvg(e));majTrace()},true);
function quitterTrace(){trace=null;$("#trace")&&$("#trace").remove();$("#vue").classList.remove("trace");$("#mode").classList.remove("on")}
function finirTrace(){if(!trace)return;if(trace.pts.length<3){toast("Il faut au moins 3 coins.",true);return}
 const p=D.pieces.find(x=>x.id==trace.id),P=trace.pts,a=aire(P)/(D.k*D.k)*D.m_pt*D.m_pt,per=enM(perim(P));
 hist.push(["trace",p.id,p.etat,p.corrige||null,p.q||null,p.doutes]);
 p.corrige=P;p.etat="corrigee";
 p.doutes=p.ecrite&&Math.abs(a/p.ecrite-1)>0.03?["contour tracé : écart "+(a/p.ecrite*100-100).toFixed(1).replace(".",",")+" % avec la surface écrite"]:[];
 p.q={piece:p.nom,sol_m2:+a.toFixed(2),plafond_m2:+a.toFixed(2),perimetre_ml:+per.toFixed(2),portes_U:0,portes_larg_m:[],fenetres_U:0,fenetres_larg_m:[],
  plinthes_ml:+per.toFixed(2),ouvertures_deduites_m2:0,hypotheses:["contour tracé à la main : portes et fenêtres non comptées ni déduites"]};
 tempsPiece[p.id]=Math.round((Date.now()-(ouvertA[p.id]||T0))/1000);
 const ec=p.ecrite?(a/p.ecrite*100-100):null;
 quitterTrace();poly(p);
 toast("Contour enregistré : "+fmt(a)+" m²"+(ec!=null?" (écart "+ec.toFixed(1).replace(".",",")+" % avec l’écrit"+(Math.abs(ec)>3?" : à reprendre ?":"")+")":"")+".");
 ouvrir(p.id)}
const _ann2=annuler;annuler=function(){const h=hist[hist.length-1];if(h&&h[0]=="trace"){hist.pop();const p=D.pieces.find(x=>x.id==h[1]);
 p.etat=h[2];p.corrige=h[3];p.q=h[4];p.doutes=h[5];poly(p);toast("Tracé annulé : "+p.nom+".",true);sel===p.id?ouvrir(p.id):dessiner();return}_ann2()};
function exporterIA(){
 const ex=D.pieces.filter(FINI).map(p=>({id:p.id,nom:p.nom,ecrite:p.ecrite,etat:p.etat,source:p.etat=="corrigee"?"main":p.source||null,
  contour_px:p.etat=="corrigee"?p.corrige:(p.etat=="valide"?p.pts:null),contour_auto_px:p.pts,secondes:tempsPiece[p.id]??null}));
 if(!ex.length){toast("Rien à exporter : traitez au moins une pièce.",true);return}
 const o={plan:D.plan,chemin:D.chemin,k:D.k,m_pt:D.m_pt,date:new Date().toISOString(),hauteur:H,exemples:ex};
 const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([JSON.stringify(o)],{type:"application/json"}));
 a.download="exemples_"+D.plan.replace(/\.pdf$/,"")+".json";a.click();
 toast(ex.length+" exemple(s) exporté(s) : à déposer dans outil/corrections/.",true)}
function exporter(){const V=D.pieces.filter(COMPTE);if(!V.length){toast("Rien à exporter : validez au moins une pièce.",true);return}
 const L=[["piece","sol_m2","plafond_m2","perimetre_ml","portes_U","fenetres_U","plinthes_ml","hauteur_m","murs_a_peindre_m2","hypotheses","file_origine","secondes_decision"]];
 V.forEach(p=>L.push([p.nom,p.q.sol_m2,p.q.plafond_m2,p.q.perimetre_ml,p.q.portes_U,p.q.fenetres_U,p.q.plinthes_ml,H,murs(p).toFixed(2),p.q.hypotheses.join(" / "),p.file,tempsPiece[p.id]??""]));
 L.push(["TEMPS TOTAL DE RELECTURE (s)",Math.round((Date.now()-T0)/1000),"","","","","","","","","pieces traitees",D.pieces.filter(FINI).length]);
 const b=new Blob(["﻿"+L.map(r=>r.map(v=>'"'+String(v).replace(/"/g,'""')+'"').join(";")).join("\n")],{type:"text/csv"});
 const a=document.createElement("a");a.href=URL.createObjectURL(b);a.download="metre_"+D.plan.replace(/\.pdf$/,"")+".csv";a.click();toast(V.length+" pièce(s) exportée(s).",true)}
document.addEventListener("keydown",e=>{if(e.target.tagName=="INPUT")return;
 if(trace){if(e.key=="Enter"){e.preventDefault();finirTrace()}else if(e.key=="Escape")quitterTrace();
  else if(e.key=="Backspace"){e.preventDefault();trace.pts.pop();majTrace()}return}
 if((e.key=="t"||e.key=="T")&&sel!=null){tracer(sel);return}
 const L=[...document.querySelectorAll("#liste li[data-id]")].map(l=>+l.dataset.id);
 const i=L.indexOf(sel);if(e.key=="j"||e.key=="J"){L.length&&ouvrir(L[Math.min(i+1,L.length-1)])}else if(e.key=="k"||e.key=="K"){L.length&&ouvrir(L[Math.max(i-1,0)])}
 else if((e.key=="v"||e.key=="V")&&sel!=null&&D.pieces.find(p=>p.id==sel).q)marquer(sel,"valide");else if((e.key=="r"||e.key=="R")&&sel!=null)marquer(sel,"rejete");
 else if(e.key=="u"||e.key=="U")annuler();else if(e.key=="Escape")fermer();else if(e.key=="?")aide.showModal();else if("1234".includes(e.key)&&e.key)choisirFile(FILES[+e.key-1][0]);
 else if(e.key=="Enter"&&L.length&&sel==null)ouvrir(L[0]);});
dessiner();
</script></body></html>"""

if __name__ == "__main__":
    print(construire(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else None))
