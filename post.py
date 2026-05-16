"""
AFDER.RECOVERY — Carrousel Instagram automatique
Groq  : génère texte + SVG illustration cartoon (un seul appel)
Layout: zones strictes — illustration 380px max, titre adaptatif, rien ne déborde
Slides: 1080x1080px PNG — Open Sans ExtraBold
"""

import os, re, json, math, time, random, base64, datetime, requests, io
from PIL import Image, ImageDraw, ImageFont
import cairosvg
import cloudinary, cloudinary.uploader
from groq import Groq

# ── Config ─────────────────────────────────────────────────────────────────────
GROQ_API_KEY    = os.environ["GROQ_API_KEY"]
IG_TOKEN        = os.environ["INSTAGRAM_ACCESS_TOKEN"]
IG_USER_ID      = os.environ["INSTAGRAM_USER_ID"]
GH_TOKEN        = os.environ["GH_TOKEN"]
REPO            = "mystofila/instagram-auto-post"
HISTORIQUE_FILE = "historique_afder.json"
GROQ_MODEL      = "llama-3.3-70b-versatile"

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
    "Rechute ≠ échec : ce que disent les neurosciences",
    "La honte en addiction : comment s'en libérer",
    "Pair-aidance : pourquoi l'expérience vécue change tout",
    "Frontières saines : c'est quoi et comment les poser",
    "Santé mentale & addiction : le lien invisible",
    "Famille & addiction : briser le silence",
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
# SECTION 3 — GROQ : TEXTE + SVG
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Tu es expert en santé mentale, addiction, pair-aidance ET illustrateur SVG.
Tu réponds UNIQUEMENT en JSON valide sur une seule ligne, sans markdown, sans backticks.
Le champ svg contient un SVG cartoon flat design coloré inline.
Règles SVG absolues :
- Commence par : <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">
- Termine par : </svg>
- Utilise UNIQUEMENT : circle, ellipse, rect, path, line, polygon, g
- INTERDIT : text, image, use, symbol, defs, filter, style, script
- Fond obligatoire : cercle <circle cx="250" cy="270" r="205" fill="#DDE3ED"/>
- Personnages cartoon : têtes rondes, yeux ronds noirs, sourires, joues roses
- Couleurs peaux #FBBF8A ou #C68642, vêtements colorés vifs
- Étoiles décoratives #FCD34D
- Minimum 15 éléments SVG"""

def generate_with_retry(client, sujet, max_retries=3):
    prompt = f"""Crée un carrousel Instagram pour @afder.recovery sur : "{sujet}"

