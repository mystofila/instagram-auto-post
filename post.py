"""
AFDER.RECOVERY — Carrousel Instagram automatique
Groq  : génère texte
HuggingFace : génère illustration flat design cover
Layout: zones strictes — illustration 380px max, titre adaptatif, rien ne déborde
Slides: 1080x1080px PNG — Open Sans ExtraBold
"""

import os, re, json, math, time, random, base64, datetime, requests, io
from PIL import Image, ImageDraw, ImageFont
import cairosvg
import cloudinary, cloudinary.uploader
from groq import Groq

# ── Config ─────────────────────────────────────────────────────────────────────
GROQ_API_KEY  = os.environ["GROQ_API_KEY"]
HF_API_KEY    = os.environ["HF_API_KEY"]
IG_TOKEN      = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_USER_ID    = os.environ["INSTAGRAM_USER_ID"]
GH_TOKEN      = os.environ["GH_TOKEN"]
REPO          = "mystofila/instagram-auto-post"
HISTORIQUE_FILE = "historique_afder.json"
GROQ_MODEL    = "llama-3.3-70b-versatile"
HF_MODEL      = "stabilityai/stable-diffusion-xl-base-1.0"

cloudinary.config(
    cloud_name = os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key    = os.environ["CLOUDINARY_API_KEY"],
    api_secret = os.environ["CLOUDINARY_API_SECRET"],
)

# ── Polices ────────────────────────────────────────────────────────────────────
_OSD = "/usr/share/fonts/truetype/open-sans/"
_FB  = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def F(name, size):
    try:    return ImageFont.truetype(_OSD + name, size)
    except: return ImageFont.truetype(_FB, size)

# ── Couleurs ───────────────────────────────────────────────────────────────────
WHITE      = (255, 255, 255)
BG_COVER   = (240, 241, 245)
BG_CONTENT = (243, 244, 247)
DARK       = (15,  15,  15)
TEXT_CLR   = (28,  28,  28)
MID_GREY   = (90,  90,  90)
RULE       = (205, 208, 215)
RED        = (240, 80,  80)
SIZE       = 1080

# ── Sujets ─────────────────────────────────────────────────────────────────────
SUJETS = [
    "La co-dépendance, c'est quoi ?",
    "Rechute et échec : ce que disent les neurosciences",
    "La honte en addiction : comment s'en libérer",
    "Pair-aidance : pourquoi l'expérience vécue change tout",
    "Frontières saines : c'est quoi et comment les poser",
    "Santé mentale et addiction : le lien invisible",
    "Famille et addiction : briser le silence",
    "Le rétablissement n'est pas linéaire — et c'est normal",
    "Les signes que tu prends soin de toi malgré tout",
    "Codépendance : quand aider devient épuisant",
    "Vivre avec quelqu'un en addiction : les émotions qu'on tait",
    "Le deuil de la personne qu'on était avant l'addiction",
    "Soutenir sans se perdre : trouver l'équilibre",
    "Les rechutes font partie du chemin",
    "Pair-aidant : un rôle qui part du vécu",
]

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — HISTORIQUE GITHUB
# ═══════════════════════════════════════════════════════════════════════════════

def get_historique():
    r = requests.get(
        f"https://api.github.com/repos/{REPO}/contents/{HISTORIQUE_FILE}",
        headers={"Authorization": f"token {GH_TOKEN}"},
    )
    if r.status_code == 404:
        return [], None
    data = r.json()
    return json.loads(base64.b64decode(data["content"]).decode()), data["sha"]

def save_historique(hist, sha):
    encoded = base64.b64encode(
        json.dumps(hist, ensure_ascii=False, indent=2).encode()
    ).decode()
    payload = {"message": f"Historique AFDER — {datetime.date.today()}", "content": encoded}
    if sha:
        payload["sha"] = sha
    r = requests.put(
        f"https://api.github.com/repos/{REPO}/contents/{HISTORIQUE_FILE}",
        headers={"Authorization": f"token {GH_TOKEN}"}, json=payload,
    )
    print(f"Historique sauvegardé : {r.status_code}")

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — REFRESH TOKEN INSTAGRAM
# ═══════════════════════════════════════════════════════════════════════════════

def refresh_instagram_token(token):
    r = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
    )
    data = r.json()
    if "access_token" not in data:
        print(f"Token non rafraîchi : {data}")
        return token
    new_token = data["access_token"]
    print("Token Instagram rafraîchi ✓")
    pub = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
        headers={"Authorization": f"token {GH_TOKEN}"},
    ).json()
    from nacl import encoding, public as nacl_pub
    pk  = nacl_pub.PublicKey(pub["key"].encode(), encoding.Base64Encoder())
    enc = base64.b64encode(nacl_pub.SealedBox(pk).encrypt(new_token.encode())).decode()
    requests.put(
        f"https://api.github.com/repos/{REPO}/actions/secrets/INSTAGRAM_ACCESS_TOKEN",
        headers={"Authorization": f"token {GH_TOKEN}"},
        json={"encrypted_value": enc, "key_id": pub["key_id"]},
    )
    return new_token

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GROQ : TEXTE UNIQUEMENT
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Tu es rédacteur expert en santé mentale, addiction et pair-aidance pour Instagram.
Tu réponds UNIQUEMENT en JSON valide sur une seule ligne, sans markdown, sans backticks.

LANGUE : Tout le texte doit être en FRANÇAIS CORRECT avec accents (é,è,ê,à,ç).
Zéro mot anglais. Orthographe et grammaire parfaites.

