"""CALQUES DU DESSIN (28/11). Les logiciels d'architecte rangent chaque trait dans un calque (Murs, Cloisons, Cotation,
Hachure, Mobilier...) ; le PDF garde ce nom dans le contenu marque (BDC /OC /MCx ... EMC). Mesure : 43 pages d'examen sur
70 ont un calque mur/cloison (3068854 : 13/13, 3085339 : 14/14). pdfplumber ne garde pas ce nom : rustine ci-dessous
(pile des BDC + ressources /Properties de la page), puis chaque objet a un champ « calque ».
  role(nom) -> "mur" | "enveloppe" | "non" | "inconnu"."""
import re
from pdfminer.pdftypes import resolve1
from pdfplumber import page as _pg

PROPS = {}   # ressources /Properties de la page en cours de lecture : {"MC0": {Type: OCG, Name: ...}}


def _nom(n):
    n = resolve1(n)
    if isinstance(n, bytes):
        return n.decode("utf-16") if n[:2] in (b"\xfe\xff", b"\xff\xfe") else n.decode("latin-1")
    return n


_A = _pg.PDFPageAggregatorWithMarkedContent
_b0, _e0, _t0 = _A.begin_tag, _A.end_tag, _A.tag_cur_item   # comportement d'origine garde (mcid, tag)


def _begin_tag(self, tag, props=None):
    _b0(self, tag, props)
    if not hasattr(self, "_pile_oc"): self._pile_oc = []
    t = getattr(tag, "name", tag); t = t.decode() if isinstance(t, bytes) else t
    nom = None
    if t == "OC":
        if not isinstance(props, dict):
            k = getattr(props, "name", props); k = k.decode() if isinstance(k, bytes) else k
            props = PROPS.get(k, {})
        nom = _nom(props.get("Name")) if isinstance(props, dict) else None
    self._pile_oc.append(nom)


def _end_tag(self):
    _e0(self)
    if getattr(self, "_pile_oc", None): self._pile_oc.pop()


def _tag_cur_item(self):
    _t0(self)
    o = self.cur_item._objs[-1] if self.cur_item._objs else None
    if o is not None:
        o.calque = next((c for c in reversed(getattr(self, "_pile_oc", [])) if c), None)


_A.begin_tag, _A.end_tag, _A.tag_cur_item = _begin_tag, _end_tag, _tag_cur_item
_pg.ALL_ATTRS = set(_pg.ALL_ATTRS) | {"calque"}


def preparer(pg):
    """a appeler AVANT de lire pg.lines / rects / curves"""
    PROPS.clear()
    try:
        pr = resolve1(resolve1(pg.page_obj.resources).get("Properties") or {})
        PROPS.update({(k.decode() if isinstance(k, bytes) else k): resolve1(v) for k, v in (pr or {}).items()})
    except Exception:
        pass


def _sans_accent(s):
    import unicodedata
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


RX_MUR = re.compile(r"\bmur|cloison|poteau|voile|ma.?onn|wall|partition|column|structure.{0,6}mur")
RX_ENV = re.compile(r"enveloppe|facade|menuiser|baie|fenetre|window|vitrage|chassis")
RX_NON = re.compile(r"cot(e|ation)|dim|annot|texte|text|hach|motif|mobil|meubl|furn|agencement|sanitaire|equip|"
                    r"escalier|marche|stair|dalle|poutre|toit|terrain|vrd|axe|trame|grid|cartouche|cadre|altim|rep.?r|"
                    r"plafond|faux|elec|plomb|cvc|chauff|ventil|cuisine|vegeta|parking|vehic|voiture|symbol|legende|"
                    r"niveau|coupe|detail|surface|zone|nom|label|tag")


def role(nom):
    s = _sans_accent(nom)
    if not s: return "inconnu"
    if RX_MUR.search(s): return "mur"
    if RX_NON.search(s): return "non"        # avant enveloppe : « Reperages coupes/facades » est une annotation
    if RX_ENV.search(s): return "enveloppe"
    return "inconnu"


def page_a_calques_murs(objs, mini=30):
    """vrai si au moins `mini` traits de la page sont dans un calque reconnu comme mur"""
    n = 0
    for o in objs:
        if role(o.get("calque")) == "mur":
            n += 1
            if n >= mini: return True
    return False