Réponds avec ce JSON sur UNE SEULE LIGNE (le svg ne doit pas contenir de retours à la ligne) :
{{"accroche":"TITRE MAJUSCULES max 32 chars","slides":[{{"contenu":"2-3 phrases bienveillantes max 190 chars tutoiement"}},{{"contenu":"Suite concrète max 190 chars"}}],"cta":"CTA MAJUSCULES max 28 chars","cta_sous":"phrase bienveillante max 80 chars","caption":"texte Instagram 5 hashtags max 190 chars","svg":"<svg xmlns=\\"http://www.w3.org/2000/svg\\" viewBox=\\"0 0 500 500\\">ILLUSTRATION CARTOON</svg>"}}

Le SVG illustre le thème "{sujet}" avec des personnages expressifs, flat design cartoon coloré."""

    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.6,
                max_tokens=2800,
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

    # Extraire le SVG avant parsing JSON
    svg_extracted = ""
    svg_match = re.search(r'"svg"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
    if svg_match:
        svg_raw = svg_match.group(1)
        svg_extracted = (svg_raw
            .replace('\\"', '"').replace('\\/', '/')
            .replace('\\n', '').replace('\\t', ''))
        text = text[:svg_match.start()] + '"svg":"__SVG__"' + text[svg_match.end():]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        try:
            from json_repair import repair_json
            data = json.loads(repair_json(text))
            print("JSON réparé via json-repair")
        except Exception:
            raise ValueError(f"JSON invalide : {text[:300]}")

    if svg_extracted:
        data["svg"] = svg_extracted

    for key in ["accroche", "slides", "cta", "cta_sous", "caption"]:
        if key not in data:
            raise ValueError(f"Clé manquante : '{key}'")
    if not isinstance(data.get("slides"), list) or len(data["slides"]) < 2:
        raise ValueError("'slides' doit avoir au moins 2 éléments")

    return data


def get_valid_svg(data: dict, sujet: str) -> str:
    svg = data.get("svg", "").strip()
    if not svg.startswith("<svg"):
        m = re.search(r'<svg[\s\S]*?</svg>', svg)
        svg = m.group(0) if m else ""
    if svg:
        try:
            cairosvg.svg2png(bytestring=svg.encode(), output_width=50, output_height=50)
            print(f"SVG Groq valide ✓ ({len(svg)} chars)")
            return svg
        except Exception as ex:
            print(f"SVG Groq invalide ({ex}) → fallback")

    s = sujet.lower()
    if any(w in s for w in ["famille","parent","enfant","proche"]):   return SVG_FAMILY
    if any(w in s for w in ["cerveau","neuro","rechute","science"]):  return SVG_BRAIN
    if any(w in s for w in ["honte","identité","miroir","estime"]):   return SVG_MIRROR
    if any(w in s for w in ["arbre","croissance","chemin","rétabli"]): return SVG_TREE
    return SVG_PEOPLE

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — SVG FALLBACKS
# ═══════════════════════════════════════════════════════════════════════════════

SVG_PEOPLE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">
  <circle cx="250" cy="270" r="205" fill="#DDE3ED"/>
  <circle cx="155" cy="195" r="58" fill="#FBBF8A"/>
  <ellipse cx="155" cy="158" rx="45" ry="28" fill="#E8622A"/>
  <circle cx="128" cy="168" r="20" fill="#E8622A"/>
  <circle cx="182" cy="168" r="20" fill="#E8622A"/>
  <rect x="110" y="248" width="90" height="100" rx="32" fill="#3B82F6"/>
  <path d="M200 285 Q255 260 280 275" stroke="#FBBF8A" stroke-width="30" stroke-linecap="round" fill="none"/>
  <circle cx="140" cy="197" r="7" fill="#7C3A1E"/>
  <circle cx="170" cy="197" r="7" fill="#7C3A1E"/>
  <path d="M138 215 Q155 228 172 215" stroke="#7C3A1E" stroke-width="4" fill="none" stroke-linecap="round"/>
  <ellipse cx="128" cy="210" rx="13" ry="9" fill="#F9A8A8" opacity="0.65"/>
  <ellipse cx="182" cy="210" rx="13" ry="9" fill="#F9A8A8" opacity="0.65"/>
  <circle cx="345" cy="195" r="58" fill="#C68642"/>
  <ellipse cx="345" cy="162" rx="42" ry="25" fill="#6B7280"/>
  <circle cx="318" cy="170" r="18" fill="#6B7280"/>
  <circle cx="372" cy="170" r="18" fill="#6B7280"/>
  <rect x="300" y="248" width="90" height="100" rx="32" fill="#F472B6"/>
  <path d="M300 285 Q245 260 220 275" stroke="#C68642" stroke-width="30" stroke-linecap="round" fill="none"/>
  <circle cx="330" cy="197" r="7" fill="#4A2008"/>
  <circle cx="360" cy="197" r="7" fill="#4A2008"/>
  <path d="M328 215 Q345 228 362 215" stroke="#4A2008" stroke-width="4" fill="none" stroke-linecap="round"/>
  <ellipse cx="318" cy="210" rx="13" ry="9" fill="#F9A8A8" opacity="0.55"/>
  <ellipse cx="372" cy="210" rx="13" ry="9" fill="#F9A8A8" opacity="0.55"/>
  <ellipse cx="250" cy="278" rx="38" ry="28" fill="#DEB887"/>
  <path d="M250 155 C250 155 232 137 220 147 C208 157 220 175 250 193 C280 175 292 157 280 147 C268 137 250 155 250 155Z" fill="#E85D5D"/>
  <g transform="translate(420,88)"><path d="M0,-22 L5.5,-5.5 L22,0 L5.5,5.5 L0,22 L-5.5,5.5 L-22,0 L-5.5,-5.5 Z" fill="#FCD34D"/></g>
  <g transform="translate(78,388)"><path d="M0,-14 L3.5,-3.5 L14,0 L3.5,3.5 L0,14 L-3.5,3.5 L-14,0 L-3.5,-3.5 Z" fill="#FCD34D"/></g>
</svg>"""

SVG_BRAIN = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 420">
  <ellipse cx="252" cy="395" rx="155" ry="18" fill="#FECACA" opacity="0.4"/>
  <path d="M250 335 C180 335 120 305 95 260 C70 215 75 160 100 130 C120 105 148 95 165 103 C168 80 182 63 200 60 C215 57 228 65 235 77 C240 63 252 53 265 53Z" fill="#FF8FAB"/>
  <path d="M250 335 C320 335 380 305 405 260 C430 215 425 160 400 130 C380 105 352 95 335 103 C332 80 318 63 300 60 C285 57 272 65 265 77 C260 63 248 53 235 53Z" fill="#FF8FAB"/>
  <path d="M250 335 L250 53" stroke="#FF6B8A" stroke-width="5" stroke-linecap="round"/>
  <path d="M115 175 Q145 157 170 173 Q195 189 180 210" fill="none" stroke="#FF6B8A" stroke-width="4.5" stroke-linecap="round"/>
  <path d="M100 225 Q133 205 160 223 Q187 241 168 263" fill="none" stroke="#FF6B8A" stroke-width="4.5" stroke-linecap="round"/>
  <path d="M385 175 Q355 157 330 173 Q305 189 320 210" fill="none" stroke="#FF6B8A" stroke-width="4.5" stroke-linecap="round"/>
  <path d="M400 225 Q367 205 340 223 Q313 241 332 263" fill="none" stroke="#FF6B8A" stroke-width="4.5" stroke-linecap="round"/>
  <path d="M118 195 Q250 173 382 195 Q382 225 250 213 Q118 225 118 195Z" fill="#C7D2FE" opacity="0.85"/>
  <ellipse cx="178" cy="255" rx="22" ry="22" fill="white"/>
  <circle cx="178" cy="259" r="13" fill="#2D2D2D"/>
  <circle cx="183" cy="254" r="5" fill="white"/>
  <ellipse cx="322" cy="255" rx="22" ry="22" fill="white"/>
  <circle cx="322" cy="259" r="13" fill="#2D2D2D"/>
  <circle cx="327" cy="254" r="5" fill="white"/>
  <path d="M205 292 Q250 315 295 292" stroke="#2D2D2D" stroke-width="5" fill="none" stroke-linecap="round"/>
  <ellipse cx="148" cy="287" rx="28" ry="17" fill="#FF8FAB" opacity="0.5"/>
  <ellipse cx="352" cy="287" rx="28" ry="17" fill="#FF8FAB" opacity="0.5"/>
  <path d="M120 287 Q88 292 78 315" stroke="#FF8FAB" stroke-width="18" stroke-linecap="round" fill="none"/>
  <ellipse cx="74" cy="323" rx="16" ry="12" fill="#FF8FAB"/>
  <path d="M380 287 Q412 292 422 315" stroke="#FF8FAB" stroke-width="18" stroke-linecap="round" fill="none"/>
  <ellipse cx="426" cy="323" rx="16" ry="12" fill="#FF8FAB"/>
  <g transform="translate(405,62)"><path d="M0,-28 L7,-7 L28,0 L7,7 L0,28 L-7,7 L-28,0 L-7,-7 Z" fill="#FCD34D"/></g>
  <g transform="translate(72,352)"><path d="M0,-18 L4.5,-4.5 L18,0 L4.5,4.5 L0,18 L-4.5,4.5 L-18,0 L-4.5,-4.5 Z" fill="#FCD34D"/></g>
</svg>"""

SVG_FAMILY = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">
  <circle cx="250" cy="270" r="210" fill="#DDE3ED"/>
  <circle cx="130" cy="165" r="55" fill="#FBBF8A"/>
  <ellipse cx="130" cy="130" rx="42" ry="26" fill="#E8622A"/>
  <circle cx="105" cy="138" r="18" fill="#E8622A"/>
  <circle cx="155" cy="138" r="18" fill="#E8622A"/>
  <rect x="88" y="215" width="84" height="105" rx="30" fill="#3B82F6"/>
  <rect x="88" y="305" width="34" height="75" rx="17" fill="#3B82F6"/>
  <rect x="138" y="305" width="34" height="75" rx="17" fill="#3B82F6"/>
  <circle cx="117" cy="167" r="7" fill="#7C3A1E"/>
  <circle cx="143" cy="167" r="7" fill="#7C3A1E"/>
  <path d="M115 183 Q130 195 145 183" stroke="#7C3A1E" stroke-width="4" fill="none" stroke-linecap="round"/>
  <ellipse cx="106" cy="178" rx="12" ry="8" fill="#F9A8A8" opacity="0.6"/>
  <ellipse cx="154" cy="178" rx="12" ry="8" fill="#F9A8A8" opacity="0.6"/>
  <circle cx="370" cy="165" r="55" fill="#C68642"/>
  <ellipse cx="370" cy="133" rx="40" ry="24" fill="#6B7280"/>
  <circle cx="345" cy="140" r="17" fill="#6B7280"/>
  <circle cx="395" cy="140" r="17" fill="#6B7280"/>
  <rect x="328" y="215" width="84" height="105" rx="30" fill="#F472B6"/>
  <rect x="328" y="305" width="34" height="75" rx="17" fill="#F472B6"/>
  <rect x="378" y="305" width="34" height="75" rx="17" fill="#F472B6"/>
  <circle cx="357" cy="167" r="7" fill="#4A2008"/>
  <circle cx="383" cy="167" r="7" fill="#4A2008"/>
  <path d="M355 183 Q370 195 385 183" stroke="#4A2008" stroke-width="4" fill="none" stroke-linecap="round"/>
  <circle cx="250" cy="245" r="42" fill="#FBBF8A"/>
  <ellipse cx="250" cy="218" rx="32" ry="18" fill="#92400E"/>
  <rect x="218" y="283" width="64" height="85" rx="24" fill="#4ADE80"/>
  <circle cx="240" cy="247" r="5.5" fill="#7C3A1E"/>
  <circle cx="260" cy="247" r="5.5" fill="#7C3A1E"/>
  <path d="M238 262 Q250 272 262 262" stroke="#7C3A1E" stroke-width="3.5" fill="none" stroke-linecap="round"/>
  <ellipse cx="232" cy="258" rx="10" ry="7" fill="#F9A8A8" opacity="0.6"/>
  <ellipse cx="268" cy="258" rx="10" ry="7" fill="#F9A8A8" opacity="0.6"/>
  <path d="M170 270 Q205 285 218 295" stroke="#FBBF8A" stroke-width="22" stroke-linecap="round" fill="none"/>
  <path d="M330 270 Q295 285 282 295" stroke="#C68642" stroke-width="22" stroke-linecap="round" fill="none"/>
  <g transform="translate(430,95)"><path d="M0,-20 L5,-5 L20,0 L5,5 L0,20 L-5,5 L-20,0 L-5,-5 Z" fill="#FCD34D"/></g>
</svg>"""

SVG_TREE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">
  <circle cx="250" cy="270" r="210" fill="#DDE3ED"/>
  <path d="M200 415 C200 415 165 440 140 452" stroke="#8B6914" stroke-width="7" stroke-linecap="round" fill="none"/>
  <path d="M200 415 C200 415 200 450 200 465" stroke="#8B6914" stroke-width="7" stroke-linecap="round" fill="none"/>
  <path d="M200 415 C200 415 235 440 260 452" stroke="#8B6914" stroke-width="7" stroke-linecap="round" fill="none"/>
  <rect x="182" y="295" width="36" height="125" rx="14" fill="#A0784A"/>
  <ellipse cx="200" cy="302" rx="120" ry="90" fill="#7BC47F"/>
  <ellipse cx="200" cy="245" rx="100" ry="82" fill="#5BAF60"/>
  <ellipse cx="200" cy="193" rx="80" ry="68" fill="#3D9443"/>
  <ellipse cx="200" cy="148" rx="58" ry="52" fill="#2D7A35"/>
  <circle cx="148" cy="248" r="11" fill="#E85D5D"/>
  <circle cx="255" cy="255" r="11" fill="#E85D5D"/>
  <circle cx="200" cy="222" r="10" fill="#F7C948"/>
  <circle cx="165" cy="198" r="9" fill="#E85D5D"/>
  <circle cx="238" cy="205" r="9" fill="#F7C948"/>
  <g transform="translate(390,110)"><path d="M0,-20 L5,-5 L20,0 L5,5 L0,20 L-5,5 L-20,0 L-5,-5 Z" fill="#FCD34D"/></g>
</svg>"""

SVG_MIRROR = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500">
  <circle cx="250" cy="265" r="210" fill="#DDE3ED"/>
  <rect x="148" y="68" width="204" height="294" rx="102" fill="#E8D5B7" stroke="#C4A167" stroke-width="7"/>
  <rect x="165" y="85" width="170" height="260" rx="88" fill="#EEF6FB"/>
  <path d="M190 115 C190 115 175 140 178 162" stroke="white" stroke-width="7" stroke-linecap="round" opacity="0.7"/>
  <rect x="224" y="362" width="52" height="82" rx="26" fill="#C4A167"/>
  <circle cx="250" cy="180" r="42" fill="#FBBF8A"/>
  <ellipse cx="250" cy="150" rx="35" ry="20" fill="#E8622A"/>
  <circle cx="228" cy="157" r="14" fill="#E8622A"/>
  <circle cx="272" cy="157" r="14" fill="#E8622A"/>
  <rect x="218" y="218" width="64" height="88" rx="24" fill="#A78BFA"/>
  <circle cx="238" cy="182" r="6" fill="#7C3A1E"/>
  <circle cx="262" cy="182" r="6" fill="#7C3A1E"/>
  <path d="M236 198 Q250 210 264 198" stroke="#7C3A1E" stroke-width="4" fill="none" stroke-linecap="round"/>
  <ellipse cx="228" cy="194" rx="11" ry="8" fill="#F9A8A8" opacity="0.65"/>
  <ellipse cx="272" cy="194" rx="11" ry="8" fill="#F9A8A8" opacity="0.65"/>
  <g transform="translate(108,115)"><path d="M0,-16 L4,-4 L16,0 L4,4 L0,16 L-4,4 L-16,0 L-4,-4 Z" fill="#FCD34D"/></g>
  <g transform="translate(392,115)"><path d="M0,-16 L4,-4 L16,0 L4,4 L0,16 L-4,4 L-16,0 L-4,-4 Z" fill="#FCD34D"/></g>
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
    # Forcer viewBox si absent
    svg = svg_str.strip()
    if 'viewBox' not in svg:
        svg = svg.replace('<svg ', '<svg viewBox="0 0 500 500" ', 1)
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=px, output_height=px)
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    # Resize de sécurité si cairosvg a ignoré les dimensions
    if img.size != (px, px):
        img = img.resize((px, px), Image.LANCZOS)
    return img

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — CRÉATION DES SLIDES
# ═══════════════════════════════════════════════════════════════════════════════

def make_cover(titre: str, svg: str, total: int) -> str:
    """
    Zones strictes — rien ne déborde jamais :
      TITRE : y=55  → y=400  (police réduite si titre long)
      ILLUS : y=415 → y=950  (SVG figé à 380px max, centré)
      NAV   : y=950 → y=1080
    """
    ILLUS_SIZE = 380
    TITRE_Y1, TITRE_Y2 = 55, 400
    ILLUS_Y1, ILLUS_Y2 = 415, 950

    img = Image.new("RGB", (SIZE, SIZE), BG_COVER)
    img = _blob(img, SIZE-30, SIZE//2+60, 340,420, (188,200,215), alpha=65)
    img = _blob(img, -20,     SIZE-50,   160,160, (190,205,215), alpha=40)

    # Illustration — taille fixe 380px, centrée dans sa zone
    illus = _svg_to_pil(svg, ILLUS_SIZE)
    zone_h = ILLUS_Y2 - ILLUS_Y1
    ix = (SIZE - ILLUS_SIZE) // 2
    iy = ILLUS_Y1 + (zone_h - ILLUS_SIZE) // 2
    img.paste(illus, (ix, iy), illus)

    # Titre — police adaptative pour tenir dans la zone
    d = ImageDraw.Draw(img)
    margin = 55
    max_w  = SIZE - margin * 2
    f, lines = None, []
    for font_size in [108, 92, 78, 66, 54]:
        f     = F("OpenSans-ExtraBold.ttf", font_size)
        lines = _wrap(d, titre.upper(), f, max_w)
        if len(lines) * int(font_size * 1.08) <= (TITRE_Y2 - TITRE_Y1 - 20):
            break

    bloc_h = len(lines) * int(f.size * 1.08)
    y = TITRE_Y1 + (TITRE_Y2 - TITRE_Y1 - bloc_h) // 2
    for line in lines:
        d.text((margin, y), line, font=f, fill=DARK)
        y += int(f.size * 1.08)

    _sep(d)
    _arrow_btn(d, SIZE-100, SIZE-100)
    _nav_dots(d, total, 0)
    path = "/tmp/afder_slide_1.png"
    img.save(path, format="PNG")
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
    if len(lines)>2: f_cta=F("OpenSans-ExtraBold.ttf",88); lines=_wrap(d,cta_titre,f_cta,SIZE-130)
    y=255
    for line in lines:
        bb=d.textbbox((0,0),line,font=f_cta)
        d.text(((SIZE-(bb[2]-bb[0]))//2,y),line,font=f_cta,fill=DARK)
        y+=int(f_cta.size*1.08)

    y+=34; f_sub=F("OpenSans-Regular.ttf",50)
    for line in _wrap(d,cta_sous,f_sub,SIZE-175):
        bb=d.textbbox((0,0),line,font=f_sub)
        d.text(((SIZE-(bb[2]-bb[0]))//2,y),line,font=f_sub,fill=MID_GREY)
        y+=int(f_sub.size*1.48)

    f_h=F("OpenSans-Semibold.ttf",46); handle="@AFDER.RECOVERY"
    bb=d.textbbox((0,0),handle,font=f_h)
    d.text(((SIZE-(bb[2]-bb[0]))//2,SIZE-130),handle,font=f_h,fill=DARK)
    _sep(d,SIZE-172)
    _prev_btn(d,SIZE//2)
    _nav_dots(d,total,total-1)
    path=f"/tmp/afder_slide_{total}.png"
    img.save(path,format="PNG")
    return path

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — PUBLICATION INSTAGRAM
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
# SECTION 8 — MAIN
# ═══════════════════════════════════════════════════════════════════════════════

# 1. Refresh token
IG_TOKEN = refresh_instagram_token(IG_TOKEN)

# 2. Sélection sujet anti-doublon
hist, hist_sha = get_historique()
today    = datetime.date.today().strftime("%Y-%m-%d")
deja_vus = [h.get("sujet","") for h in hist]
neufs    = [s for s in SUJETS if s not in deja_vus]
sujet    = random.choice(neufs) if neufs else deja_vus[0]
print(f"Sujet : {sujet}")

# 3. Groq — texte + SVG
client = Groq(api_key=GROQ_API_KEY)
print("Génération Groq…")
raw  = generate_with_retry(client, sujet)
data = parse_groq_response(raw)
svg  = get_valid_svg(data, sujet)
print(f"Titre : {data['accroche']}")
print(f"SVG   : {len(svg)} chars")

# 4. Historique
hist.append({"date": today, "sujet": sujet})
save_historique(hist, hist_sha)

# 5. Slides
total  = 4
slides = [
    make_cover(data["accroche"], svg, total),
    make_content(data["slides"][0]["contenu"], 2, total),
    make_content(data["slides"][1]["contenu"], 3, total),
    make_cta(data["cta"], data["cta_sous"], total),
]
print(f"Slides : {slides}")

# 6. Upload Cloudinary en PNG
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

# 7. Publier Instagram (pause entre chaque container)
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