TITRE (accroche) : maximum 5 MOTS en français, MAJUSCULES, percutant et SPÉCIFIQUE au sujet.
Le titre doit être une vérité concrète ou une question directe sur le sujet.
INTERDIT : titres génériques comme "TU N'ES PAS SEUL", "LA GUÉRISON EST POSSIBLE", "NOUS SOMMES LÀ".
INTERDIT : tout mot anglais (MENTAL, HEALTH, RECOVERY, SELF, CARE, etc.)
Exemples VALIDES pour "La honte en addiction" : "LA HONTE N'EST PAS UNE FAUTE", "HONTE ET ADDICTION : LE PIÈGE"
Exemples VALIDES pour "Rechute" : "RECHUTER N'EST PAS ÉCHOUER", "LA RECHUTE FAIT PARTIE DU CHEMIN"
Exemples VALIDES pour "Codépendance" : "AIDER SANS SE PERDRE SOI-MÊME", "QUAND AIDER DEVIENT UNE PRISON"

SLIDES : contenu factuel, concret, basé sur des mécanismes psychologiques réels.
Pas de slogans. Pas de "tu n'es pas seul". Des faits, des processus, des insights actionnables.
Tutoiement bienveillant. Max 190 caractères par slide.

CAPTION : accrocheur, avec question ouverte pour engager la communauté. 3-5 hashtags pertinents."""

def generate_with_retry(client, sujet, titres_deja_utilises, max_retries=3):
    contrainte_titres = ""
    if titres_deja_utilises:
        liste = ", ".join(f'"{t}"' for t in titres_deja_utilises[-10:])
        contrainte_titres = f"\nTITRES DÉJÀ UTILISÉS À ÉVITER ABSOLUMENT : {liste}"

    prompt = f"""Crée un carrousel Instagram pour @afder.recovery sur : "{sujet}"{contrainte_titres}

Réponds avec ce JSON sur UNE SEULE LIGNE :
{{"accroche":"TITRE SPÉCIFIQUE AU SUJET MAX 5 MOTS MAJUSCULES","slides":[{{"contenu":"fait concret ou mécanisme psychologique réel, tutoiement, max 190 chars"}},{{"contenu":"suite pratique ou insight actionnable, max 190 chars"}}],"cta":"CTA FRANÇAIS MAJUSCULES max 28 chars","cta_sous":"phrase bienveillante française max 80 chars","caption":"accroche + question communauté + 3-5 hashtags, max 190 chars"}}"""

    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.85,
                max_tokens=1200,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if any(x in str(e).lower() for x in ["rate_limit", "503", "500"]):
                wait = 15 * (attempt + 1)
                print(f"Groq rate-limit, retry {wait}s… ({attempt+1}/{max_retries})")
                time.sleep(wait)
            else:
                raise
    raise Exception("Groq indisponible après 3 tentatives")


def parse_groq_response(raw: str) -> dict:
    text = raw.strip()
    if "```" in text:
        for part in text.split("```")[1:]:
            c = part.strip().lstrip("json").strip()
            if c.startswith("{"): text = c; break

    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        raise ValueError(f"Pas de JSON : {text[:200]}")
    text = text[s:e+1]
    text = text.replace("\u2019","'").replace("\u2018","'")
    text = text.replace("\u201c",'"').replace("\u201d",'"')

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            data = json.loads(repair_json(text))
            print("JSON réparé via json-repair")
        except Exception:
            raise ValueError(f"JSON invalide : {text[:300]}")

    for key in ["accroche", "slides", "cta", "cta_sous", "caption"]:
        if key not in data:
            raise ValueError(f"Clé manquante : '{key}'")
    if not isinstance(data.get("slides"), list) or len(data["slides"]) < 2:
        raise ValueError("'slides' doit avoir au moins 2 éléments")

    MOTS_ANGLAIS = {"mental","health","recovery","self","care","love","mind","brain",
                    "body","soul","help","support","heal","feel","life","free","hope",
                    "strong","safe","okay","well","good","bad","you","your","we","our"}
    TITRES_GENERIQUES = {
        "tu n'es pas seul", "tu nes pas seul", "la guerison est possible",
        "la guérison est possible", "nous sommes là", "nous sommes la",
        "tu peux y arriver", "ensemble on est plus forts", "tu n'es pas seule",
    }
    accroche = data.get("accroche", "")
    mots = accroche.split()
    if len(mots) > 6:
        print(f"⚠ Titre trop long ({len(mots)} mots) : {accroche!r} → tronqué")
        data["accroche"] = " ".join(mots[:5])
    mots_en = [m for m in mots if m.lower().strip(".,!?'") in MOTS_ANGLAIS]
    if mots_en:
        print(f"⚠ Mots anglais détectés dans le titre : {mots_en}")
    if accroche.lower().strip(".,!?'\"") in TITRES_GENERIQUES:
        print(f"⚠ Titre générique détecté : {accroche!r} — sera régénéré si possible")
        data["_titre_generique"] = True

    return data

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — SVG FALLBACKS
# ═══════════════════════════════════════════════════════════════════════════════

def get_svg_for_sujet(sujet: str) -> str:
    s = sujet.lower()
    if any(w in s for w in ["famille","parent","enfant","proche","silence"]):
        return SVG_FAMILY
    if any(w in s for w in ["cerveau","neuro","rechute","science","linéaire","chemin"]):
        return SVG_BRAIN
    if any(w in s for w in ["honte","identité","miroir","estime","deuil"]):
        return SVG_MIRROR
    if any(w in s for w in ["arbre","croissance","rétabli","soin","signes"]):
        return SVG_TREE
    if any(w in s for w in ["codépendance","dépendance","co-dépendance","frontière","épuisant","perdre"]):
        return SVG_CODEP
    return SVG_PEOPLE

SVG_PEOPLE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">
  <circle cx="250" cy="270" r="205" fill="#DDE3ED"/>
  <circle cx="155" cy="190" r="52" fill="#FBBF8A"/>
  <ellipse cx="155" cy="155" rx="40" ry="24" fill="#E8622A"/>
  <circle cx="130" cy="163" r="17" fill="#E8622A"/>
  <circle cx="180" cy="163" r="17" fill="#E8622A"/>
  <rect x="112" y="238" width="86" height="95" rx="30" fill="#3B82F6"/>
  <rect x="112" y="318" width="30" height="70" rx="15" fill="#3B82F6"/>
  <rect x="168" y="318" width="30" height="70" rx="15" fill="#3B82F6"/>
  <circle cx="141" cy="192" r="6" fill="#7C3A1E"/>
  <circle cx="169" cy="192" r="6" fill="#7C3A1E"/>
  <path d="M139 208 Q155 220 171 208" stroke="#7C3A1E" stroke-width="4" fill="none" stroke-linecap="round"/>
  <ellipse cx="130" cy="204" rx="12" ry="8" fill="#F9A8A8" opacity="0.6"/>
  <ellipse cx="180" cy="204" rx="12" ry="8" fill="#F9A8A8" opacity="0.6"/>
  <rect x="195" y="265" width="55" height="22" rx="11" fill="#FBBF8A"/>
  <circle cx="345" cy="190" r="52" fill="#C68642"/>
  <ellipse cx="345" cy="158" rx="38" ry="22" fill="#6B7280"/>
  <circle cx="320" cy="165" r="16" fill="#6B7280"/>
  <circle cx="370" cy="165" r="16" fill="#6B7280"/>
  <rect x="302" y="238" width="86" height="95" rx="30" fill="#F472B6"/>
  <rect x="302" y="318" width="30" height="70" rx="15" fill="#F472B6"/>
  <rect x="358" y="318" width="30" height="70" rx="15" fill="#F472B6"/>
  <circle cx="331" cy="192" r="6" fill="#4A2008"/>
  <circle cx="359" cy="192" r="6" fill="#4A2008"/>
  <path d="M329 208 Q345 220 361 208" stroke="#4A2008" stroke-width="4" fill="none" stroke-linecap="round"/>
  <ellipse cx="320" cy="204" rx="12" ry="8" fill="#F9A8A8" opacity="0.5"/>
  <ellipse cx="370" cy="204" rx="12" ry="8" fill="#F9A8A8" opacity="0.5"/>
  <rect x="250" y="265" width="55" height="22" rx="11" fill="#C68642"/>
  <path d="M250 255 C250 255 234 238 223 247 C212 256 223 272 250 288 C277 272 288 256 277 247 C266 238 250 255 250 255Z" fill="#E85D5D"/>
  <g transform="translate(418,90)"><path d="M0,-20 L5,-5 L20,0 L5,5 L0,20 L-5,5 L-20,0 L-5,-5 Z" fill="#FCD34D"/></g>
  <g transform="translate(80,390)"><path d="M0,-13 L3,-3 L13,0 L3,3 L0,13 L-3,3 L-13,0 L-3,-3 Z" fill="#FCD34D"/></g>
  <g transform="translate(420,360)"><path d="M0,-10 L2.5,-2.5 L10,0 L2.5,2.5 L0,10 L-2.5,2.5 L-10,0 L-2.5,-2.5 Z" fill="#FCD34D"/></g>
</svg>"""

SVG_BRAIN = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">
  <circle cx="250" cy="265" r="205" fill="#DDE3ED"/>
  <ellipse cx="250" cy="210" rx="130" ry="105" fill="#FFB3C6"/>
  <ellipse cx="185" cy="195" rx="70" ry="85" fill="#FF8FAB"/>
  <ellipse cx="315" cy="195" rx="70" ry="85" fill="#FF8FAB"/>
  <line x1="250" y1="115" x2="250" y2="305" stroke="#E8607A" stroke-width="5" stroke-linecap="round"/>
  <path d="M130 175 Q155 158 178 175 Q155 192 130 175Z" fill="#E8607A" opacity="0.5"/>
  <path d="M118 220 Q148 200 172 220 Q148 240 118 220Z" fill="#E8607A" opacity="0.5"/>
  <path d="M128 265 Q158 245 180 265 Q158 285 128 265Z" fill="#E8607A" opacity="0.5"/>
  <path d="M370 175 Q345 158 322 175 Q345 192 370 175Z" fill="#E8607A" opacity="0.5"/>
  <path d="M382 220 Q352 200 328 220 Q352 240 382 220Z" fill="#E8607A" opacity="0.5"/>
  <path d="M372 265 Q342 245 320 265 Q342 285 372 265Z" fill="#E8607A" opacity="0.5"/>
  <circle cx="250" cy="355" r="55" fill="#FBBF8A"/>
  <circle cx="232" cy="347" r="7" fill="#7C3A1E"/>
  <circle cx="268" cy="347" r="7" fill="#7C3A1E"/>
  <path d="M230 368 Q250 385 270 368" stroke="#7C3A1E" stroke-width="5" fill="none" stroke-linecap="round"/>
  <ellipse cx="220" cy="362" rx="12" ry="8" fill="#F9A8A8" opacity="0.6"/>
  <ellipse cx="280" cy="362" rx="12" ry="8" fill="#F9A8A8" opacity="0.6"/>
  <polygon points="275,130 258,168 270,168 248,210 272,210 245,255 295,200 272,200 290,165 275,165 292,130" fill="#FCD34D"/>
  <g transform="translate(95,105)"><path d="M0,-18 L4.5,-4.5 L18,0 L4.5,4.5 L0,18 L-4.5,4.5 L-18,0 L-4.5,-4.5 Z" fill="#FCD34D"/></g>
  <g transform="translate(408,108)"><path d="M0,-14 L3.5,-3.5 L14,0 L3.5,3.5 L0,14 L-3.5,3.5 L-14,0 L-3.5,-3.5 Z" fill="#FCD34D"/></g>
</svg>"""

SVG_FAMILY = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">
  <circle cx="250" cy="270" r="210" fill="#DDE3ED"/>
  <circle cx="135" cy="168" r="50" fill="#FBBF8A"/>
  <ellipse cx="135" cy="135" rx="38" ry="22" fill="#E8622A"/>
  <circle cx="112" cy="142" r="16" fill="#E8622A"/>
  <circle cx="158" cy="142" r="16" fill="#E8622A"/>
  <rect x="95" y="214" width="80" height="100" rx="28" fill="#3B82F6"/>
  <rect x="95" y="300" width="28" height="72" rx="14" fill="#3B82F6"/>
  <rect x="147" y="300" width="28" height="72" rx="14" fill="#3B82F6"/>
  <circle cx="122" cy="170" r="6" fill="#7C3A1E"/>
  <circle cx="148" cy="170" r="6" fill="#7C3A1E"/>
  <path d="M120 186 Q135 197 150 186" stroke="#7C3A1E" stroke-width="3.5" fill="none" stroke-linecap="round"/>
  <ellipse cx="112" cy="181" rx="11" ry="7" fill="#F9A8A8" opacity="0.6"/>
  <ellipse cx="158" cy="181" rx="11" ry="7" fill="#F9A8A8" opacity="0.6"/>
  <circle cx="365" cy="168" r="50" fill="#C68642"/>
  <ellipse cx="365" cy="137" rx="36" ry="21" fill="#6B7280"/>
  <circle cx="342" cy="144" r="15" fill="#6B7280"/>
  <circle cx="388" cy="144" r="15" fill="#6B7280"/>
  <rect x="325" y="214" width="80" height="100" rx="28" fill="#F472B6"/>
  <rect x="325" y="300" width="28" height="72" rx="14" fill="#F472B6"/>
  <rect x="377" y="300" width="28" height="72" rx="14" fill="#F472B6"/>
  <circle cx="352" cy="170" r="6" fill="#4A2008"/>
  <circle cx="378" cy="170" r="6" fill="#4A2008"/>
  <path d="M350 186 Q365 197 380 186" stroke="#4A2008" stroke-width="3.5" fill="none" stroke-linecap="round"/>
  <ellipse cx="342" cy="181" rx="11" ry="7" fill="#F9A8A8" opacity="0.5"/>
  <ellipse cx="388" cy="181" rx="11" ry="7" fill="#F9A8A8" opacity="0.5"/>
  <circle cx="250" cy="248" r="38" fill="#FBBF8A"/>
  <ellipse cx="250" cy="222" rx="28" ry="16" fill="#92400E"/>
  <rect x="220" y="283" width="60" height="80" rx="22" fill="#4ADE80"/>
  <rect x="220" y="345" width="22" height="55" rx="11" fill="#4ADE80"/>
  <rect x="258" y="345" width="22" height="55" rx="11" fill="#4ADE80"/>
  <circle cx="238" cy="250" r="5" fill="#7C3A1E"/>
  <circle cx="262" cy="250" r="5" fill="#7C3A1E"/>
  <path d="M236 264 Q250 274 264 264" stroke="#7C3A1E" stroke-width="3" fill="none" stroke-linecap="round"/>
  <ellipse cx="230" cy="259" rx="9" ry="6" fill="#F9A8A8" opacity="0.6"/>
  <ellipse cx="270" cy="259" rx="9" ry="6" fill="#F9A8A8" opacity="0.6"/>
  <rect x="172" y="272" width="52" height="18" rx="9" fill="#FBBF8A"/>
  <rect x="276" y="272" width="52" height="18" rx="9" fill="#C68642"/>
  <g transform="translate(250,100)"><path d="M0,-22 L5.5,-5.5 L22,0 L5.5,5.5 L0,22 L-5.5,5.5 L-22,0 L-5.5,-5.5 Z" fill="#FCD34D"/></g>
</svg>"""

SVG_TREE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">
  <circle cx="250" cy="270" r="210" fill="#DDE3ED"/>
  <rect x="228" y="320" width="44" height="130" rx="18" fill="#A0784A"/>
  <path d="M228 430 Q195 448 168 458" stroke="#8B6914" stroke-width="8" stroke-linecap="round" fill="none"/>
  <path d="M250 445 Q250 462 250 475" stroke="#8B6914" stroke-width="8" stroke-linecap="round" fill="none"/>
  <path d="M272 430 Q305 448 332 458" stroke="#8B6914" stroke-width="8" stroke-linecap="round" fill="none"/>
  <ellipse cx="250" cy="325" rx="118" ry="88" fill="#7BC47F"/>
  <ellipse cx="250" cy="268" rx="100" ry="80" fill="#5BAF60"/>
  <ellipse cx="250" cy="215" rx="80" ry="66" fill="#3D9443"/>
  <ellipse cx="250" cy="168" rx="58" ry="50" fill="#2D7A35"/>
  <circle cx="192" cy="278" r="12" fill="#E85D5D"/>
  <circle cx="308" cy="278" r="12" fill="#E85D5D"/>
  <circle cx="250" cy="242" r="11" fill="#F7C948"/>
  <circle cx="210" cy="225" r="10" fill="#E85D5D"/>
  <circle cx="290" cy="225" r="10" fill="#F7C948"/>
  <circle cx="250" cy="195" r="9" fill="#E85D5D"/>
  <ellipse cx="340" cy="190" rx="18" ry="12" fill="#60A5FA"/>
  <circle cx="354" cy="185" r="9" fill="#60A5FA"/>
  <circle cx="359" cy="183" r="3" fill="#1E3A5F"/>
  <polygon points="364,185 372,183 364,187" fill="#F7C948"/>
  <path d="M322 190 Q330 175 340 182" stroke="#60A5FA" stroke-width="3" fill="none" stroke-linecap="round"/>
  <g transform="translate(105,130)"><path d="M0,-18 L4.5,-4.5 L18,0 L4.5,4.5 L0,18 L-4.5,4.5 L-18,0 L-4.5,-4.5 Z" fill="#FCD34D"/></g>
  <g transform="translate(408,340)"><path d="M0,-12 L3,-3 L12,0 L3,3 L0,12 L-3,3 L-12,0 L-3,-3 Z" fill="#FCD34D"/></g>
</svg>"""

SVG_MIRROR = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">
  <circle cx="250" cy="265" r="210" fill="#DDE3ED"/>
  <rect x="148" y="65" width="204" height="295" rx="102" fill="#C4A167"/>
  <rect x="160" y="77" width="180" height="271" rx="92" fill="#EEF6FB"/>
  <path d="M185 108 C185 108 170 135 174 158" stroke="white" stroke-width="8" stroke-linecap="round" opacity="0.75"/>
  <rect x="222" y="360" width="56" height="85" rx="28" fill="#C4A167"/>
  <ellipse cx="250" cy="445" rx="45" ry="12" fill="#B8904A"/>
  <circle cx="250" cy="178" r="44" fill="#FBBF8A"/>
  <ellipse cx="250" cy="147" rx="36" ry="21" fill="#E8622A"/>
  <circle cx="227" cy="155" r="14" fill="#E8622A"/>
  <circle cx="273" cy="155" r="14" fill="#E8622A"/>
  <rect x="216" y="218" width="68" height="92" rx="26" fill="#A78BFA"/>
  <rect x="216" y="295" width="25" height="58" rx="12" fill="#A78BFA"/>
  <rect x="259" y="295" width="25" height="58" rx="12" fill="#A78BFA"/>
  <circle cx="237" cy="180" r="6" fill="#7C3A1E"/>
  <circle cx="263" cy="180" r="6" fill="#7C3A1E"/>
  <path d="M235 197 Q250 209 265 197" stroke="#7C3A1E" stroke-width="4" fill="none" stroke-linecap="round"/>
  <ellipse cx="226" cy="192" rx="11" ry="7" fill="#F9A8A8" opacity="0.65"/>
  <ellipse cx="274" cy="192" rx="11" ry="7" fill="#F9A8A8" opacity="0.65"/>
  <g transform="translate(108,112)"><path d="M0,-16 L4,-4 L16,0 L4,4 L0,16 L-4,4 L-16,0 L-4,-4 Z" fill="#FCD34D"/></g>
  <g transform="translate(392,112)"><path d="M0,-16 L4,-4 L16,0 L4,4 L0,16 L-4,4 L-16,0 L-4,-4 Z" fill="#FCD34D"/></g>
  <g transform="translate(410,350)"><path d="M0,-12 L3,-3 L12,0 L3,3 L0,12 L-3,3 L-12,0 L-3,-3 Z" fill="#FCD34D"/></g>
</svg>"""

SVG_CODEP = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">
  <circle cx="250" cy="270" r="205" fill="#DDE3ED"/>
  <circle cx="205" cy="250" r="95" fill="#93C5FD" opacity="0.7"/>
  <circle cx="295" cy="250" r="95" fill="#F9A8D4" opacity="0.7"/>
  <path d="M250 162 Q298 175 298 250 Q298 325 250 338 Q202 325 202 250 Q202 175 250 162Z" fill="#C4B5FD" opacity="0.85"/>
  <circle cx="172" cy="215" r="38" fill="#FBBF8A"/>
  <ellipse cx="172" cy="190" rx="30" ry="17" fill="#3B82F6"/>
  <circle cx="158" cy="197" r="11" fill="#3B82F6"/>
  <circle cx="186" cy="197" r="11" fill="#3B82F6"/>
  <circle cx="161" cy="217" r="5" fill="#7C3A1E"/>
  <circle cx="183" cy="217" r="5" fill="#7C3A1E"/>
  <path d="M159 232 Q172 230 185 232" stroke="#7C3A1E" stroke-width="3.5" fill="none" stroke-linecap="round"/>
  <ellipse cx="152" cy="225" rx="9" ry="6" fill="#F9A8A8" opacity="0.6"/>
  <ellipse cx="192" cy="225" rx="9" ry="6" fill="#F9A8A8" opacity="0.6"/>
  <circle cx="328" cy="215" r="38" fill="#C68642"/>
  <ellipse cx="328" cy="191" rx="28" ry="16" fill="#6B7280"/>
  <circle cx="314" cy="198" r="10" fill="#6B7280"/>
  <circle cx="342" cy="198" r="10" fill="#6B7280"/>
  <circle cx="317" cy="217" r="5" fill="#4A2008"/>
  <circle cx="339" cy="217" r="5" fill="#4A2008"/>
  <path d="M315 232 Q328 228 341 232" stroke="#4A2008" stroke-width="3.5" fill="none" stroke-linecap="round"/>
  <ellipse cx="308" cy="225" rx="9" ry="6" fill="#F9A8A8" opacity="0.5"/>
  <ellipse cx="348" cy="225" rx="9" ry="6" fill="#F9A8A8" opacity="0.5"/>
  <circle cx="250" cy="290" r="14" fill="none" stroke="#8B5CF6" stroke-width="5"/>
  <circle cx="250" cy="320" r="14" fill="none" stroke="#8B5CF6" stroke-width="5"/>
  <rect x="244" y="300" width="12" height="24" fill="#DDE3ED"/>
  <g transform="translate(415,92)"><path d="M0,-18 L4.5,-4.5 L18,0 L4.5,4.5 L0,18 L-4.5,4.5 L-18,0 L-4.5,-4.5 Z" fill="#FCD34D"/></g>
  <g transform="translate(82,400)"><path d="M0,-13 L3,-3 L13,0 L3,3 L0,13 L-3,3 L-13,0 L-3,-3 Z" fill="#FCD34D"/></g>
</svg>"""

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — UTILITAIRES DESSIN
# ═══════════════════════════════════════════════════════════════════════════════

def _blob(img, cx, cy, rx, ry, color=(195,205,215), alpha=55):
    ov = Image.new("RGBA", img.size, (0,0,0,0))
    ImageDraw.Draw(ov).ellipse([cx-rx,cy-ry,cx+rx,cy+ry], fill=(*color,alpha))
    base = img.convert("RGBA"); base.paste(ov, mask=ov)
    return base.convert("RGB")

def _wrap(draw, text, font, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = f"{cur} {w}".strip()
        if draw.textbbox((0,0), t, font=font)[2] <= max_w: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def _arrow_btn(draw, cx, cy, r=56):
    draw.ellipse([cx-r,cy-r,cx+r,cy+r], fill=RED)
    draw.line([(cx-15,cy),(cx+13,cy)], fill=WHITE, width=5)
    draw.polygon([(cx+5,cy-10),(cx+21,cy),(cx+5,cy+10)], fill=WHITE)

def _prev_btn(draw, cy):
    draw.ellipse([18,cy-44,82,cy+44], fill=(222,223,228))
    draw.polygon([(58,cy-16),(40,cy),(58,cy+16)], fill=(145,145,155))

def _nav_dots(draw, total, active):
    gap=20; sx=(SIZE-(total-1)*gap)//2; cy=SIZE-30
    for i in range(total):
        x = sx+i*gap
        if i==active: draw.ellipse([x-5,cy-5,x+5,cy+5], fill=DARK)
        else:         draw.ellipse([x-4,cy-4,x+4,cy+4], fill=RULE)

def _sep(draw, y=SIZE-102):
    draw.line([(55,y),(SIZE-192,y)], fill=RULE, width=2)

def _heart_shape(draw, cx, cy, sz, color):
    pts = []
    for i in range(360):
        a=math.radians(i); sc=sz/100
        pts.append((cx+int(sz*(16*math.sin(a)**3)*sc*0.56),
                    cy-int(sz*(13*math.cos(a)-5*math.cos(2*a)-2*math.cos(3*a)-math.cos(4*a))*sc*0.56)))
    draw.polygon(pts, fill=color)

def _svg_to_pil(svg_str: str, px: int) -> Image.Image:
    svg = svg_str.strip()
    if 'viewBox' not in svg:
        svg = svg.replace('<svg ', '<svg viewBox="0 0 500 500" ', 1)
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=px, output_height=px)
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    if img.size != (px, px):
        img = img.resize((px, px), Image.LANCZOS)
    return img

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — HUGGINGFACE : IMAGE COVER
# ═══════════════════════════════════════════════════════════════════════════════

# Prompts par thème — style flat design illustration cohérent
HF_PROMPTS = {
    "famille":      "flat design illustration, family support and connection, warm pastel colors, simple geometric shapes, caring figures, soft background, mental health awareness poster style, no text",
    "rechute":      "flat design illustration, person walking forward on a winding path, resilience and hope, muted tones, simple geometric shapes, gentle journey metaphor, mental health awareness style, no text",
    "honte":        "flat design illustration, person emerging from shadow into light, self-compassion theme, soft warm colors, simple geometric shapes, gentle and hopeful mood, mental health awareness poster, no text",
    "pair":         "flat design illustration, two figures side by side in solidarity, peer support theme, warm pastel colors, simple geometric shapes, community and empathy, mental health awareness style, no text",
    "frontière":    "flat design illustration, person standing calmly with clear personal space, boundaries and self-respect, soft colors, simple geometric shapes, empowerment theme, mental health awareness poster, no text",
    "codépendance": "flat design illustration, two overlapping circles with figures finding balance, codependency awareness, soft pastel colors, simple geometric shapes, equilibrium theme, mental health style, no text",
    "deuil":        "flat design illustration, person holding a glowing light, grief and healing journey, soft muted colors, simple geometric shapes, gentle hopeful mood, mental health awareness poster, no text",
    "soin":         "flat design illustration, person nurturing a small plant or light, self-care theme, warm soft colors, simple geometric shapes, growth and healing mood, mental health awareness style, no text",
    "default":      "flat design illustration, single figure in calm contemplative pose, mental health and wellbeing, soft pastel colors, simple geometric shapes, peaceful mood, awareness campaign poster style, no text",
}

def _get_hf_prompt(sujet: str) -> str:
    s = sujet.lower()
    if any(w in s for w in ["famille","parent","enfant","proche","silence"]): return HF_PROMPTS["famille"]
    if any(w in s for w in ["rechute","linéaire","chemin","neuroscience"]):   return HF_PROMPTS["rechute"]
    if any(w in s for w in ["honte","deuil","identité"]):                     return HF_PROMPTS["honte"]
    if any(w in s for w in ["pair","aidance","vécu"]):                        return HF_PROMPTS["pair"]
    if any(w in s for w in ["frontière","saine","poser"]):                    return HF_PROMPTS["frontière"]
    if any(w in s for w in ["codépendance","co-dépendance","épuisant","perdre"]): return HF_PROMPTS["codépendance"]
    if any(w in s for w in ["deuil"]):                                        return HF_PROMPTS["deuil"]
    if any(w in s for w in ["soin","signes","prends"]):                       return HF_PROMPTS["soin"]
    return HF_PROMPTS["default"]

def fetch_cover_image(sujet: str) -> Image.Image:
    """Génère l'image cover via HuggingFace SDXL → retourne PIL Image."""
    prompt = _get_hf_prompt(sujet)
    negative = "photorealistic, photo, 3d render, text, watermark, logo, ugly, blurry, dark, violent, sad"

    print(f"HuggingFace : appel {HF_MODEL}…")
    resp = requests.post(
        f"https://api-inference.huggingface.co/models/{HF_MODEL}",
        headers={"Authorization": f"Bearer {HF_API_KEY}"},
        json={
            "inputs": prompt,
            "parameters": {
                "negative_prompt": negative,
                "width":  1024,
                "height": 1024,
                "num_inference_steps": 30,
                "guidance_scale": 7.5,
            },
            "options": {"wait_for_model": True},
        },
        timeout=120,
    )
    print(f"HuggingFace : status {resp.status_code}")

    if resp.status_code == 503:
        # Modèle en cours de chargement — attente et retry
        print("Modèle en chargement, attente 30s…")
        time.sleep(30)
        resp = requests.post(
            f"https://api-inference.huggingface.co/models/{HF_MODEL}",
            headers={"Authorization": f"Bearer {HF_API_KEY}"},
            json={
                "inputs": prompt,
                "parameters": {
                    "negative_prompt": negative,
                    "width":  1024,
                    "height": 1024,
                    "num_inference_steps": 30,
                    "guidance_scale": 7.5,
                },
                "options": {"wait_for_model": True},
            },
            timeout=120,
        )
        print(f"HuggingFace retry : status {resp.status_code}")

    if resp.status_code != 200:
        raise RuntimeError(f"HuggingFace {resp.status_code} — {resp.text[:300]}")

    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    print(f"HuggingFace : image reçue {img.size} ✓")
    return img.resize((SIZE, SIZE), Image.LANCZOS)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — CRÉATION DES SLIDES
# ═══════════════════════════════════════════════════════════════════════════════

def make_cover(titre: str, sujet: str, svg: str, total: int) -> str:
    """
    Slide 1 — cover.
    Priorité : image HuggingFace plein fond + overlay gradient + titre blanc.
    Fallback  : fond gris + illustration SVG + titre sombre.
    """
    ILLUS_SIZE = 380
    ILLUS_ZONE_Y1, ILLUS_ZONE_Y2 = 415, 950
    TITRE_ZONE_Y1, TITRE_ZONE_Y2 = 55,  400

    ai_ok = False
    try:
        bg = fetch_cover_image(sujet)
        ai_ok = True
    except Exception as e:
        print(f"HuggingFace indisponible ({e}) → fallback SVG")

    if ai_ok:
        img = bg.copy()
        overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for i in range(520):
            alpha = int((i / 520) ** 1.5 * 195)
            od.line([(0, SIZE - 520 + i), (SIZE, SIZE - 520 + i)], fill=(0, 0, 0, alpha))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        d = ImageDraw.Draw(img)

        margin = 55
        max_w  = SIZE - margin * 2
        f = lines = None
        for font_size in [100, 86, 72, 60, 50]:
            f     = F("OpenSans-ExtraBold.ttf", font_size)
            lines = _wrap(d, titre.upper(), f, max_w)
            if len(lines) <= 3:
                break
        bloc_h = len(lines) * int(f.size * 1.1)
        y = SIZE - 160 - bloc_h
        for line in lines:
            d.text((margin + 3, y + 3), line, font=f, fill=(0, 0, 0, 160))
            d.text((margin,     y    ), line, font=f, fill=(255, 255, 255))
            y += int(f.size * 1.1)

    else:
        img = Image.new("RGB", (SIZE, SIZE), BG_COVER)
        img = _blob(img, SIZE - 30, SIZE // 2 + 60, 340, 420, (188, 200, 215), alpha=65)
        img = _blob(img, -20,       SIZE - 50,      160, 160, (190, 205, 215), alpha=40)

        illus = _svg_to_pil(svg, ILLUS_SIZE)
        ix = (SIZE - ILLUS_SIZE) // 2
        iy = ILLUS_ZONE_Y1 + (ILLUS_ZONE_Y2 - ILLUS_ZONE_Y1 - ILLUS_SIZE) // 2
        img.paste(illus, (ix, iy), illus)

        d = ImageDraw.Draw(img)
        margin = 55
        max_w  = SIZE - margin * 2
        f = lines = None
        for font_size in [108, 92, 78, 66, 54]:
            f     = F("OpenSans-ExtraBold.ttf", font_size)
            lines = _wrap(d, titre.upper(), f, max_w)
            if len(lines) * int(font_size * 1.08) <= (TITRE_ZONE_Y2 - TITRE_ZONE_Y1 - 20):
                break
        bloc_h = len(lines) * int(f.size * 1.08)
        y = TITRE_ZONE_Y1 + (TITRE_ZONE_Y2 - TITRE_ZONE_Y1 - bloc_h) // 2
        for line in lines:
            d.text((margin, y), line, font=f, fill=DARK)
            y += int(f.size * 1.08)

    d = ImageDraw.Draw(img)
    _sep(d)
    _arrow_btn(d, SIZE - 100, SIZE - 100)
    _nav_dots(d, total, 0)

    path = "/tmp/afder_slide_1.png"
    img.save(path, format="PNG")
    print(f"Slide 1 sauvegardée → {path}")
    return path


def make_content(texte: str, slide_idx: int, total: int) -> str:
    img = Image.new("RGB", (SIZE, SIZE), BG_CONTENT)
    img = _blob(img, SIZE-40, SIZE//2+200, 280,320, (188,200,215), alpha=40)

    d = ImageDraw.Draw(img)
    f_reg  = F("OpenSans-Regular.ttf", 66)
    f_bold = F("OpenSans-Bold.ttf",    66)
    margin = 72; max_w = SIZE-margin*2
    lh = int(f_reg.size*1.50)
    sp = d.textbbox((0,0)," ",font=f_reg)[2]

    tokens = re.split(r'(\*\*[^*]+\*\*)', texte)
    wf = []
    for tok in tokens:
        if tok.startswith("**") and tok.endswith("**"):
            for w in tok[2:-2].split(): wf.append((w, f_bold))
        else:
            for w in tok.split(): wf.append((w, f_reg))

    lines_wf, cur_l, cur_w = [], [], 0
    for word, font in wf:
        ww = d.textbbox((0,0),word,font=font)[2]
        need = ww+(sp if cur_l else 0)
        if cur_w+need<=max_w: cur_l.append((word,font)); cur_w+=need
        else:
            if cur_l: lines_wf.append(cur_l)
            cur_l,cur_w=[(word,font)],ww
    if cur_l: lines_wf.append(cur_l)

    total_h = len(lines_wf)*lh
    y = 90 + (SIZE-148-90-total_h)//2
    for wfline in lines_wf:
        lx=margin
        for word,font in wfline:
            d.text((lx,y),word,font=font,fill=TEXT_CLR)
            lx+=d.textbbox((0,0),word,font=font)[2]+sp
        y+=lh

    _sep(d)
    _arrow_btn(d, SIZE-100, SIZE-100)
    _prev_btn(d, SIZE//2)
    _nav_dots(d, total, slide_idx-1)
    path = f"/tmp/afder_slide_{slide_idx}.png"
    img.save(path, format="PNG")
    return path


def make_cta(cta_titre: str, cta_sous: str, total: int) -> str:
    img = Image.new("RGB", (SIZE, SIZE), BG_CONTENT)
    img = _blob(img, SIZE//2, SIZE-60, 440,220, (188,200,215), alpha=62)
    img = _blob(img, 45, 175, 155,155, (188,200,215), alpha=40)

    d = ImageDraw.Draw(img)
    hcy = 138
    d.ellipse([SIZE//2-60,hcy-60,SIZE//2+60,hcy+60], fill=RED)
    _heart_shape(d, SIZE//2, hcy, 44, WHITE)
    d.line([(62,hcy-76),(SIZE//2-88,hcy-76)], fill=RULE, width=2)
    d.line([(SIZE//2+88,hcy-76),(SIZE-62,hcy-76)], fill=RULE, width=2)

    f_cta = F("OpenSans-ExtraBold.ttf", 106)
    lines = _wrap(d, cta_titre, f_cta, SIZE-130)
    if len(lines)>2:
        f_cta=F("OpenSans-ExtraBold.ttf",88)
        lines=_wrap(d,cta_titre,f_cta,SIZE-130)
    y=255
    for line in lines:
        bb=d.textbbox((0,0),line,font=f_cta)
        d.text(((SIZE-(bb[2]-bb[0]))//2,y),line,font=f_cta,fill=DARK)
        y+=int(f_cta.size*1.08)

    y+=34
    f_sub=F("OpenSans-Regular.ttf",50)
    for line in _wrap(d,cta_sous,f_sub,SIZE-175):
        bb=d.textbbox((0,0),line,font=f_sub)
        d.text(((SIZE-(bb[2]-bb[0]))//2,y),line,font=f_sub,fill=MID_GREY)
        y+=int(f_sub.size*1.48)

    f_h=F("OpenSans-Semibold.ttf",46)
    handle="@AFDER.RECOVERY"
    bb=d.textbbox((0,0),handle,font=f_h)
    d.text(((SIZE-(bb[2]-bb[0]))//2,SIZE-130),handle,font=f_h,fill=DARK)
    _sep(d,SIZE-172)
    _prev_btn(d,SIZE//2)
    _nav_dots(d,total,total-1)
    path=f"/tmp/afder_slide_{total}.png"
    img.save(path,format="PNG")
    return path

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 8 — PUBLICATION INSTAGRAM
# ═══════════════════════════════════════════════════════════════════════════════

def ig_child(url):
    r = requests.post(
        f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media",
        data={"image_url":url,"is_carousel_item":"true","access_token":IG_TOKEN},
    )
    resp = r.json()
    if "id" not in resp: raise Exception(f"Child failed: {resp}")
    return resp["id"]

def ig_carousel(ids, caption):
    r = requests.post(
        f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media",
        data={"media_type":"CAROUSEL","children":",".join(ids),
              "caption":caption,"access_token":IG_TOKEN},
    )
    resp = r.json()
    if "id" not in resp: raise Exception(f"Carousel failed: {resp}")
    return resp["id"]

def ig_publish(cid):
    r = requests.post(
        f"https://graph.instagram.com/v19.0/{IG_USER_ID}/media_publish",
        data={"creation_id":cid,"access_token":IG_TOKEN},
    )
    return r.json()

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 9 — MAIN
# ═══════════════════════════════════════════════════════════════════════════════

IG_TOKEN = refresh_instagram_token(IG_TOKEN)

hist, hist_sha = get_historique()
today    = datetime.date.today().strftime("%Y-%m-%d")
deja_vus = [h.get("sujet","") for h in hist]
titres_deja_utilises = [h.get("titre","") for h in hist if h.get("titre")]
neufs    = [s for s in SUJETS if s not in deja_vus]
sujet    = random.choice(neufs) if neufs else random.choice(SUJETS)
print(f"Sujet : {sujet}")

client = Groq(api_key=GROQ_API_KEY)
print("Génération Groq…")

data = None
for tentative in range(3):
    raw  = generate_with_retry(client, sujet, titres_deja_utilises)
    data = parse_groq_response(raw)
    if not data.get("_titre_generique"):
        break
    print(f"Titre générique — nouvelle tentative ({tentative+1}/3)…")
    time.sleep(5)

print(f"Titre retenu : {data['accroche']}")

svg = get_svg_for_sujet(sujet)

hist.append({"date": today, "sujet": sujet, "titre": data["accroche"]})
save_historique(hist, hist_sha)

total  = 4
slides = [
    make_cover(data["accroche"], sujet, svg, total),
    make_content(data["slides"][0]["contenu"], 2, total),
    make_content(data["slides"][1]["contenu"], 3, total),
    make_cta(data["cta"], data["cta_sous"], total),
]
print(f"Slides : {slides}")

urls = []
for path in slides:
    res = cloudinary.uploader.upload(
        path,
        folder="afder_carousel",
        format="png",
        resource_type="image",
        access_mode="public",
    )
    urls.append(res["secure_url"])
    print(f"Upload ✓  {res['secure_url']}")

child_ids = []
for u in urls:
    print(f"Container : {u}")
    child_ids.append(ig_child(u))
    time.sleep(3)

carousel_id = ig_carousel(child_ids, data["caption"])
print(f"Carrousel : {carousel_id}")
time.sleep(15)
pub = ig_publish(carousel_id)
print(f"Publié ✓  {pub}")
